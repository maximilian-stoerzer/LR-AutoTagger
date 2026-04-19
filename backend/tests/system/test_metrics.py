"""System tests for /metrics — Prometheus exposition endpoint."""


def test_metrics_no_api_key_needed(client):
    """/metrics is unauth (scraped by Prometheus on the LAN, same as /health)."""
    resp = client.get("/metrics")
    assert resp.status_code == 200


def test_metrics_exposes_custom_lr_metrics(client):
    resp = client.get("/metrics")
    body = resp.text

    expected = [
        "lr_ollama_inference_duration_seconds",
        "lr_ollama_requests_total",
        "lr_batch_jobs_active",
        "lr_batch_chunks_active",
        "lr_batch_chunks_completed_total",
        "lr_batch_chunks_failed_total",
        "lr_pipeline_stage_duration_seconds",
        "lr_keywords_per_image",
        "lr_nominatim_requests_total",
        "lr_nominatim_duration_seconds",
    ]
    for name in expected:
        assert name in body, f"expected metric {name} missing from /metrics output"


def test_metrics_exposes_http_instrumentator(client):
    """prometheus-fastapi-instrumentator adds standard http_* metrics."""
    # Trigger at least one request that's tracked (health is excluded by default
    # path whitelist behaviour, so hit /metrics itself first, then /api/v1/health
    # and re-query).
    client.get("/api/v1/health")
    resp = client.get("/metrics")
    body = resp.text

    assert "http_requests_total" in body
    assert "http_request_duration_seconds" in body


def test_metrics_content_type(client):
    resp = client.get("/metrics")
    # Prometheus text exposition format — either the classic text/plain or
    # the newer openmetrics variant are both acceptable.
    ctype = resp.headers.get("content-type", "")
    assert "text/plain" in ctype or "openmetrics-text" in ctype
