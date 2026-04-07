"""Unit tests for app.pipeline.keyword_pipeline — U-KWP-01 to U-KWP-10."""

from unittest.mock import AsyncMock, patch

import pytest

from app.pipeline.keyword_pipeline import KeywordPipeline


@pytest.fixture
def mock_repo():
    repo = AsyncMock()
    repo.save_image_keywords = AsyncMock()
    return repo


@pytest.fixture
def pipeline(mock_repo):
    return KeywordPipeline(mock_repo)


def _patch_pipeline(vision_keywords, geo_result=None):
    """Patch Ollama and Geocoder for pipeline tests."""
    patches = []

    p1 = patch("app.pipeline.keyword_pipeline.resize_for_analysis", return_value=b"resized")
    patches.append(p1)

    p2 = patch.object(KeywordPipeline, "__init__", lambda self, repo: None)
    # We won't use this — instead patch the instances directly
    # Let's just patch the external calls

    return patches


# U-KWP-01
@pytest.mark.asyncio
async def test_image_with_gps(pipeline, mock_repo, sample_jpeg):
    with patch("app.pipeline.keyword_pipeline.resize_for_analysis", return_value=b"resized"):
        pipeline.ollama = AsyncMock()
        pipeline.ollama.analyze_image = AsyncMock(return_value=["Bruecke", "Fluss"])
        pipeline.geocoder = AsyncMock()
        pipeline.geocoder.reverse = AsyncMock(
            return_value={
                "geo_keywords": ["Heidelberg", "Deutschland"],
                "location_name": "Heidelberg, Deutschland",
            }
        )
        pipeline.repo = mock_repo

        result = await pipeline.analyze_single(sample_jpeg, gps_lat=49.4, gps_lon=8.7, image_id="img1")

        assert "Heidelberg" in result["keywords"]
        assert "Bruecke" in result["keywords"]
        assert result["location_name"] == "Heidelberg, Deutschland"


# U-KWP-02
@pytest.mark.asyncio
async def test_image_without_gps(pipeline, mock_repo, sample_jpeg):
    with patch("app.pipeline.keyword_pipeline.resize_for_analysis", return_value=b"resized"):
        pipeline.ollama = AsyncMock()
        pipeline.ollama.analyze_image = AsyncMock(return_value=["Bruecke", "Fluss"])
        pipeline.geocoder = AsyncMock()
        pipeline.repo = mock_repo

        result = await pipeline.analyze_single(sample_jpeg, gps_lat=None, gps_lon=None)

        assert result["keywords"] == ["Bruecke", "Fluss"]
        assert result["geo_keywords"] == []
        pipeline.geocoder.reverse.assert_not_called()


# U-KWP-03
@pytest.mark.asyncio
async def test_duplicate_between_vision_and_geo(pipeline, mock_repo, sample_jpeg):
    with patch("app.pipeline.keyword_pipeline.resize_for_analysis", return_value=b"resized"):
        pipeline.ollama = AsyncMock()
        pipeline.ollama.analyze_image = AsyncMock(return_value=["Berlin", "Fluss"])
        pipeline.geocoder = AsyncMock()
        pipeline.geocoder.reverse = AsyncMock(
            return_value={
                "geo_keywords": ["Berlin", "Deutschland"],
                "location_name": "Berlin",
            }
        )
        pipeline.repo = mock_repo

        result = await pipeline.analyze_single(sample_jpeg, gps_lat=52.5, gps_lon=13.4)

        assert result["keywords"].count("Berlin") == 1


# U-KWP-04
@pytest.mark.asyncio
async def test_case_insensitive_dedup(pipeline, mock_repo, sample_jpeg):
    with patch("app.pipeline.keyword_pipeline.resize_for_analysis", return_value=b"resized"):
        pipeline.ollama = AsyncMock()
        pipeline.ollama.analyze_image = AsyncMock(return_value=["berlin", "Fluss"])
        pipeline.geocoder = AsyncMock()
        pipeline.geocoder.reverse = AsyncMock(
            return_value={
                "geo_keywords": ["Berlin", "Deutschland"],
                "location_name": "Berlin",
            }
        )
        pipeline.repo = mock_repo

        result = await pipeline.analyze_single(sample_jpeg, gps_lat=52.5, gps_lon=13.4)

        berlin_count = sum(1 for k in result["keywords"] if k.lower() == "berlin")
        assert berlin_count == 1


