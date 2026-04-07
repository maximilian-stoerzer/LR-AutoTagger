"""Unit tests for app.pipeline.ollama_client — U-OLL-01 to U-OLL-15."""

import asyncio
from unittest.mock import AsyncMock, patch, MagicMock

import httpx
import pytest

from app.pipeline.ollama_client import OllamaClient


# ---------------------------------------------------------------------------
# Parse-logic tests (_parse_keywords is deterministic, no mocks needed)
# ---------------------------------------------------------------------------

@pytest.fixture
def client():
    return OllamaClient()


# U-OLL-01
def test_parse_valid_json_array(client):
    result = client._parse_keywords('["Bruecke", "Fluss"]')
    assert result == ["Bruecke", "Fluss"]


# U-OLL-02
def test_parse_json_in_markdown_codeblock(client):
    raw = '```json\n["Bruecke", "Fluss"]\n```'
    result = client._parse_keywords(raw)
    assert result == ["Bruecke", "Fluss"]


# U-OLL-03
def test_parse_more_than_25_keywords_truncated(client):
    keywords = [f"keyword_{i}" for i in range(30)]
    import json
    raw = json.dumps(keywords)
    result = client._parse_keywords(raw)
    assert len(result) == 25


# U-OLL-04
def test_parse_empty_array(client):
    result = client._parse_keywords("[]")
    assert result == []


# U-OLL-05
def test_parse_freetext_fallback(client):
    result = client._parse_keywords("Bruecke, Fluss, Berg")
    assert "Bruecke" in result
    assert "Fluss" in result
    assert "Berg" in result


# U-OLL-06
def test_parse_empty_string(client):
    result = client._parse_keywords("")
    assert result == []


# U-OLL-07
def test_parse_mixed_types_in_array(client):
    result = client._parse_keywords('["Bruecke", 42, null]')
    assert "Bruecke" in result
    assert "42" in result
    # null → "None" string, should be filtered or present
    assert len(result) >= 2


# U-OLL-14
def test_parse_keywords_with_whitespace(client):
    result = client._parse_keywords('[" Bruecke ", " "]')
    assert result == ["Bruecke"]


# U-OLL-15
def test_parse_json_array_embedded_in_text(client):
    raw = 'Hier sind die Keywords: ["Baum", "Wiese"] und mehr Text'
    result = client._parse_keywords(raw)
    assert result == ["Baum", "Wiese"]


# ---------------------------------------------------------------------------
# HTTP interaction tests (mocked)
# ---------------------------------------------------------------------------


def _mock_ollama_response(keywords_json: str, status: int = 200):
    """Build a mock httpx.Response for Ollama /api/generate."""
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = status
    mock_resp.json.return_value = {"response": keywords_json}
    mock_resp.raise_for_status = MagicMock()
    if status >= 400:
        mock_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "error", request=MagicMock(), response=mock_resp
        )
    return mock_resp


@pytest.mark.asyncio
async def test_analyze_image_happy_path(client, sample_jpeg):
    """U-OLL-01 via full analyze_image path."""
    mock_resp = _mock_ollama_response('["Bruecke", "Fluss"]')

    with patch("app.pipeline.ollama_client.httpx.AsyncClient") as MockClient:
        instance = AsyncMock()
        instance.post.return_value = mock_resp
        instance.__aenter__ = AsyncMock(return_value=instance)
        instance.__aexit__ = AsyncMock(return_value=False)
        MockClient.return_value = instance

        # Reset semaphore for test isolation
        import app.pipeline.ollama_client as mod
        mod._semaphore = None

        result = await client.analyze_image(sample_jpeg)
        assert result == ["Bruecke", "Fluss"]


