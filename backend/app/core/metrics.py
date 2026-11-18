"""Prometheus metrics. Exposed at /metrics (API) and pushed via the worker's own registry."""

from prometheus_client import Counter, Gauge, Histogram

HTTP_REQUESTS = Counter(
    "http_requests_total", "HTTP requests", ["method", "route", "status"]
)
HTTP_LATENCY = Histogram(
    "http_request_duration_seconds", "HTTP latency", ["method", "route"],
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5),
)
MATCH_LATENCY = Histogram(
    "matching_duration_seconds", "Candidate generation + scoring", ["direction"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1),
)
MATCHES_CREATED = Counter("matches_created_total", "Matches persisted", ["status"])
NOTIFICATIONS_SENT = Counter("notifications_sent_total", "Notifications", ["kind", "channel"])
LLM_CALLS = Counter("llm_calls_total", "LLM calls", ["purpose", "outcome"])
LLM_LATENCY = Histogram("llm_call_duration_seconds", "LLM latency", ["purpose"])
OUTBOX_LAG = Gauge("outbox_unpublished_events", "Outbox events waiting to be relayed")
JOBS = Counter("worker_jobs_total", "Worker jobs", ["task", "outcome"])