# U-KWP-05
@pytest.mark.asyncio
async def test_combined_keywords_capped_at_25(pipeline, mock_repo, sample_jpeg):
    with patch("app.pipeline.keyword_pipeline.resize_for_analysis", return_value=b"resized"):
        pipeline.ollama = AsyncMock()
        pipeline.ollama.analyze_image = AsyncMock(return_value=[f"vision_{i}" for i in range(20)])
        pipeline.geocoder = AsyncMock()
        pipeline.geocoder.reverse = AsyncMock(
            return_value={
                "geo_keywords": [f"geo_{i}" for i in range(20)],
                "location_name": "Test",
            }
        )
        pipeline.repo = mock_repo

        result = await pipeline.analyze_single(sample_jpeg, gps_lat=1.0, gps_lon=1.0)

        assert len(result["keywords"]) <= 25


# U-KWP-06
@pytest.mark.asyncio
async def test_geo_keywords_come_first(pipeline, mock_repo, sample_jpeg):
    with patch("app.pipeline.keyword_pipeline.resize_for_analysis", return_value=b"resized"):
        pipeline.ollama = AsyncMock()
        pipeline.ollama.analyze_image = AsyncMock(return_value=["Bruecke"])
        pipeline.geocoder = AsyncMock()
        pipeline.geocoder.reverse = AsyncMock(
            return_value={
                "geo_keywords": ["Heidelberg"],
                "location_name": "Heidelberg",
            }
        )
        pipeline.repo = mock_repo

        result = await pipeline.analyze_single(sample_jpeg, gps_lat=49.4, gps_lon=8.7)

        assert result["keywords"][0] == "Heidelberg"
        assert result["keywords"][1] == "Bruecke"


# U-KWP-07
@pytest.mark.asyncio
async def test_ollama_error_propagates(pipeline, mock_repo, sample_jpeg):
    with patch("app.pipeline.keyword_pipeline.resize_for_analysis", return_value=b"resized"):
        pipeline.ollama = AsyncMock()
        pipeline.ollama.analyze_image = AsyncMock(side_effect=RuntimeError("Ollama down"))
        pipeline.geocoder = AsyncMock()
        pipeline.repo = mock_repo

        with pytest.raises(RuntimeError, match="Ollama down"):
            await pipeline.analyze_single(sample_jpeg, gps_lat=None, gps_lon=None)


# U-KWP-08
@pytest.mark.asyncio
async def test_geocoding_failure_still_returns_vision(pipeline, mock_repo, sample_jpeg):
    with patch("app.pipeline.keyword_pipeline.resize_for_analysis", return_value=b"resized"):
        pipeline.ollama = AsyncMock()
        pipeline.ollama.analyze_image = AsyncMock(return_value=["Bruecke", "Fluss"])
        pipeline.geocoder = AsyncMock()
        pipeline.geocoder.reverse = AsyncMock(return_value=None)
        pipeline.repo = mock_repo

        result = await pipeline.analyze_single(sample_jpeg, gps_lat=49.4, gps_lon=8.7)

        assert result["keywords"] == ["Bruecke", "Fluss"]
        assert result["geo_keywords"] == []


# U-KWP-09
@pytest.mark.asyncio
async def test_result_saved_when_image_id_given(pipeline, mock_repo, sample_jpeg):
    with patch("app.pipeline.keyword_pipeline.resize_for_analysis", return_value=b"resized"):
        pipeline.ollama = AsyncMock()
        pipeline.ollama.analyze_image = AsyncMock(return_value=["Bruecke"])
        pipeline.geocoder = AsyncMock()
        pipeline.repo = mock_repo

        await pipeline.analyze_single(sample_jpeg, image_id="img42")

        mock_repo.save_image_keywords.assert_called_once()
        call_kwargs = mock_repo.save_image_keywords.call_args
        assert call_kwargs[1]["image_id"] == "img42" or call_kwargs[0][0] == "img42"


# U-KWP-10
@pytest.mark.asyncio
async def test_no_save_without_image_id(pipeline, mock_repo, sample_jpeg):
    with patch("app.pipeline.keyword_pipeline.resize_for_analysis", return_value=b"resized"):
        pipeline.ollama = AsyncMock()
        pipeline.ollama.analyze_image = AsyncMock(return_value=["Bruecke"])
        pipeline.geocoder = AsyncMock()
        pipeline.repo = mock_repo

        await pipeline.analyze_single(sample_jpeg, image_id=None)

        mock_repo.save_image_keywords.assert_not_called()
