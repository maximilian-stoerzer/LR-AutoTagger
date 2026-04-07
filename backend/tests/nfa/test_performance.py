"""NFA tests: Performance — P-THR-01 to P-THR-07, P-MEM-01."""

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytestmark = pytest.mark.performance


# P-THR-02
def test_health_latency(client, auth_headers):
    with patch("app.api.routes.OllamaClient") as MockOllama:
        instance = AsyncMock()
        instance.health = AsyncMock(return_value=True)
        MockOllama.return_value = instance

        start = time.monotonic()
        resp = client.get("/api/v1/health")
        elapsed = time.monotonic() - start

    assert resp.status_code == 200
    assert elapsed < 0.2, f"Health endpoint took {elapsed:.3f}s, expected <200ms"


# P-THR-04
def test_batch_status_latency(client, auth_headers):
    start = time.monotonic()
    resp = client.get("/api/v1/batch/status", headers=auth_headers)
    elapsed = time.monotonic() - start

    assert resp.status_code == 200
    assert elapsed < 0.1, f"Batch status took {elapsed:.3f}s, expected <100ms"


# P-THR-05
@pytest.mark.asyncio
async def test_ollama_semaphore_limits_concurrency(sample_jpeg):
    """Verify Ollama semaphore enforces OLLAMA_MAX_CONCURRENT."""
    import app.pipeline.ollama_client as mod

    mod._semaphore = None

    concurrent = 0
    max_concurrent = 0

    async def slow_post(*args, **kwargs):
        nonlocal concurrent, max_concurrent
        concurrent += 1
        max_concurrent = max(max_concurrent, concurrent)
        await asyncio.sleep(0.05)
        concurrent -= 1
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {"response": '["test"]'}
        resp.raise_for_status = MagicMock()
        return resp

    with patch("app.pipeline.ollama_client.httpx.AsyncClient") as MockClient:
        instance = AsyncMock()
        instance.post = slow_post
        instance.__aenter__ = AsyncMock(return_value=instance)
        instance.__aexit__ = AsyncMock(return_value=False)
        MockClient.return_value = instance

        from app.pipeline.ollama_client import OllamaClient

        client = OllamaClient()
        tasks = [client.analyze_image(sample_jpeg) for _ in range(10)]
        await asyncio.gather(*tasks)

    from app.config import settings

    assert max_concurrent <= settings.ollama_max_concurrent


# P-THR-06
@pytest.mark.asyncio
async def test_geocoder_throttle_rate():
    """Verify Nominatim throttle enforces max 1 req/sec."""
    import app.pipeline.geocoder as mod

    mod._last_request_time = 0.0

    call_times = []

    with patch("app.pipeline.geocoder.httpx.AsyncClient") as MockClient:
        instance = AsyncMock()
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {"address": {"country": "Test"}, "display_name": "Test"}
        resp.raise_for_status = MagicMock()
        instance.get.return_value = resp
        instance.__aenter__ = AsyncMock(return_value=instance)
        instance.__aexit__ = AsyncMock(return_value=False)
        MockClient.return_value = instance

        from app.pipeline.geocoder import Geocoder

        geo = Geocoder()

        start = time.monotonic()
        for _ in range(3):
            await geo.reverse(49.0, 8.0)
            call_times.append(time.monotonic() - start)

    # 3 calls should take at least 2 seconds (2 throttle waits)
    total = call_times[-1]
    assert total >= 1.8, f"3 geocoder calls took only {total:.2f}s, expected >=2s"


# P-MEM-01
def test_image_processing_no_memory_leak(sample_jpeg):
    """Process many images and verify stable memory usage."""
    import tracemalloc

    from app.pipeline.image_processor import resize_for_analysis

    tracemalloc.start()

    # Warmup
    for _ in range(10):
        resize_for_analysis(sample_jpeg)

    snapshot1 = tracemalloc.take_snapshot()

    for _ in range(100):
        resize_for_analysis(sample_jpeg)

    snapshot2 = tracemalloc.take_snapshot()
    tracemalloc.stop()

    # Compare: allow some growth but not linear with iterations
    stats1 = sum(s.size for s in snapshot1.statistics("filename"))
    stats2 = sum(s.size for s in snapshot2.statistics("filename"))

    growth = stats2 - stats1
    # Allow up to 5MB growth (images are small test images)
    assert growth < 5 * 1024 * 1024, f"Memory grew by {growth / 1024 / 1024:.1f}MB"