# U-OLL-08
@pytest.mark.asyncio
async def test_analyze_image_timeout(client, sample_jpeg):
    with patch("app.pipeline.ollama_client.httpx.AsyncClient") as MockClient:
        instance = AsyncMock()
        instance.post.side_effect = httpx.TimeoutException("timeout")
        instance.__aenter__ = AsyncMock(return_value=instance)
        instance.__aexit__ = AsyncMock(return_value=False)
        MockClient.return_value = instance

        import app.pipeline.ollama_client as mod
        mod._semaphore = None

        with pytest.raises(httpx.TimeoutException):
            await client.analyze_image(sample_jpeg)


# U-OLL-09
@pytest.mark.asyncio
async def test_analyze_image_http_500(client, sample_jpeg):
    mock_resp = _mock_ollama_response("", status=500)

    with patch("app.pipeline.ollama_client.httpx.AsyncClient") as MockClient:
        instance = AsyncMock()
        instance.post.return_value = mock_resp
        instance.__aenter__ = AsyncMock(return_value=instance)
        instance.__aexit__ = AsyncMock(return_value=False)
        MockClient.return_value = instance

        import app.pipeline.ollama_client as mod
        mod._semaphore = None

        with pytest.raises(httpx.HTTPStatusError):
            await client.analyze_image(sample_jpeg)


# U-OLL-10
@pytest.mark.asyncio
async def test_analyze_image_connection_error(client, sample_jpeg):
    with patch("app.pipeline.ollama_client.httpx.AsyncClient") as MockClient:
        instance = AsyncMock()
        instance.post.side_effect = httpx.ConnectError("refused")
        instance.__aenter__ = AsyncMock(return_value=instance)
        instance.__aexit__ = AsyncMock(return_value=False)
        MockClient.return_value = instance

        import app.pipeline.ollama_client as mod
        mod._semaphore = None

        with pytest.raises(httpx.ConnectError):
            await client.analyze_image(sample_jpeg)


# U-OLL-11
@pytest.mark.asyncio
async def test_health_check_positive(client):
    mock_resp = MagicMock()
    mock_resp.status_code = 200

    with patch("app.pipeline.ollama_client.httpx.AsyncClient") as MockClient:
        instance = AsyncMock()
        instance.get.return_value = mock_resp
        instance.__aenter__ = AsyncMock(return_value=instance)
        instance.__aexit__ = AsyncMock(return_value=False)
        MockClient.return_value = instance

        assert await client.health() is True


# U-OLL-12
@pytest.mark.asyncio
async def test_health_check_negative(client):
    with patch("app.pipeline.ollama_client.httpx.AsyncClient") as MockClient:
        instance = AsyncMock()
        instance.get.side_effect = httpx.ConnectError("refused")
        instance.__aenter__ = AsyncMock(return_value=instance)
        instance.__aexit__ = AsyncMock(return_value=False)
        MockClient.return_value = instance

        assert await client.health() is False


# U-OLL-13
@pytest.mark.asyncio
async def test_semaphore_limits_concurrency(sample_jpeg):
    """Verify that at most OLLAMA_MAX_CONCURRENT requests run in parallel."""
    import app.pipeline.ollama_client as mod
    mod._semaphore = None

    concurrent_count = 0
    max_concurrent = 0

    async def slow_post(*args, **kwargs):
        nonlocal concurrent_count, max_concurrent
        concurrent_count += 1
        max_concurrent = max(max_concurrent, concurrent_count)
        await asyncio.sleep(0.1)
        concurrent_count -= 1
        return _mock_ollama_response('["test"]')

    with patch("app.pipeline.ollama_client.httpx.AsyncClient") as MockClient:
        instance = AsyncMock()
        instance.post = slow_post
        instance.__aenter__ = AsyncMock(return_value=instance)
        instance.__aexit__ = AsyncMock(return_value=False)
        MockClient.return_value = instance

        client = OllamaClient()
        tasks = [client.analyze_image(sample_jpeg) for _ in range(5)]
        await asyncio.gather(*tasks)

    assert max_concurrent <= 2  # OLLAMA_MAX_CONCURRENT default
