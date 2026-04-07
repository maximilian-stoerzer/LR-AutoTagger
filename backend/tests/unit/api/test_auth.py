"""Unit tests for app.api.auth — U-AUTH-01 to U-AUTH-05."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.api.auth import api_key_middleware


def _make_request(path: str, api_key: str | None = None):
    request = MagicMock()
    request.url.path = path
    if api_key is not None:
        request.headers.get.return_value = api_key
    else:
        request.headers.get.return_value = None
    return request


@pytest.fixture
def call_next():
    response = MagicMock()
    response.status_code = 200
    return AsyncMock(return_value=response)


# U-AUTH-01
@pytest.mark.asyncio
async def test_valid_api_key(call_next):
    from app.config import settings
    request = _make_request("/api/v1/analyze", api_key=settings.api_key)

    response = await api_key_middleware(request, call_next)

    call_next.assert_called_once_with(request)


# U-AUTH-02
@pytest.mark.asyncio
async def test_missing_api_key(call_next):
    request = _make_request("/api/v1/analyze", api_key=None)

    response = await api_key_middleware(request, call_next)

    assert response.status_code == 401
    call_next.assert_not_called()


# U-AUTH-03
@pytest.mark.asyncio
async def test_wrong_api_key(call_next):
    request = _make_request("/api/v1/analyze", api_key="wrong-key")

    response = await api_key_middleware(request, call_next)

    assert response.status_code == 401
    call_next.assert_not_called()


# U-AUTH-04
@pytest.mark.asyncio
async def test_empty_api_key(call_next):
    request = _make_request("/api/v1/analyze", api_key="")

    response = await api_key_middleware(request, call_next)

    assert response.status_code == 401
    call_next.assert_not_called()


# U-AUTH-05
@pytest.mark.asyncio
async def test_health_endpoint_exempt(call_next):
    request = _make_request("/api/v1/health", api_key=None)

    response = await api_key_middleware(request, call_next)

    call_next.assert_called_once_with(request)
