"""Locust load test for Motor Insurance Claim Intake & Triage (D6, A7).

Measures end-to-end run duration from submission to final result completion
against the deterministic stub model.
"""

import time
import uuid
import datetime as dt
from locust import HttpUser, task, between


class ClaimIntakeUser(HttpUser):
    wait_time = between(0.1, 0.5)

    @task(4)
    def submit_and_poll_claim(self):
        """Standard valid claim lifecycle: submit -> poll until completed."""
        today = dt.date.today()
        client_uid = uuid.uuid4().hex[:8]
        payload = {
            "policy_number": f"POL-LOCUST-{client_uid}",
            "insured_name": f"Locust User {client_uid}",
            "vehicle_registration": "KA-01-AB-1234",
            "channel": "app",
            "date_of_loss": str(today - dt.timedelta(days=1)),
            "date_of_report": str(today),
            "place_of_loss": "Bangalore",
            "estimated_loss_inr": 25000.0,
            "description": "Front bumper cracked after hitting a bollard while parking.",
            "garage_name": "Rapid Care Motors",
            "cashless_requested": True,
            "third_party_involved": False,
            "injuries": False,
            "police_report_filed": False,
        }

        headers = {
            "Content-Type": "application/json",
            "X-Client-Id": f"client_{client_uid}",
        }

        t_start = time.perf_counter()

        # 1. Submit claim (202 Accepted)
        with self.client.post("/claims", json=payload, headers=headers, catch_response=True) as resp:
            if resp.status_code == 202:
                resp.success()
                body = resp.json()
                poll_url = body.get("poll_url")
            elif resp.status_code == 200:
                resp.success()  # Cache hit
                return
            else:
                resp.failure(f"Submit failed: status {resp.status_code}")
                return

        # 2. Poll until terminal state
        terminal_statuses = {"completed", "escalated", "failed", "degraded"}
        max_poll_time = 30.0
        poll_interval = 0.5

        while time.perf_counter() - t_start < max_poll_time:
            time.sleep(poll_interval)
            with self.client.get(poll_url, name="/runs/{id} [poll]", catch_response=True) as poll_resp:
                if poll_resp.status_code == 200:
                    status = poll_resp.json().get("status")
                    if status in terminal_statuses:
                        poll_resp.success()
                        # Record full end-to-end transaction latency
                        e2e_time = (time.perf_counter() - t_start) * 1000
                        self.environment.events.request.fire(
                            request_type="E2E",
                            name="claim_full_lifecycle",
                            response_time=e2e_time,
                            response_length=len(poll_resp.content),
                            exception=None,
                            context=None
                        )
                        return
                    else:
                        poll_resp.success()
                else:
                    poll_resp.failure(f"Poll returned status {poll_resp.status_code}")
                    return

    @task(1)
    def submit_malformed_claim(self):
        """Tests that malformed claims are instantly quarantined with 422 under load."""
        payload = {
            "policy_number": "BAD",
            "insured_name": "Test",
            "vehicle_registration": "NOT-A-PLATE",
            "channel": "invalid_channel",
            "date_of_loss": "2030-01-01",
            "date_of_report": "2030-01-01",
            "place_of_loss": "Nowhere",
            "estimated_loss_inr": -100.0,
            "description": "Short",
        }
        with self.client.post("/claims", json=payload, catch_response=True) as resp:
            if resp.status_code == 422:
                resp.success()
            else:
                resp.failure(f"Expected 422 for malformed claim, got {resp.status_code}")
