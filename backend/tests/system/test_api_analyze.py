"""System tests for POST /api/v1/analyze — S-ANL-01 to S-ANL-06."""

import io


# S-ANL-01
def test_analyze_with_gps(client, auth_headers, sample_jpeg):
    resp = client.post(
        "/api/v1/analyze",
        headers=auth_headers,
        files={"file": ("test.jpg", io.BytesIO(sample_jpeg), "image/jpeg")},
        data={"gps_lat": "49.4", "gps_lon": "8.7", "image_id": "test_img_1"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "keywords" in data
    assert len(data["keywords"]) > 0


# S-ANL-02
def test_analyze_without_gps(client, auth_headers, sample_jpeg):
    resp = client.post(
        "/api/v1/analyze",
        headers=auth_headers,
        files={"file": ("test.jpg", io.BytesIO(sample_jpeg), "image/jpeg")},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "keywords" in data


# S-ANL-03
def test_analyze_no_file(client, auth_headers):
    resp = client.post("/api/v1/analyze", headers=auth_headers)
    assert resp.status_code == 422


# S-ANL-05
def test_analyze_missing_api_key(client, sample_jpeg):
    resp = client.post(
        "/api/v1/analyze",
        files={"file": ("test.jpg", io.BytesIO(sample_jpeg), "image/jpeg")},
    )
    assert resp.status_code == 401


# S-ANL-06
def test_analyze_response_format(client, auth_headers, sample_jpeg):
    resp = client.post(
        "/api/v1/analyze",
        headers=auth_headers,
        files={"file": ("test.jpg", io.BytesIO(sample_jpeg), "image/jpeg")},
        data={"image_id": "fmt_test"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "image_id" in data
    assert "keywords" in data
    assert "geo_keywords" in data
    assert "vision_keywords" in data
    assert "location_name" in data
    assert isinstance(data["keywords"], list)
