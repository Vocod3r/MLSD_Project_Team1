"""Tests for FastAPI endpoints, asynchronous execution, rate limiting, and run caching (A4, D7, L6)."""

import time
import datetime as dt
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.store import STORE, MemoryStore


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def sample_fnol():
    today = dt.date.today()
    return {
        "policy_number": f"POL-{int(time.time()*1000)}",
        "insured_name": "Rohan Mehta",
        "vehicle_registration": "MH-02-CD-5678",
        "channel": "web",
        "date_of_loss": str(today - dt.timedelta(days=1)),
        "date_of_report": str(today),
        "place_of_loss": "Mumbai, Maharashtra",
        "estimated_loss_inr": 35000.0,
        "description": "Rear bumper dented while reversing at a supermarket parking lot.",
        "garage_name": "Carnation Auto Mumbai",
        "cashless_requested": True,
        "third_party_involved": False,
        "injuries": False,
        "police_report_filed": False,
    }


def test_health_check(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "queue" in data
    assert "store" in data


def test_metrics_endpoint(client):
    resp = client.get("/metrics")
    assert resp.status_code == 200
    assert "claims_http_requests_total" in resp.text


def test_submit_valid_claim_returns_202_queued(client, sample_fnol):
    resp = client.post("/claims", json=sample_fnol)
    assert resp.status_code == 202
    assert resp.headers.get("X-Cache") == "MISS"
    data = resp.json()
    assert "run_id" in data
    assert data["status"] == "queued"
    assert data["poll_url"] == f"/runs/{data['run_id']}"


def test_get_run_lifecycle_and_feedback(client, sample_fnol):
    # Submit claim
    resp = client.post("/claims", json=sample_fnol)
    run_id = resp.json()["run_id"]

    # Poll run
    poll_resp = client.get(f"/runs/{run_id}")
    assert poll_resp.status_code == 200
    run_data = poll_resp.json()
    assert run_data["run_id"] == run_id
    assert run_data["status"] in ("queued", "running", "completed", "escalated")

    # Post handler feedback (L6)
    fb_resp = client.post(f"/runs/{run_id}/feedback", json={
        "satisfactory": True,
        "reason": "Accurate coverage check and fast track routing."
    })
    assert fb_resp.status_code == 201
    assert fb_resp.json() == {"ok": True}

    # Summary check
    summary_resp = client.get("/feedback/summary")
    assert summary_resp.status_code == 200
    summary = summary_resp.json()
    assert summary["total"] >= 1


def test_per_client_rate_limiting(client, sample_fnol):
    client_id = f"client_rate_test_{time.time()}"
    headers = {"X-Client-Id": client_id}

    # Default RATE_LIMIT_PER_MIN is 30. Sending 35 requests should trigger 429
    hit_429 = False
    for i in range(35):
        # vary policy number slightly to avoid caching
        payload = dict(sample_fnol, policy_number=f"POL-RL-{i}-{time.time()}")
        resp = client.post("/claims", json=payload, headers=headers)
        if resp.status_code == 429:
            hit_429 = True
            assert "Retry-After" in resp.headers
            assert "exceeded" in resp.json()["detail"]
            break

    assert hit_429, "Rate limit of 30/min was not enforced!"


def test_run_caching_returns_200_cache_hit(client, sample_fnol):
    # Unique client to avoid rate limits
    headers = {"X-Client-Id": f"client_cache_test_{time.time()}"}

    # 1. First submission (enqueued)
    resp1 = client.post("/claims", json=sample_fnol, headers=headers)
    assert resp1.status_code == 202
    run_id1 = resp1.json()["run_id"]

    # Mock the run completion in the store so it qualifies for caching
    run_data = STORE.get_json(f"run:{run_id1}")
    run_data.update(status="completed", result={"route": "fast_track", "claim_type": "own_damage"})
    STORE.set_json(f"run:{run_id1}", run_data)

    # 2. Second submission with IDENTICAL payload
    resp2 = client.post("/claims", json=sample_fnol, headers=headers)
    assert resp2.status_code == 200
    assert resp2.headers.get("X-Cache") == "HIT"
    body2 = resp2.json()
    assert body2["cached"] is True
    assert body2["run_id"] == run_id1
    assert body2["status"] == "completed"
