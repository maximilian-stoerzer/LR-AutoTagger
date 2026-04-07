"""System tests for GET /api/v1/health — S-HLT-01 to S-HLT-04."""

from unittest.mock import AsyncMock, patch


# S-HLT-01
def test_health_all_ok(client):
    with patch("app.api.routes.OllamaClient") as MockOllama:
        instance = AsyncMock()
        instance.health = AsyncMock(return_value=True)
        MockOllama.return_value = instance

        resp = client.get("/api/v1/health")

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["database"] == "ok"
    assert data["ollama"] == "ok"


# S-HLT-02
def test_health_db_unavailable(client, mock_repo):
    mock_repo.ping = AsyncMock(return_value=False)

    with patch("app.api.routes.OllamaClient") as MockOllama:
        instance = AsyncMock()
        instance.health = AsyncMock(return_value=True)
        MockOllama.return_value = instance

        resp = client.get("/api/v1/health")

    data = resp.json()
    assert data["status"] == "degraded"
    assert data["database"] == "unavailable"


# S-HLT-03
def test_health_ollama_unavailable(client):
    with patch("app.api.routes.OllamaClient") as MockOllama:
        instance = AsyncMock()
        instance.health = AsyncMock(return_value=False)
        MockOllama.return_value = instance

        resp = client.get("/api/v1/health")

    data = resp.json()
    assert data["status"] == "degraded"
    assert data["ollama"] == "unavailable"


# S-HLT-04
def test_health_no_api_key_needed(client):
    with patch("app.api.routes.OllamaClient") as MockOllama:
        instance = AsyncMock()
        instance.health = AsyncMock(return_value=True)
        MockOllama.return_value = instance

        resp = client.get("/api/v1/health")  # No X-API-Key header

    assert resp.status_code == 200
