"""Tests providing formal proof that quarantined requests never start an agent run (F2, D1, Demo Item 4)."""

import datetime as dt
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.store import STORE, MemoryStore


@pytest.fixture
def client():
    return TestClient(app)


def count_run_keys():
    """Counts active run keys in STORE to prove no new run is initialized."""
    if isinstance(STORE, MemoryStore):
        with STORE._lock:
            return sum(1 for k in STORE._kv.keys() if k.startswith("run:") and not k.startswith("runcache:"))
    else:
        # Redis store fallback
        return len(STORE.r.keys("run:*"))


def test_malformed_fnol_quarantined_and_no_run_started(client):
    # 1. Record baseline count of runs
    initial_runs = count_run_keys()

    # 2. Prepare malformed payload (invalid registration plate, future date, missing garage for cashless)
    tomorrow = dt.date.today() + dt.timedelta(days=2)
    malformed_payload = {
        "policy_number": "POL-12345",
        "insured_name": "Test Claimant",
        "vehicle_registration": "NOT_A_VALID_NUMBER",
        "channel": "app",
        "date_of_loss": str(tomorrow),
        "date_of_report": str(tomorrow),
        "place_of_loss": "Bangalore",
        "estimated_loss_inr": -5000.0,
        "description": "Short",
        "garage_name": None,
        "cashless_requested": True,
    }

    # 3. Post to boundary
    resp = client.post("/claims", json=malformed_payload)
    assert resp.status_code == 422
    data = resp.json()

    assert "quarantine_id" in data
    assert "errors" in data
    qid = data["quarantine_id"]
    assert qid.startswith("q_")

    # 4. PROOF 1: The rejected request is preserved in quarantine storage with field-level errors
    q_entry = STORE.get_json(f"quarantine:{qid}")
    assert q_entry is not None
    assert q_entry["quarantine_id"] == qid
    assert len(q_entry["errors"]) >= 3
    assert q_entry["payload"]["vehicle_registration"] == "NOT_A_VALID_NUMBER"

    # 5. PROOF 2: Recent quarantine list records this event
    recent_q = STORE.list("quarantine:recent", n=10)
    assert any(q["quarantine_id"] == qid for q in recent_q)

    # 6. PROOF 3: No run ID was created for this quarantine entry
    assert STORE.get_json(f"run:{qid}") is None

    # 7. PROOF 4: The total number of runs in the system DID NOT INCREASE
    final_runs = count_run_keys()
    assert final_runs == initial_runs, f"Expected {initial_runs} runs, but found {final_runs}. An agent run was illegally created!"


def test_invalid_json_body_quarantined_and_no_run_started(client):
    initial_runs = count_run_keys()

    # Send completely malformed raw JSON bytes
    resp = client.post("/claims", content=b"{ broken_json: [", headers={"Content-Type": "application/json"})
    assert resp.status_code == 422
    data = resp.json()

    qid = data["quarantine_id"]
    q_entry = STORE.get_json(f"quarantine:{qid}")
    assert q_entry is not None
    assert any(e["field"] == "(body)" for e in q_entry["errors"])

    # No run was initiated
    assert count_run_keys() == initial_runs
