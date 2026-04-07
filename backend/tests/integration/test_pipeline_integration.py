"""Integration tests for KeywordPipeline with real DB — I-PIP-01 to I-PIP-04."""

from unittest.mock import AsyncMock, patch

import pytest

from app.pipeline.keyword_pipeline import KeywordPipeline

pytestmark = pytest.mark.integration


def _make_pipeline(repo) -> KeywordPipeline:
    p = KeywordPipeline(repo)
    p.ollama = AsyncMock()
    p.ollama.analyze_image = AsyncMock(return_value=["Bruecke", "Fluss"])
    p.geocoder = AsyncMock()
    p.geocoder.reverse = AsyncMock(return_value={
        "geo_keywords": ["Heidelberg", "Deutschland"],
        "location_name": "Heidelberg, Deutschland",
    })
    return p


# I-PIP-01
@pytest.mark.asyncio
async def test_analyze_single_saves_to_db(repo, sample_jpeg):
    pipeline = _make_pipeline(repo)

    with patch("app.pipeline.keyword_pipeline.resize_for_analysis", return_value=b"resized"):
        await pipeline.analyze_single(sample_jpeg, gps_lat=49.4, gps_lon=8.7, image_id="pip_test_1")

    result = await repo.get_image_keywords("pip_test_1")
    assert result is not None
    assert "Bruecke" in result["keywords"]
    assert "Heidelberg" in result["keywords"]


# I-PIP-02
@pytest.mark.asyncio
async def test_upsert_overwrites_existing(repo, sample_jpeg):
    pipeline = _make_pipeline(repo)

    with patch("app.pipeline.keyword_pipeline.resize_for_analysis", return_value=b"resized"):
        await pipeline.analyze_single(sample_jpeg, image_id="pip_test_2")

    # Change vision keywords
    pipeline.ollama.analyze_image = AsyncMock(return_value=["Berg", "Schnee"])

    with patch("app.pipeline.keyword_pipeline.resize_for_analysis", return_value=b"resized"):
        await pipeline.analyze_single(sample_jpeg, image_id="pip_test_2")

    result = await repo.get_image_keywords("pip_test_2")
    assert "Berg" in result["keywords"]
    assert "Bruecke" not in result["keywords"]


# I-PIP-03
@pytest.mark.asyncio
async def test_pipeline_with_gps(repo, sample_jpeg):
    pipeline = _make_pipeline(repo)

    with patch("app.pipeline.keyword_pipeline.resize_for_analysis", return_value=b"resized"):
        result = await pipeline.analyze_single(sample_jpeg, gps_lat=49.4, gps_lon=8.7, image_id="pip_test_3")

    assert "Heidelberg" in result["keywords"]
    assert result["location_name"] == "Heidelberg, Deutschland"


# I-PIP-04
@pytest.mark.asyncio
async def test_pipeline_without_gps(repo, sample_jpeg):
    pipeline = _make_pipeline(repo)
    pipeline.geocoder.reverse = AsyncMock(return_value=None)

    with patch("app.pipeline.keyword_pipeline.resize_for_analysis", return_value=b"resized"):
        result = await pipeline.analyze_single(sample_jpeg, image_id="pip_test_4")

    assert result["geo_keywords"] == []
    assert "Bruecke" in result["keywords"]
