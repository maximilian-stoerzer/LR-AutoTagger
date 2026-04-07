"""System tests for Batch endpoints — S-BAT-01 to S-BAT-10."""

import io
import json


# S-BAT-01
def test_batch_start(client, auth_headers):
    resp = client.post(
        "/api/v1/batch/start",
        headers={**auth_headers, "Content-Type": "application/json"},
        content=json.dumps({"images": [{"image_id": f"img_{i}"} for i in range(10)]}),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "id" in data
    assert data["status"] == "running"


# S-BAT-02
def test_batch_start_no_images(client, auth_headers):
    resp = client.post(
        "/api/v1/batch/start",
        headers={**auth_headers, "Content-Type": "application/json"},
        content=json.dumps({"images": []}),
    )
    assert resp.status_code == 400


# S-BAT-03
def test_batch_status_active_job(client, auth_headers, mock_repo):
    mock_repo.get_active_batch_job.return_value = {
        "id": "job-1",
        "status": "running",
        "total_images": 100,
        "processed": 42,
        "failed": 0,
        "skipped": 0,
        "created_at": "2026-01-01T00:00:00+00:00",
        "updated_at": "2026-01-01T00:01:00+00:00",
    }

    resp = client.get("/api/v1/batch/status", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["processed"] == 42


# S-BAT-04
def test_batch_status_no_job(client, auth_headers):
    resp = client.get("/api/v1/batch/status", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "idle"


# S-BAT-05
def test_batch_next_returns_image_id(client, auth_headers, mock_repo):
    mock_repo.get_active_batch_job.return_value = {"id": "job-1", "status": "running"}
    mock_repo.get_next_unprocessed_image.return_value = "img_0042"

    resp = client.get("/api/v1/batch/next", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["image_id"] == "img_0042"
    assert body["job_id"] == "job-1"


# S-BAT-06
def test_batch_next_empty(client, auth_headers):
    resp = client.get("/api/v1/batch/next", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["image_id"] is None


# S-BAT-07
def test_batch_image_upload(client, auth_headers, sample_jpeg, mock_repo):
    # Active batch with this image registered
    mock_repo.get_active_batch_job.return_value = {"id": "job-1", "status": "running"}
    mock_repo.get_batch_image_meta.return_value = {"gps_lat": None, "gps_lon": None}

    resp = client.post(
        "/api/v1/batch/image",
        headers=auth_headers,
        files={"file": ("test.jpg", io.BytesIO(sample_jpeg), "image/jpeg")},
        data={"image_id": "batch_img_1"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "keywords" in data


# S-BAT-07b: Image not in active batch → 404
def test_batch_image_unknown_id(client, auth_headers, sample_jpeg, mock_repo):
    mock_repo.get_active_batch_job.return_value = {"id": "job-1", "status": "running"}
    mock_repo.get_batch_image_meta.return_value = None

    resp = client.post(
        "/api/v1/batch/image",
        headers=auth_headers,
        files={"file": ("test.jpg", io.BytesIO(sample_jpeg), "image/jpeg")},
        data={"image_id": "not_in_batch"},
    )
    assert resp.status_code == 404


# S-BAT-07c: No active batch → 409
def test_batch_image_no_active_batch(client, auth_headers, sample_jpeg, mock_repo):
    mock_repo.get_active_batch_job.return_value = None

    resp = client.post(
        "/api/v1/batch/image",
        headers=auth_headers,
        files={"file": ("test.jpg", io.BytesIO(sample_jpeg), "image/jpeg")},
        data={"image_id": "batch_img_1"},
    )
    assert resp.status_code == 409


# S-BAT-08
def test_batch_pause_resume(client, auth_headers, mock_repo):
    mock_repo.get_active_batch_job.return_value = {"id": "job-1", "status": "running"}

    resp = client.post("/api/v1/batch/pause", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "paused"

    mock_repo.get_active_batch_job.return_value = {"id": "job-1", "status": "paused"}

    resp = client.post("/api/v1/batch/resume", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "running"


# S-BAT-09
def test_batch_cancel(client, auth_headers, mock_repo):
    mock_repo.get_active_batch_job.return_value = {"id": "job-1", "status": "running"}

    resp = client.post("/api/v1/batch/cancel", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "cancelled"


# S-BAT-10
def test_batch_endpoints_require_api_key(client):
    for method, path in [
        ("post", "/api/v1/batch/start"),
        ("get", "/api/v1/batch/status"),
        ("get", "/api/v1/batch/next"),
        ("post", "/api/v1/batch/pause"),
        ("post", "/api/v1/batch/resume"),
        ("post", "/api/v1/batch/cancel"),
    ]:
        resp = getattr(client, method)(path)
        assert resp.status_code == 401, f"{method.upper()} {path} should require API key"
