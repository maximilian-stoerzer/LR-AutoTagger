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
async def test_combined_keywords_capped_at_max(pipeline, mock_repo, sample_jpeg):
    from app.config import settings

    with patch("app.pipeline.keyword_pipeline.resize_for_analysis", return_value=b"resized"):
        pipeline.ollama = AsyncMock()
        pipeline.ollama.analyze_image = AsyncMock(return_value=[f"vision_{i}" for i in range(25)])
        pipeline.geocoder = AsyncMock()
        pipeline.geocoder.reverse = AsyncMock(
            return_value={
                "geo_keywords": [f"geo_{i}" for i in range(25)],
                "location_name": "Test",
            }
        )
        pipeline.repo = mock_repo

        result = await pipeline.analyze_single(sample_jpeg, gps_lat=1.0, gps_lon=1.0)

        assert len(result["keywords"]) <= settings.max_keywords


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


# ---------------------------------------------------------------------------
# U-KWP-11 to U-KWP-14: Cross-category Lichtsituation vetos
# ---------------------------------------------------------------------------


class TestConsistencyVetos:
    """Verify that contradictory keyword combinations are cleaned up."""

    async def _run(self, pipeline, mock_repo, sample_jpeg, vision_kw):
        """Run analyze_single with mocked vision keywords, return result."""
        with patch("app.pipeline.keyword_pipeline.resize_for_analysis", return_value=b"resized"):
            pipeline.ollama = AsyncMock()
            pipeline.ollama.analyze_image = AsyncMock(return_value=vision_kw)
            pipeline.geocoder = AsyncMock()
            result = await pipeline.analyze_single(sample_jpeg)
        return result

    # --- Cross-category: weather → light ---

    # U-KWP-11
    @pytest.mark.asyncio
    async def test_overcast_vetoes_hard_light(self, pipeline, mock_repo, sample_jpeg):
        """Bedeckt + Hartes Licht is physically impossible."""
        result = await self._run(pipeline, mock_repo, sample_jpeg, ["Bedeckt", "Hartes Licht", "Abend", "Friedlich"])
        assert "Hartes Licht" not in result["vision_keywords"]
        assert "Bedeckt" in result["vision_keywords"]

    # U-KWP-12
    @pytest.mark.asyncio
    async def test_fog_vetoes_directional_light(self, pipeline, mock_repo, sample_jpeg):
        """Nebel rules out directional light sources."""
        result = await self._run(pipeline, mock_repo, sample_jpeg, ["Nebel", "Gegenlicht", "Lichtstrahlen", "Mystisch"])
        assert "Gegenlicht" not in result["vision_keywords"]
        assert "Lichtstrahlen" not in result["vision_keywords"]
        assert "Nebel" in result["vision_keywords"]

    # U-KWP-13
    @pytest.mark.asyncio
    async def test_night_without_kunstlicht_vetoes_hard(self, pipeline, mock_repo, sample_jpeg):
        """Nacht without Kunstlicht can't have hard directional sunlight."""
        result = await self._run(pipeline, mock_repo, sample_jpeg, ["Nacht", "Hartes Licht", "Einsam"])
        assert "Hartes Licht" not in result["vision_keywords"]

    # U-KWP-14
    @pytest.mark.asyncio
    async def test_sunny_keeps_hard_light(self, pipeline, mock_repo, sample_jpeg):
        """Sonnig + Hartes Licht is perfectly valid — no veto."""
        result = await self._run(pipeline, mock_repo, sample_jpeg, ["Sonnig", "Hartes Licht", "Mittag"])
        assert "Hartes Licht" in result["vision_keywords"]

    # --- Intra-Lichtsituation: mutually exclusive pairs ---

    # U-KWP-15
    @pytest.mark.asyncio
    async def test_hard_soft_light_keeps_first(self, pipeline, mock_repo, sample_jpeg):
        """Hartes Licht + Weiches Licht — keep first, drop second."""
        result = await self._run(pipeline, mock_repo, sample_jpeg, ["Weiches Licht", "Hartes Licht", "Friedlich"])
        assert "Weiches Licht" in result["vision_keywords"]
        assert "Hartes Licht" not in result["vision_keywords"]

    # U-KWP-16
    @pytest.mark.asyncio
    async def test_hard_diffuse_light_keeps_first(self, pipeline, mock_repo, sample_jpeg):
        """Hartes Licht + Diffuses Licht — keep first, drop second."""
        result = await self._run(pipeline, mock_repo, sample_jpeg, ["Diffuses Licht", "Hartes Licht", "Bewoelkt"])
        assert "Diffuses Licht" in result["vision_keywords"]
        assert "Hartes Licht" not in result["vision_keywords"]

    # U-KWP-17
    @pytest.mark.asyncio
    async def test_highkey_lowkey_keeps_first(self, pipeline, mock_repo, sample_jpeg):
        """High-Key + Low-Key — mutually exclusive, keep first."""
        result = await self._run(pipeline, mock_repo, sample_jpeg, ["Low-Key", "High-Key", "Dramatisch"])
        assert "Low-Key" in result["vision_keywords"]
        assert "High-Key" not in result["vision_keywords"]

    # U-KWP-18
    @pytest.mark.asyncio
    async def test_silhouette_frontlicht_keeps_first(self, pipeline, mock_repo, sample_jpeg):
        """Silhouette + Frontlicht — silhouette needs backlight, not front."""
        result = await self._run(pipeline, mock_repo, sample_jpeg, ["Silhouette", "Frontlicht", "Dramatisch"])
        assert "Silhouette" in result["vision_keywords"]
        assert "Frontlicht" not in result["vision_keywords"]

    # U-KWP-19
    @pytest.mark.asyncio
    async def test_silhouette_highkey_keeps_first(self, pipeline, mock_repo, sample_jpeg):
        """Silhouette + High-Key — dark subject vs everything bright."""
        result = await self._run(pipeline, mock_repo, sample_jpeg, ["Silhouette", "High-Key", "Dramatisch"])
        assert "Silhouette" in result["vision_keywords"]
        assert "High-Key" not in result["vision_keywords"]

    # --- Intra-Wetter: mutually exclusive pairs ---

    # U-KWP-20
    @pytest.mark.asyncio
    async def test_sunny_overcast_keeps_first(self, pipeline, mock_repo, sample_jpeg):
        """Sonnig + Bedeckt — mutually exclusive, keep first."""
        result = await self._run(pipeline, mock_repo, sample_jpeg, ["Bedeckt", "Sonnig", "Friedlich"])
        assert "Bedeckt" in result["vision_keywords"]
        assert "Sonnig" not in result["vision_keywords"]

    # U-KWP-21
    @pytest.mark.asyncio
    async def test_sunny_fog_keeps_first(self, pipeline, mock_repo, sample_jpeg):
        """Sonnig + Nebel — mutually exclusive, keep first."""
        result = await self._run(pipeline, mock_repo, sample_jpeg, ["Sonnig", "Nebel", "Mystisch"])
        assert "Sonnig" in result["vision_keywords"]
        assert "Nebel" not in result["vision_keywords"]
