"""System test fixtures — FastAPI TestClient with mocked external services."""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.config import settings


@pytest.fixture
def mock_repo():
    """Mock repository that behaves like a connected DB."""
    repo = AsyncMock()
    repo.ping = AsyncMock(return_value=True)
    repo.connect = AsyncMock()
    repo.run_migrations = AsyncMock()
    repo.close = AsyncMock()
    repo.get_image_keywords = AsyncMock(return_value=None)
    repo.save_image_keywords = AsyncMock()
    repo.image_already_processed = AsyncMock(return_value=False)
    repo.create_batch_job = AsyncMock(
        return_value={
            "id": "test-job-id",
            "status": "running",
            "total_images": 10,
            "processed": 0,
            "failed": 0,
            "skipped": 0,
            "created_at": "2026-01-01T00:00:00+00:00",
        }
    )
    repo.increment_batch_progress = AsyncMock()
    repo.create_chunks = AsyncMock()
    repo.store_batch_image_meta = AsyncMock()
    repo.get_active_batch_job = AsyncMock(return_value=None)
    repo.get_next_unprocessed_image = AsyncMock(return_value=None)
    repo.get_batch_image_meta = AsyncMock(return_value=None)
    repo.update_batch_job_status = AsyncMock()
    repo.mark_chunk_image_done = AsyncMock()
    repo.has_pending_chunks = AsyncMock(return_value=False)
    return repo


@pytest.fixture
def api_key():
    return settings.api_key


@pytest.fixture
def auth_headers(api_key):
    return {"X-API-Key": api_key}


@pytest.fixture
def client(mock_repo):
    """FastAPI TestClient with mocked Repository, Ollama, Geocoder.

    The lifespan handler creates a Repository() — we patch the symbol used
    by app.main so that the lifespan never touches a real database.
    """
    with (
        patch("app.main.Repository", return_value=mock_repo),
        patch("app.pipeline.keyword_pipeline.OllamaClient") as MockOllama,
        patch("app.pipeline.keyword_pipeline.Geocoder") as MockGeocoder,
    ):
        ollama_instance = AsyncMock()
        ollama_instance.analyze_image = AsyncMock(return_value=["Bruecke", "Fluss", "Stein"])
        ollama_instance.health = AsyncMock(return_value=True)
        MockOllama.return_value = ollama_instance

        geocoder_instance = AsyncMock()
        geocoder_instance.reverse = AsyncMock(
            return_value={
                "geo_keywords": ["Heidelberg", "Deutschland"],
                "location_name": "Heidelberg, Deutschland",
            }
        )
        MockGeocoder.return_value = geocoder_instance

        from app.main import app

        with TestClient(app, raise_server_exceptions=False) as c:
            yield c
