# FNOL Data Contract (F1, F2, D1)

This document publishes the formal external data contract for the **First Notice of Loss (FNOL)** ingestion interface of the Motor Insurance Claim Intake & Triage service.

---

## 1. Boundary & Ingestion Principles

1. **Strict Boundary Enforcement (F2, D1)**: All incoming payloads to `POST /claims` are validated at the ingestion boundary before any agent, queue, or downstream service is invoked.
2. **Quarantine On Rejection**: Any payload failing type, range, categorical, format, or cross-field validation is rejected with HTTP `422 Unprocessable Entity` and saved into the quarantine store with field-level errors. **No agent run is created for quarantined requests.**
3. **No Unknown Fields**: Extra or unrecognised fields are strictly forbidden (`extra="forbid"`).
4. **Machine-Readable Schema**: The JSON Schema representation is available at [`docs/fnol_schema.json`](file:///d:/Ashvin/PES/Sem%205/ML%20and%20Agent%20Ops/Mini%20project/MLSD_Project_Team1/docs/fnol_schema.json).

---

## 2. Field Specifications

| Field Name | Type | Required | Constraints / Validation | Description |
| :--- | :--- | :---: | :--- | :--- |
| `policy_number` | string | **Yes** | Length: 5 – 40 chars | Motor insurance policy identifier. |
| `insured_name` | string | **Yes** | Length: 2 – 100 chars | Name of the policyholder. |
| `vehicle_registration` | string | **Yes** | Length: 4 – 15 chars. Must match Indian registration standard (`^[A-Z]{2}[ -]?\d{1,2}[ -]?[A-Z]{0,3}[ -]?\d{1,4}$`) or Bharat Series (`^\d{2}[ -]?BH[ -]?\d{4}[ -]?[A-Z]{1,2}$`). | Vehicle registration number (e.g. `KA-11-AB-1234` or `22-BH-1234-AA`). Normalized to uppercase. |
| `channel` | string (enum) | **Yes** | Allowed values: `"web"`, `"app"`, `"call_centre"` | Channel through which the FNOL arrived. |
| `date_of_loss` | string (date) | **Yes** | Format: `YYYY-MM-DD`. Cannot be in the future ($\le$ today). | Date on which the incident/loss occurred. |
| `date_of_report` | string (date) | **Yes** | Format: `YYYY-MM-DD`. Cannot be in the future ($\le$ today). | Date on which the claim is being reported. |
| `place_of_loss` | string | **Yes** | Length: 2 – 200 chars | Physical location/city where the loss occurred. |
| `estimated_loss_inr` | float / number | **Yes** | Minimum: `0.0`. Maximum: `5,00,00,000.0` (₹5 Crore). | Estimated loss amount in Indian Rupees. |
| `description` | string | **Yes** | Length: 15 – 5,000 chars | Narrative description of the incident. |
| `garage_name` | string \| null | Conditional | Max length: 120 chars. **Required if `cashless_requested` is true.** | Name of the repair facility. |
| `fir_number` | string \| null | Conditional | Max length: 60 chars. **Required if `police_report_filed` is true.** | Police First Information Report number. |
| `cashless_requested` | boolean | No | Default: `false` | Whether the claimant requests cashless repair settlement. |
| `third_party_involved`| boolean | No | Default: `false` | Whether third-party vehicle or property was affected. |
| `injuries` | boolean | No | Default: `false` | Whether any bodily injuries occurred in the incident. |
| `police_report_filed` | boolean | No | Default: `false` | Whether a police report/FIR was lodged. |

---

## 3. Cross-Field Consistency Rules

1. **Chronological Validity**:
   - `date_of_report` must be on or after `date_of_loss`.
2. **Reporting Window**:
   - `date_of_report - date_of_loss` must not exceed **365 days** (`MAX_REPORT_DELAY_DAYS`). Claims beyond this limit are rejected outright at the boundary rather than flagged.
3. **Cashless Prerequisite**:
   - When `cashless_requested == true`, a non-empty `garage_name` is mandatory.
4. **Police Report Prerequisite**:
   - When `police_report_filed == true`, a non-empty `fir_number` is mandatory.

---

## 4. Ingestion Response Contracts

### 4.1 Valid Ingestion (New Run)
* **Status**: `202 Accepted`
* **Headers**: `X-Cache: MISS`, `X-Correlation-ID: <uuid>`
```json
{
  "run_id": "run_a1b2c3d4e5f6",
  "status": "queued",
  "poll_url": "/runs/run_a1b2c3d4e5f6"
}
```

### 4.2 Valid Ingestion (Cache Hit — Requirement D7)
* **Status**: `200 OK`
* **Headers**: `X-Cache: HIT`, `X-Correlation-ID: <uuid>`
```json
{
  "run_id": "run_a1b2c3d4e5f6",
  "status": "completed",
  "poll_url": "/runs/run_a1b2c3d4e5f6",
  "cached": true
}
```

### 4.3 Validation Rejection (Quarantined — Requirements F2, D1)
* **Status**: `422 Unprocessable Entity`
* **Headers**: `X-Correlation-ID: <uuid>`
```json
{
  "quarantine_id": "q_9f8e7d6c5b4a",
  "errors": [
    {
      "field": "garage_name",
      "message": "required when cashless_requested is true"
    },
    {
      "field": "vehicle_registration",
      "message": "not a valid Indian registration number (e.g. KA-11-AB-1234)"
    }
  ]
}
```

### 4.4 Rate Limit Exceeded (Requirement D7)
* **Status**: `429 Too Many Requests`
* **Headers**: `Retry-After: 42`, `X-Correlation-ID: <uuid>`
```json
{
  "detail": "rate limit of 30/min exceeded"
}
```
