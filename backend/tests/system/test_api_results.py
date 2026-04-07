"""System tests for GET /api/v1/results/{image_id} — S-RES-01 to S-RES-03."""


# S-RES-01
def test_results_existing_image(client, auth_headers, mock_repo):
    mock_repo.get_image_keywords.return_value = {
        "image_id": "img_42",
        "keywords": ["Bruecke", "Fluss"],
        "geo_keywords": ["Heidelberg"],
        "vision_keywords": ["Bruecke", "Fluss"],
        "gps_lat": 49.4,
        "gps_lon": 8.7,
        "location_name": "Heidelberg",
        "model_used": "llava:13b",
        "processed_at": "2026-01-01T00:00:00+00:00",
    }

    resp = client.get("/api/v1/results/img_42", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["image_id"] == "img_42"
    assert "Bruecke" in data["keywords"]


# S-RES-02
def test_results_nonexistent_image(client, auth_headers, mock_repo):
    mock_repo.get_image_keywords.return_value = None

    resp = client.get("/api/v1/results/nonexistent", headers=auth_headers)
    assert resp.status_code == 404


# S-RES-03
def test_results_require_api_key(client):
    resp = client.get("/api/v1/results/img_42")
    assert resp.status_code == 401
