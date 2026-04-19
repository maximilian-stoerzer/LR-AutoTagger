"""Prometheus metrics for LR-AutoTag.

Exposes custom business metrics via prometheus_client. All metric names are
prefixed with ``lr_`` to keep them distinct in a shared Prometheus instance.

HTTP-level metrics (requests, latencies, status codes) are emitted by the
prometheus-fastapi-instrumentator wired into main.py; nothing in this module
duplicates them.
"""
from __future__ import annotations

import time
from contextlib import asynccontextmanager, contextmanager

from prometheus_client import Counter, Gauge, Histogram

# ---------------------------------------------------------------------------
# Ollama vision inference
# ---------------------------------------------------------------------------

ollama_inference_duration = Histogram(
    "lr_ollama_inference_duration_seconds",
    "Wall-clock time of a single /api/generate call to Ollama, by model.",
    labelnames=("model",),
    # Buckets tuned for LLaVA/Gemma on a P40: 1s to 5min
    buckets=(1, 2, 5, 10, 15, 25, 40, 60, 90, 120, 180, 300),
)

ollama_requests_total = Counter(
    "lr_ollama_requests_total",
    "Total Ollama vision inference calls, labelled by model and outcome.",
    labelnames=("model", "status"),  # status: success | error | timeout
)

# ---------------------------------------------------------------------------
# Batch job / chunk state
# ---------------------------------------------------------------------------

batch_jobs_active = Gauge(
    "lr_batch_jobs_active",
    "Number of batch jobs currently in each state.",
    labelnames=("state",),  # pending | running | paused | done | cancelled
)

batch_chunks_active = Gauge(
    "lr_batch_chunks_active",
    "Number of chunks currently in each state across all jobs.",
    labelnames=("state",),  # pending | processing | done | failed
)

batch_chunks_completed_total = Counter(
    "lr_batch_chunks_completed_total",
    "Chunks that transitioned to state=done.",
)

batch_chunks_failed_total = Counter(
    "lr_batch_chunks_failed_total",
    "Chunks that transitioned to state=failed (final failure after retries).",
)

# ---------------------------------------------------------------------------
# Pipeline stages
# ---------------------------------------------------------------------------

pipeline_stage_duration = Histogram(
    "lr_pipeline_stage_duration_seconds",
    "Wall-clock time per pipeline stage.",
    labelnames=("stage",),  # preprocess | geocode | vision | combine
    buckets=(0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10, 25, 60, 120),
)

keywords_per_image = Histogram(
    "lr_keywords_per_image",
    "Final number of keywords per image returned to the plugin.",
    buckets=(0, 3, 6, 10, 15, 20, 25, 30),
)

# ---------------------------------------------------------------------------
# Nominatim reverse geocoding
# ---------------------------------------------------------------------------

nominatim_requests_total = Counter(
    "lr_nominatim_requests_total",
    "Total Nominatim reverse-geocoding requests, by outcome.",
    labelnames=("status",),  # success | error (http / parse / empty)
)

nominatim_duration = Histogram(
    "lr_nominatim_duration_seconds",
    "Wall-clock time of a Nominatim reverse request, including rate-limit wait.",
    buckets=(0.1, 0.25, 0.5, 1, 2, 5, 10),
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@contextmanager
def track_stage(stage: str):
    """Context manager that records wall-clock time into lr_pipeline_stage_duration."""
    t0 = time.monotonic()
    try:
        yield
    finally:
        pipeline_stage_duration.labels(stage=stage).observe(time.monotonic() - t0)


@asynccontextmanager
async def track_ollama(model: str):
    """Async context manager for Ollama inference.

    Records duration and increments the requests counter with the right status.
    The caller decides whether an exception marks error or timeout by raising
    the appropriate type (httpx.ReadTimeout → timeout, anything else → error).
    """
    import httpx

    t0 = time.monotonic()
    status = "success"
    try:
        yield
    except httpx.TimeoutException:
        status = "timeout"
        raise
    except Exception:
        status = "error"
        raise
    finally:
        ollama_inference_duration.labels(model=model).observe(time.monotonic() - t0)
        ollama_requests_total.labels(model=model, status=status).inc()


async def refresh_batch_gauges(repo) -> None:
    """Refresh all batch-related gauges from the database.

    Called periodically (every scrape interval) so the gauges reflect actual
    state — not just deltas applied by the request handlers.
    """
    job_counts = await repo.count_batch_jobs_by_state()
    for state in ("pending", "running", "paused", "done", "cancelled"):
        batch_jobs_active.labels(state=state).set(job_counts.get(state, 0))

    chunk_counts = await repo.count_chunks_by_state()
    for state in ("pending", "processing", "done", "failed"):
        batch_chunks_active.labels(state=state).set(chunk_counts.get(state, 0))
