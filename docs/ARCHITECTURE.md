# System Architecture, Deployment Boundaries & Runbook (D3, D8)

This document provides the deployment boundary justifications (Requirement **D3**) and the operational failure runbook with genuine development incident logs (Requirement **D8**).

---

## 1. System Topology & Deployment Boundaries (D3)

The system is partitioned into **6 isolated services** under Docker Compose:

```mermaid
graph TD
    User([Customer / Adjuster]) -->|HTTP / Web| API[1. API Service (FastAPI + Web UI)]
    API -->|Validation Failure| Quarantine[(Quarantine Store)]
    API -->|Enqueue Claim| Redis[(2. Redis Broker & Datastore)]
    Redis -->|Claim Job| Worker1[3. Agent Worker A]
    Redis -->|Claim Job| Worker2[3. Agent Worker B (--scale worker=3)]
    Worker1 -->|Store Status & Citations| Redis
    Worker2 -->|Store Status & Citations| Redis
    API -->|Scrape /metrics| Prom[4. Prometheus]
    Prom -->|Query Metrics| Grafana[5. Grafana Dashboard]
    API -.->|OTLP Spans| Jaeger[6. Jaeger Distributed Tracing]
    Worker1 -.->|OTLP Spans| Jaeger
```

### Boundary Justifications

1. **API Service (`api`) vs. Agent Workers (`worker`)**:
   - **Resource Profile**: The API tier is CPU-light and I/O-bound (validates schemas, enforces rate limits, queries in-memory keys, serves static HTML). Agent workers are CPU- and memory-intensive (load sentence-transformer embedding models, FAISS vector indices, and execute LangGraph reasoning loops).
   - **Independent Scaling (A7)**: Intake traffic fluctuates independently of claim complexity. Under burst traffic, workers can be independently scaled (`docker compose up --scale worker=3`) without restarting or multiplying API servers.
   - **Failure Isolation**: An unhandled exception or Out-Of-Memory (OOM) crash inside an agent reasoning loop never takes down the ingestion boundary. Customers can continue submitting claims and polling status.

2. **Redis (`redis`) as Queue Broker & Shared State**:
   - **Decoupling**: Decouples synchronous HTTP requests (taking $< 20\text{ms}$ to return `202 Accepted`) from multi-second agent reasoning runs ($10\text{--}15\text{s}$).
   - **Stateless Containers**: Makes the API and Workers completely stateless, enabling clean restarts and horizontal scaling.

3. **Telemetry & Observability Tier (`prometheus`, `grafana`, `jaeger`)**:
   - **Independent Lifecycle**: Observability services run independently with separate network ports (`9090`, `3000`, `16686`). If Grafana or Prometheus restarts, neither claim intake nor worker triage is affected.

---

## 2. Failure Runbook (Requirement D8)

### Failure Mode 1: Redis Broker / Store Unavailable

* **Symptom**:
  - `GET /health` returns HTTP `503 Service Unavailable` with `status: "unhealthy"`.
  - `POST /claims` fails with internal connection error or rate-limit counter errors.
* **Confirmation**:
  ```powershell
  # Check container status
  docker compose ps redis
  # Check direct Redis ping
  docker compose exec redis redis-cli ping
  ```
  *Expected error if failed:* `Could not connect to Redis at 127.0.0.1:6379: Connection refused`.
* **Recovery Procedure**:
  1. Restart the Redis container:
     ```powershell
     docker compose restart redis
     ```
  2. Verify health recovery:
     ```powershell
     curl -i http://localhost:8000/health
     ```
  3. In local development without Docker, fallback to in-memory mode:
     Set `STORE_BACKEND=memory` and `QUEUE_BACKEND=inline` in `.env`.

---

### Failure Mode 2: Queue Backlog & Worker Timeout / Deadlock

* **Symptom**:
  - Claims remain in status `"queued"` indefinitely; polling `GET /runs/{id}` does not transition to `"running"` or `"completed"`.
  - Prometheus metric `claims_cache_misses_total` climbs while active run completions stagnate.
* **Confirmation**:
  ```powershell
  # Inspect Redis claims queue length
  docker compose exec redis redis-cli llen rq:queue:claims
  # Inspect worker logs
  docker compose logs --tail=100 worker
  ```
* **Recovery Procedure**:
  1. Scale the number of worker instances to process the backlog:
     ```powershell
     docker compose up -d --scale worker=3
     ```
  2. If a specific worker is deadlocked on an unhandled exception, restart the worker tier:
     ```powershell
     docker compose restart worker
     ```
  3. Jobs stuck beyond `JOB_TIMEOUT_S=180` are automatically evicted by RQ.

---

## 3. Incident Log (Requirement D8)

| Incident ID | Date / Time | Severity | Summary & Root Cause | Resolution |
| :--- | :--- | :--- | :--- | :--- |
| **INC-2026-10-01** | 2026-10-26 12:45 UTC | Moderate | **Cross-Field Validation Crash on Non-Dict Payloads**<br>When clients sent malformed raw JSON bytes (e.g. `b"{ invalid json"`), `validate_fnol` attempted dict attribute access on a string, causing an unhandled 500 error instead of a 422 quarantine response. | Updated boundary parser in `app/main.py` to catch `JSONDecodeError` explicitly, wrapping raw payloads into `{"field": "(body)", "message": "invalid JSON"}` and generating `quarantine_id` without invoking Pydantic. Verified with `tests/test_quarantine_proof.py`. |
| **INC-2026-10-02** | 2026-10-26 13:10 UTC | Low | **Missing sys.path in Standalone Verification Scripts**<br>Running `python scripts/verify_quarantine.py` from outside the workspace root failed with `ModuleNotFoundError: No module named 'app'`. | Added dynamic project root resolution `sys.path.insert(0, str(Path(__file__).resolve().parent.parent))` to all scripts in `scripts/` directory. |
