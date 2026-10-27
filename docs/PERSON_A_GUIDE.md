# Person A: Ingestion, API, Observability & Deployment Guide

This document is a comprehensive, plain-English reference explaining everything implemented for **Person A**, how to run the viva demonstration commands, and how to access and view the **Grafana dashboard**.

---

## 1. The Big Picture: What Was Your Role?

In this project, our service processes motor insurance claims using AI agents.
Your role (**Person A**) is the **Gatekeeper, Queue Manager, and Operations Engineer**:
* **The Gatekeeper:** You validate incoming FNOL (First Notice of Loss) claims against strict data contracts and quarantine invalid ones with field-level errors. You ensure malformed requests **never** start an agent run.
* **The Queue Manager:** Since AI agents take 10–15 seconds to reason, you respond to the client immediately with an HTTP `202 Accepted` and a `run_id`, dropping the task into a background Redis queue for workers to process.
* **The Cost Controller:** You prevent abuse and save money by enforcing per-client rate limiting (30 req/min) and SHA-256 run caching for duplicate claims.
* **The Operations Engineer:** You build the local observability stack (Prometheus metrics, OpenTelemetry tracing to Jaeger, and Grafana dashboards) and package the system into a multi-service Docker Compose architecture.

---

## 2. Explanation of the Viva Demonstration Commands

During the evaluation and viva, your evaluators will ask you to demonstrate your features. Here is what each command does, step by step, and what it proves.

### Command 1: Run All 24 Unit & Integration Tests
```powershell
python -m pytest tests/ -v
```

* **What this command does:**
  Runs the complete test suite across three test modules:
  1. `tests/test_schemas.py` (16 tests): Tests every single field rule in `app/schemas.py`:
     - Standard Indian vehicle registrations (`KA-11-AB-1234`) and Bharat Series (`22-BH-1234-AA`).
     - Channel enum (`web`, `app`, `call_centre`).
     - Loss estimates bounded between ₹0 and ₹5 Crore.
     - Future date prevention for accident and report dates.
     - Cross-field consistency: report date must be on or after loss date; claims older than 365 days rejected; cashless repair requires `garage_name`; police report requires `fir_number`.
     - Rejection of unexpected fields (`extra="forbid"`).
  2. `tests/test_quarantine_proof.py` (2 tests): Verifies that malformed payloads and broken JSON are quarantined with HTTP `422` and that zero agent runs are started.
  3. `tests/test_api.py` (6 tests): Tests the FastAPI lifecycle:
     - `GET /health` returns `200 OK`.
     - `GET /metrics` exports Prometheus metrics.
     - `POST /claims` returns `202 Accepted` with `run_id` and `poll_url`.
     - `GET /runs/{id}` returns run status and steps.
     - `POST /runs/{id}/feedback` records user feedback.
     - Rate limiter blocks requests beyond 30/min with HTTP `429` and `Retry-After`.
     - Caching returns HTTP `200` with `X-Cache: HIT` and `cached: true` for duplicate submissions.
* **What it proves to the evaluator:**
  Proves that all code is fully functional, robust against edge cases, and satisfies requirements **F1, F2, D1, A4, D7, and L6**.

---

### Command 2: Malformed Request Quarantine & Proof of Zero Run (Demo Item 4)
```powershell
python scripts/verify_quarantine.py
```

* **What this command does:**
  Specifically built to satisfy **Demonstration Item 4** in the project rubric (*"A malformed request rejected and quarantined, with evidence that no agent run started"*).
  1. **Step 1 (Baseline):** Queries the datastore and prints the current count of active agent runs (e.g., `Runs before = 0`).
  2. **Step 2 (Submission):** Submits a deliberately broken claim to `POST /claims` (e.g. invalid plate `NOT-A-REG-NUMBER`, accident date 5 days in the future, negative damage cost, and cashless requested without a garage).
  3. **Step 3 (Rejection):** Verifies the server intercepts the request at the boundary and returns HTTP `422 Unprocessable Entity` with a generated `quarantine_id` (e.g. `q_3d0c4e133a23`) and 6 detailed field-level error messages.
  4. **Step 4 (Quarantine Store):** Queries the quarantine database (`quarantine:q_...`) and confirms the bad payload and errors were safely archived.
  5. **Step 5 (The Proof):** Checks whether `run:q_...` exists (it returns `None`) and re-counts all runs in the system (`Runs after = 0`). Because `Runs before == Runs after`, it proves that zero worker jobs or agent steps were initiated.
