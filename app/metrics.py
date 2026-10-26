"""Prometheus metrics definition for the Claim Intake & Triage service (D5, A6)."""

from __future__ import annotations

import time
from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST
from fastapi import Response

# HTTP metrics
HTTP_REQUESTS_TOTAL = Counter(
    "claims_http_requests_total",
    "Total HTTP requests handled by the API",
    ["method", "endpoint", "status_code"],
)
HTTP_REQUEST_DURATION_SECONDS = Histogram(
    "claims_http_request_duration_seconds",
    "HTTP request latency in seconds",
    ["endpoint"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)

# Ingestion & Cache metrics
CLAIMS_SUBMITTED_TOTAL = Counter(
    "claims_submitted_total",
    "Total FNOL claims submitted at the ingestion boundary",
    ["channel", "status"],  # status: queued, quarantined, cached
)
RUN_CACHE_HITS_TOTAL = Counter(
    "claims_cache_hits_total",
    "Total claim submissions resolved via the run cache (D7)",
)
RUN_CACHE_MISSES_TOTAL = Counter(
    "claims_cache_misses_total",
    "Total claim submissions requiring execution (cache miss)",
)
RATE_LIMIT_EXCEEDED_TOTAL = Counter(
    "claims_rate_limit_exceeded_total",
    "Total requests rejected by per-client rate limiting (D7)",
    ["client"],
)

# Agent performance & execution metrics (A6)
AGENT_STEP_DURATION_SECONDS = Histogram(
    "agent_step_duration_seconds",
    "Latency of individual agent steps and tool calls",
    ["agent", "action"],
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0, 20.0),
)
AGENT_STEP_COST_USD = Counter(
    "agent_step_cost_usd_total",
    "Attributed cost of agent executions in USD (L5)",
    ["agent"],
)
CLAIM_RUN_DURATION_SECONDS = Histogram(
    "claim_run_duration_seconds",
    "End-to-end duration of a claim triage run from start to finish",
    ["outcome"],  # outcome: completed, escalated, failed
    buckets=(0.5, 1.0, 2.0, 5.0, 10.0, 15.0, 30.0, 60.0, 120.0),
)


def metrics_endpoint() -> Response:
    """FastAPI endpoint handler returning Prometheus text exposition format."""
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
