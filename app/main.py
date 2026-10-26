"""Claim intake API (Person A: F1, F2, D1, A4, A8, D7, L6).

POST /claims                 validate -> quarantine (422) or queue a run (202 + run_id)
GET  /runs/{run_id}          poll status and result
POST /runs/{run_id}/feedback handler feedback on a result
GET  /feedback/summary       aggregated feedback
GET  /quarantine             recently rejected requests (and /quarantine/{id})
GET  /health                 liveness + store check
/                            the web client (web/index.html)
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import logging
import os
import sys
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app.schemas import validate_fnol
from app.store import RUN_TTL_S, STORE
from app.metrics import (
    metrics_endpoint,
    HTTP_REQUESTS_TOTAL,
    HTTP_REQUEST_DURATION_SECONDS,
    CLAIMS_SUBMITTED_TOTAL,
    RUN_CACHE_HITS_TOTAL,
    RUN_CACHE_MISSES_TOTAL,
    RATE_LIMIT_EXCEEDED_TOTAL,
)

ROOT = Path(__file__).resolve().parent.parent
QUEUE_BACKEND = os.getenv("QUEUE_BACKEND", "inline")      # inline | rq
RATE_LIMIT_PER_MIN = int(os.getenv("RATE_LIMIT_PER_MIN", "30"))
RUN_CACHE_TTL_S = int(os.getenv("RUN_CACHE_TTL_S", "600"))  # 0 disables the run cache
JOB_TIMEOUT_S = int(os.getenv("JOB_TIMEOUT_S", "180"))


# ---------- structured JSON logs with correlation id ----------
class JsonFormatter(logging.Formatter):
    def format(self, r):
        out = {"ts": dt.datetime.now(dt.timezone.utc).isoformat(), "level": r.levelname,
               "logger": r.name, "msg": r.getMessage()}
        for k in ("correlation_id", "run_id", "quarantine_id", "status", "path", "code", "ms", "cache"):
            if hasattr(r, k):
                out[k] = getattr(r, k)
        return json.dumps(out)


class SafeStreamHandler(logging.StreamHandler):
    def emit(self, record):
        try:
            msg = self.format(record)
            stream = self.stream
            stream.write(msg + self.terminator)
            self.flush()
        except (ValueError, OSError):
            pass

    def handleError(self, record):
        t, v, tb = sys.exc_info()
        if isinstance(v, (ValueError, OSError)):
            return
        super().handleError(record)


_h = SafeStreamHandler(sys.stdout)
_h.setFormatter(JsonFormatter())
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"), handlers=[_h], force=True)
log = logging.getLogger("api")


# ---------- queue ----------
if QUEUE_BACKEND == "rq":
    import redis
    from rq import Queue
    _queue = Queue("claims", connection=redis.Redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379/0")))

    def enqueue(run_id, fnol):
        _queue.enqueue("app.worker.process_run", run_id, fnol, job_id=run_id, job_timeout=JOB_TIMEOUT_S)
else:
    _pool = ThreadPoolExecutor(max_workers=int(os.getenv("INLINE_WORKERS", "2")))

    def enqueue(run_id, fnol):
        from app.worker import process_run
        _pool.submit(process_run, run_id, fnol)


# ---------- app ----------
app = FastAPI(title="Motor Claim Intake & Triage")
app.add_middleware(CORSMiddleware, allow_origins=os.getenv("CORS_ORIGINS", "*").split(","),
                   allow_methods=["*"], allow_headers=["*"], expose_headers=["Retry-After", "X-Cache",
                                                                             "X-Correlation-ID"])


@app.middleware("http")
async def correlation_and_access_log(request: Request, call_next):
    cid = request.headers.get("X-Correlation-ID") or uuid.uuid4().hex
    request.state.cid = cid
    t0 = time.perf_counter()
    resp = await call_next(request)
    elapsed = time.perf_counter() - t0
    resp.headers["X-Correlation-ID"] = cid
    path = request.url.path
    HTTP_REQUESTS_TOTAL.labels(method=request.method, endpoint=path, status_code=str(resp.status_code)).inc()
    HTTP_REQUEST_DURATION_SECONDS.labels(endpoint=path).observe(elapsed)
    if not path.startswith(("/health", "/runs/")) or resp.status_code >= 400:
        log.info("request", extra={"correlation_id": cid, "path": f"{request.method} {path}",
                                   "code": resp.status_code, "ms": round(elapsed * 1000, 1)})
    return resp


def _now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def _client_id(request: Request):
    return request.headers.get("X-Client-Id") or (request.client.host if request.client else "unknown")


@app.post("/claims")
async def submit_claim(request: Request):
    cid = request.state.cid
    client_id = _client_id(request)

    # D7: per-client rate limit (fixed one-minute window)
    if RATE_LIMIT_PER_MIN > 0:
        n = STORE.incr(f"rl:{client_id}:{int(time.time() // 60)}", ttl=70)
        if n > RATE_LIMIT_PER_MIN:
            RATE_LIMIT_EXCEEDED_TOTAL.labels(client=client_id).inc()
            return JSONResponse({"detail": f"rate limit of {RATE_LIMIT_PER_MIN}/min exceeded"}, status_code=429,
                                headers={"Retry-After": str(60 - int(time.time()) % 60)})

    # F2 / D1: validate at the boundary; anything invalid is quarantined, no run is created
    raw = await request.body()
    try:
        payload = json.loads(raw or b"null")
    except json.JSONDecodeError as e:
        payload, errors = raw.decode("utf-8", "replace")[:5000], [{"field": "(body)", "message": f"invalid JSON: {e.msg}"}]
    else:
        fnol, errors = validate_fnol(payload)

    if errors:
        channel = payload.get("channel", "unknown") if isinstance(payload, dict) else "unknown"
        CLAIMS_SUBMITTED_TOTAL.labels(channel=channel, status="quarantined").inc()
        qid = "q_" + uuid.uuid4().hex[:12]
        STORE.set_json(f"quarantine:{qid}", {"quarantine_id": qid, "received_at": _now(), "correlation_id": cid,
                                             "client": client_id, "errors": errors, "payload": payload},
                       ttl=RUN_TTL_S)
        STORE.push("quarantine:recent", {"quarantine_id": qid, "received_at": _now(), "errors": errors})
        log.info("quarantined", extra={"correlation_id": cid, "quarantine_id": qid})
        return JSONResponse({"quarantine_id": qid, "errors": errors}, status_code=422)

    channel = fnol.get("channel", "unknown")
    # D7: identical FNOL recently completed -> return that run instead of running the agents again
    fp = hashlib.sha256(json.dumps(fnol, sort_keys=True).encode()).hexdigest()
    if RUN_CACHE_TTL_S > 0:
        cached = STORE.get_json(f"runcache:{fp}")
        prev = cached and STORE.get_json(f"run:{cached}")
        if prev and prev.get("status") in ("completed", "escalated"):
            RUN_CACHE_HITS_TOTAL.inc()
            CLAIMS_SUBMITTED_TOTAL.labels(channel=channel, status="cached").inc()
            log.info("cache hit", extra={"correlation_id": cid, "run_id": cached, "cache": "hit"})
            return JSONResponse({"run_id": cached, "status": prev["status"], "poll_url": f"/runs/{cached}",
                                 "cached": True}, status_code=200, headers={"X-Cache": "HIT"})

    RUN_CACHE_MISSES_TOTAL.inc()
    CLAIMS_SUBMITTED_TOTAL.labels(channel=channel, status="queued").inc()
    run_id = "run_" + uuid.uuid4().hex[:12]
    STORE.set_json(f"run:{run_id}", {"run_id": run_id, "status": "queued", "created_at": _now(),
                                     "correlation_id": cid, "fnol": fnol, "steps": []}, ttl=RUN_TTL_S)
    if RUN_CACHE_TTL_S > 0:
        STORE.set_json(f"runcache:{fp}", run_id, ttl=RUN_CACHE_TTL_S)
    enqueue(run_id, fnol)
    log.info("queued", extra={"correlation_id": cid, "run_id": run_id})
    return JSONResponse({"run_id": run_id, "status": "queued", "poll_url": f"/runs/{run_id}"}, status_code=202,
                        headers={"X-Cache": "MISS"})


@app.get("/runs/{run_id}")
def get_run(run_id: str):
    run = STORE.get_json(f"run:{run_id}")
    if not run:
        return JSONResponse({"detail": "run not found"}, status_code=404)
    run.pop("error", None)
    return run


class Feedback(BaseModel):
    satisfactory: bool
    reason: str = Field(default="", max_length=1000)


@app.post("/runs/{run_id}/feedback", status_code=201)
def post_feedback(run_id: str, fb: Feedback):
    run = STORE.get_json(f"run:{run_id}")
    if not run:
        return JSONResponse({"detail": "run not found"}, status_code=404)
    res = run.get("result") or {}
    STORE.push("feedback", {"run_id": run_id, "at": _now(), **fb.model_dump(),
                            "route": res.get("route"), "claim_type": res.get("claim_type"),
                            "prompt_version": res.get("prompt_version"), "status": run.get("status")},
               max_len=100000)
    return {"ok": True}


@app.get("/feedback/summary")
def feedback_summary():
    items = STORE.list("feedback", n=100000)
    by = {}
    for f in items:
        for dim in ("route", "prompt_version", "claim_type"):
            b = by.setdefault(dim, {}).setdefault(str(f.get(dim)), {"n": 0, "satisfactory": 0})
            b["n"] += 1
            b["satisfactory"] += bool(f["satisfactory"])
    for dim in by.values():
        for b in dim.values():
            b["rate"] = round(b["satisfactory"] / b["n"], 3)
    return {"total": len(items), "satisfactory": sum(bool(f["satisfactory"]) for f in items), "by": by,
            "recent_unsatisfactory": [f for f in items if not f["satisfactory"]][:20]}


@app.get("/quarantine")
def list_quarantine(n: int = 50):
    return STORE.list("quarantine:recent", n=n)


@app.get("/quarantine/{qid}")
def get_quarantine(qid: str):
    q = STORE.get_json(f"quarantine:{qid}")
    return q or JSONResponse({"detail": "not found"}, status_code=404)


@app.get("/health")
def health():
    try:
        ok = bool(STORE.ping())
    except Exception as e:
        return JSONResponse({"status": "unhealthy", "store": str(e)}, status_code=503)
    return {"status": "ok" if ok else "unhealthy", "queue": QUEUE_BACKEND,
            "store": os.getenv("STORE_BACKEND", "memory")}


@app.get("/metrics")
def metrics():
    return metrics_endpoint()


# web client last, so it never shadows an API route
app.mount("/", StaticFiles(directory=ROOT / "web", html=True), name="web")