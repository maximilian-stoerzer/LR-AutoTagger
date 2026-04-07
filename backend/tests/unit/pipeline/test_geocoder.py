"""Unit tests for app.pipeline.geocoder — U-GEO-01 to U-GEO-10."""

import time
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.pipeline.geocoder import Geocoder


@pytest.fixture
def geocoder():
    return Geocoder()


def _mock_nominatim_response(data: dict, status: int = 200):
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = status
    mock_resp.json.return_value = data
    mock_resp.raise_for_status = MagicMock()
    if status >= 400:
        mock_resp.raise_for_status.side_effect = httpx.HTTPStatusError("error", request=MagicMock(), response=mock_resp)
    return mock_resp


def _patch_httpx(mock_resp):
    """Patch httpx.AsyncClient to return mock_resp on GET."""
    patcher = patch("app.pipeline.geocoder.httpx.AsyncClient")
    MockClient = patcher.start()
    instance = AsyncMock()
    instance.get.return_value = mock_resp
    instance.__aenter__ = AsyncMock(return_value=instance)
    instance.__aexit__ = AsyncMock(return_value=False)
    MockClient.return_value = instance
    return patcher, instance


def _reset_throttle():
    import app.pipeline.geocoder as mod

    mod._last_request_time = 0.0


# U-GEO-01
@pytest.mark.asyncio
async def test_full_address_heidelberg(geocoder, mock_nominatim_heidelberg):
    _reset_throttle()
    resp = _mock_nominatim_response(mock_nominatim_heidelberg)
    patcher, _ = _patch_httpx(resp)
    try:
        result = await geocoder.reverse(49.4094, 8.6942)
        assert result is not None
        assert result["city"] == "Heidelberg"
        assert result["state"] == "Baden-Wuerttemberg"
        assert result["country"] == "Deutschland"
        assert "Heidelberg" in result["geo_keywords"]
        assert "Deutschland" in result["geo_keywords"]
        assert result["location_name"] == "Heidelberg, Baden-Wuerttemberg, Deutschland"
    finally:
        patcher.stop()


# U-GEO-02
@pytest.mark.asyncio
async def test_only_country_available(geocoder):
    _reset_throttle()
    data = {
        "address": {"country": "Atlantik"},
        "display_name": "Atlantik",
    }
    resp = _mock_nominatim_response(data)
    patcher, _ = _patch_httpx(resp)
    try:
        result = await geocoder.reverse(0.0, -30.0)
        assert result is not None
        assert result["geo_keywords"] == ["Atlantik"]
    finally:
        patcher.stop()


# U-GEO-03
@pytest.mark.asyncio
async def test_nominatim_http_error(geocoder):
    _reset_throttle()
    resp = _mock_nominatim_response({}, status=500)
    patcher, instance = _patch_httpx(resp)
    instance.get.side_effect = httpx.HTTPStatusError("500", request=MagicMock(), response=resp)
    try:
        result = await geocoder.reverse(49.0, 8.0)
        assert result is None
    finally:
        patcher.stop()


# U-GEO-04
@pytest.mark.asyncio
async def test_nominatim_timeout(geocoder):
    _reset_throttle()
    patcher = patch("app.pipeline.geocoder.httpx.AsyncClient")
    MockClient = patcher.start()
    instance = AsyncMock()
    instance.get.side_effect = httpx.TimeoutException("timeout")
    instance.__aenter__ = AsyncMock(return_value=instance)
    instance.__aexit__ = AsyncMock(return_value=False)
    MockClient.return_value = instance
    try:
        result = await geocoder.reverse(49.0, 8.0)
        assert result is None
    finally:
        patcher.stop()


# U-GEO-05
@pytest.mark.asyncio
async def test_nominatim_error_field(geocoder):
    _reset_throttle()
    data = {"error": "Unable to geocode"}
    resp = _mock_nominatim_response(data)
    patcher, _ = _patch_httpx(resp)
    try:
        result = await geocoder.reverse(49.0, 8.0)
        assert result is None
    finally:
        patcher.stop()


# U-GEO-06
@pytest.mark.asyncio
async def test_null_island_gps(geocoder, mock_nominatim_heidelberg):
    _reset_throttle()
    resp = _mock_nominatim_response(mock_nominatim_heidelberg)
    patcher, _ = _patch_httpx(resp)
    try:
        result = await geocoder.reverse(0.0, 0.0)
        # Should return something (mocked), not crash
        assert result is not None
    finally:
        patcher.stop()


# U-GEO-07
@pytest.mark.asyncio
async def test_extreme_coordinates(geocoder, mock_nominatim_heidelberg):
    _reset_throttle()
    resp = _mock_nominatim_response(mock_nominatim_heidelberg)
    patcher, _ = _patch_httpx(resp)
    try:
        result = await geocoder.reverse(90.0, 180.0)
        assert result is not None
    finally:
        patcher.stop()


# U-GEO-08
@pytest.mark.asyncio
async def test_throttle_enforces_1s_delay(geocoder, mock_nominatim_heidelberg):
    _reset_throttle()
    resp = _mock_nominatim_response(mock_nominatim_heidelberg)
    patcher, _ = _patch_httpx(resp)
    try:
        start = time.monotonic()
        await geocoder.reverse(49.0, 8.0)
        await geocoder.reverse(49.0, 8.0)
        elapsed = time.monotonic() - start
        assert elapsed >= 0.9  # second call should wait ~1s
    finally:
        patcher.stop()


# U-GEO-09
@pytest.mark.asyncio
async def test_suburb_city_state_all_in_keywords(geocoder, mock_nominatim_heidelberg):
    _reset_throttle()
    resp = _mock_nominatim_response(mock_nominatim_heidelberg)
    patcher, _ = _patch_httpx(resp)
    try:
        result = await geocoder.reverse(49.4094, 8.6942)
        kw = result["geo_keywords"]
        assert "Altstadt" in kw
        assert "Heidelberg" in kw
        assert "Baden-Wuerttemberg" in kw
    finally:
        patcher.stop()


# U-GEO-10
@pytest.mark.asyncio
async def test_no_address_field_uses_display_name(geocoder):
    _reset_throttle()
    data = {"display_name": "Somewhere, Earth"}
    resp = _mock_nominatim_response(data)
    patcher, _ = _patch_httpx(resp)
    try:
        result = await geocoder.reverse(10.0, 20.0)
        assert result is not None
        assert result["location_name"] == "Somewhere, Earth"
    finally:
        patcher.stop()
