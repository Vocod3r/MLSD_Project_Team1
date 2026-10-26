"""Demonstration script for Item 4: Malformed request rejected and quarantined, with proof that no agent run started."""

import json
import sys
import datetime as dt
from fastapi.testclient import TestClient

from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.main import app
from app.store import STORE, MemoryStore


def count_active_runs():
    if isinstance(STORE, MemoryStore):
        with STORE._lock:
            return sum(1 for k in STORE._kv.keys() if k.startswith("run:") and not k.startswith("runcache:"))
    return len(STORE.r.keys("run:*"))


def main():
    print("=" * 70)
    print("DEMO ITEM 4: QUARANTINE STORE & PROOF OF ZERO AGENT RUN EXECUTION")
    print("=" * 70)

    client = TestClient(app)

    # 1. State before submission
    runs_before = count_active_runs()
    print(f"\n[1] Baseline Store State:")
    print(f"    Active Agent Runs in Store: {runs_before}")

    # 2. Submit malformed FNOL
    tomorrow = dt.date.today() + dt.timedelta(days=5)
    malformed_fnol = {
        "policy_number": "POL-INVALID",
        "insured_name": "Demonstration User",
        "vehicle_registration": "NOT-A-REG-NUMBER",
        "channel": "fax",  # invalid channel
        "date_of_loss": str(tomorrow),  # future date
        "date_of_report": str(tomorrow),
        "place_of_loss": "Demo City",
        "estimated_loss_inr": -15000.0,  # negative
        "description": "Short",  # too short
        "cashless_requested": True,
        "garage_name": None  # missing mandatory garage
    }

    print(f"\n[2] Submitting Malformed FNOL to POST /claims:")
    print(json.dumps(malformed_fnol, indent=4))

    resp = client.post("/claims", json=malformed_fnol)
    print(f"\n[3] Ingestion Boundary Response:")
    print(f"    HTTP Status: {resp.status_code} (Expected 422 Unprocessable Entity)")
    body = resp.json()
    qid = body.get("quarantine_id")
    errors = body.get("errors", [])
    print(f"    Quarantine ID: {qid}")
    print(f"    Field-Level Validation Errors Caught: ({len(errors)})")
    for err in errors:
        print(f"      - {err['field']}: {err['message']}")

    # 3. Verify Quarantine Store
    print(f"\n[4] Inspecting Quarantine Store (quarantine:{qid}):")
    stored_quarantine = STORE.get_json(f"quarantine:{qid}")
    if stored_quarantine:
        print(f"    [PASS] Record exists in quarantine storage.")
        print(f"    Preserved Client: {stored_quarantine.get('client')}")
        print(f"    Preserved Correlation ID: {stored_quarantine.get('correlation_id')}")
    else:
        print(f"    [FAIL] Record missing in quarantine storage!")
        sys.exit(1)

    # 4. Prove no run was started
    print(f"\n[5] Verifying Agent Run Isolation (THE PROOF):")
    runs_after = count_active_runs()
    run_for_quarantine = STORE.get_json(f"run:{qid}")

    print(f"    Check A: STORE.get_json('run:{qid}') -> {run_for_quarantine}")
    print(f"    Check B: Runs before = {runs_before}, Runs after = {runs_after}")

    if run_for_quarantine is None and runs_after == runs_before:
        print("\n" + "=" * 70)
        print("RESULT: PROOF SUCCESSFUL! The malformed request was safely quarantined,")
        print("and ZERO agent runs or worker jobs were initiated.")
        print("=" * 70 + "\n")
    else:
        print("\n[FAIL]: An agent run was created for a quarantined request!")
        sys.exit(1)


if __name__ == "__main__":
    main()