* **What it proves to the evaluator:**
  Gives undeniable visual proof on screen that invalid data never reaches the expensive LLM agent layer.

---

### Command 3: Cache Speedup & Cost Savings Benchmark (Requirement D7)
```powershell
python scripts/benchmark_cache.py
```

* **What this command does:**
  Measures the real-world impact of the run cache required by **Requirement D7** (*"Report the measured effect of caching on p95 and cost per run"*).
  1. Sends 20 distinct claims (uncached cache misses), recording the round-trip latency and LLM token costs (~$0.0025 per run).
  2. Re-sends the exact same 20 claims (cache hits), where the server recognizes the SHA-256 fingerprint of the form and instantly returns the previous decision without re-running agents.
  3. Computes the 50th percentile (median) and 95th percentile (p95) response times and costs for both groups.
  4. Prints a summary table:
     ```
     Metric                       Uncached (MISS)        Cached (HIT)          Change
     ---------------------------------------------------------------------------
     Ingestion p50 Latency:           4.49 ms             3.27 ms          1.4x faster
     Ingestion p95 Latency:          13.01 ms             5.27 ms          2.5x faster
     LLM Agent Cost per Run:     $ 0.00248        $ 0.00000       100.0% saved
     Cost per 100 Runs:          $   0.248        $   0.000       100% saved
     ```
* **What it proves to the evaluator:**
  Demonstrates that you quantified the performance and financial benefit of caching with empirical benchmarks ready for your final project report.

---

## 3. What is Grafana and How Do You See the Dashboard?

### What is Grafana?
**Grafana** is an open-source web application for visualizing metrics and monitoring data.
* **Prometheus** collects the raw numbers (like *how many requests per second?* or *how many milliseconds did the triage agent take?*).
* **Grafana** connects to Prometheus and turns those raw numbers into visual charts, graphs, and gauges.

---

### Step-by-Step: How to View the Dashboard

Our setup includes an **auto-provisioned** Grafana dashboard. You do **not** need to manually build charts or connect databases—it is already configured in `observability/grafana/`.

#### Step 1: Start the Multi-Service Stack
Ensure Docker Desktop is open and running on your computer, then start the stack:
```powershell
docker compose up --build
```
This spins up all 6 services: `redis`, `api`, `worker`, `jaeger`, `prometheus`, and `grafana`.

#### Step 2: Open Grafana in Your Web Browser
Open your browser and navigate to:
```
http://localhost:3000
```

#### Step 3: Log In
* **Username:** `admin`
* **Password:** `admin`
*(If prompted to change your password, click **Skip** or set a new password).*

#### Step 4: Open the Pre-Configured Dashboard
1. In the left navigation sidebar, click on **Dashboards** (or the four-squares icon).
2. Click on the pre-loaded dashboard named:
   **`Motor Claim Ingestion & Triage Dashboard`** (or browse folder `Motor Insurance Claim Triage`).

#### What You Will See on the Dashboard:
* **Ingestion Throughput (RPS):** Live line chart showing how many requests per second the API is handling.
* **Ingestion Latency p50 & p95:** Live graph showing median (p50) and 95th percentile (p95) response times in seconds.
* **Cache Hit Ratio (D7):** Big gauge metric showing what percentage of duplicate claims were resolved via cache.
* **Submissions by Status:** Multi-color graph breaking down claims into `queued`, `quarantined`, and `cached`.
* **Rate Limit Exceeded (429):** Spike graph showing when clients exceed the 30 requests/minute budget.

---

## 4. Other Accessible Local Interfaces

When `docker compose up` is running, you have access to four web interfaces:

| Service | URL | Purpose |
| :--- | :--- | :--- |
| **Claim Intake Web App** | `http://localhost:8000` | The primary UI where adjusters submit claims, view status, citations, and feedback. |
| **Prometheus Raw Metrics** | `http://localhost:9090` | Raw time-series database scraping `http://api:8000/metrics`. |
| **Jaeger Distributed Tracing** | `http://localhost:16686` | Search by `run_id` to view Gantt-chart timeline traces of every agent step. |
| **Grafana Dashboard** | `http://localhost:3000` | Live operational charts and system health monitoring. |
