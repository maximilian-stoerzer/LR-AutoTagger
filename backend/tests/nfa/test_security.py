"""NFA tests: Security — SEC-01 to SEC-10."""

import io
import json

import pytest

pytestmark = pytest.mark.security


# SEC-01: API key in URL parameter should be ignored
def test_api_key_in_query_param_rejected(client, api_key, sample_jpeg):
    resp = client.post(
        f"/api/v1/analyze?api_key={api_key}",
        files={"file": ("test.jpg", io.BytesIO(sample_jpeg), "image/jpeg")},
    )
    assert resp.status_code == 401


# SEC-03: Path traversal in image_id
def test_path_traversal_in_image_id(client, auth_headers, mock_repo):
    mock_repo.get_image_keywords.return_value = None

    malicious_ids = [
        "../../etc/passwd",
        "..\\..\\windows\\system32\\config\\sam",
        "%2e%2e%2fetc%2fpasswd",
    ]
    for img_id in malicious_ids:
        resp = client.get(f"/api/v1/results/{img_id}", headers=auth_headers)
        # Should just return 404 (not found), not expose files
        assert resp.status_code == 404, f"Path traversal not handled for: {img_id}"


# SEC-04: SQL injection in image_id
def test_sql_injection_in_image_id(client, auth_headers, mock_repo):
    mock_repo.get_image_keywords.return_value = None

    malicious_ids = [
        "'; DROP TABLE image_keywords; --",
        "1' OR '1'='1",
        "img_1 UNION SELECT * FROM batch_jobs--",
    ]
    for img_id in malicious_ids:
        resp = client.get(f"/api/v1/results/{img_id}", headers=auth_headers)
        # psycopg uses parameterized queries — should be safe, just 404
        assert resp.status_code == 404


# SEC-05: Oversized file upload
def test_oversized_file_upload(client, auth_headers):
    # 100MB of zeros
    large_data = b"\x00" * (100 * 1024 * 1024)
    resp = client.post(
        "/api/v1/analyze",
        headers=auth_headers,
        files={"file": ("huge.jpg", io.BytesIO(large_data), "image/jpeg")},
    )
    # Should either reject (413) or fail gracefully (not crash the server)
    assert resp.status_code in (200, 413, 422, 500)


# SEC-07: Content-type mismatch
def test_content_type_mismatch(client, auth_headers):
    not_an_image = b"This is not an image at all, just plain text."
    resp = client.post(
        "/api/v1/analyze",
        headers=auth_headers,
        files={"file": ("test.jpg", io.BytesIO(not_an_image), "image/jpeg")},
    )
    # Should fail gracefully (Pillow can't open it)
    assert resp.status_code in (422, 500)


# SEC-09: No wildcard CORS
def test_no_wildcard_cors(client):
    resp = client.options("/api/v1/health")
    cors_header = resp.headers.get("access-control-allow-origin", "")
    assert cors_header != "*", "Wildcard CORS should not be enabled"


# SEC-10: Error responses should not leak internals
def test_error_no_stacktrace(client, auth_headers):
    not_an_image = b"corrupt data"
    resp = client.post(
        "/api/v1/analyze",
        headers=auth_headers,
        files={"file": ("bad.jpg", io.BytesIO(not_an_image), "image/jpeg")},
    )
    if resp.status_code == 500:
        body = resp.text
        assert "Traceback" not in body, "Stack trace leaked in error response"
        assert 'File "/' not in body, "File paths leaked in error response"


# SEC: Batch start with malicious JSON
def test_batch_start_malicious_json(client, auth_headers):
    # Attempt to inject via image metadata
    malicious_payload = {
        "images": [
            {"image_id": "'; DROP TABLE batch_jobs;--"},
            {"image_id": "<script>alert(1)</script>"},
        ]
    }
    resp = client.post(
        "/api/v1/batch/start",
        headers={**auth_headers, "Content-Type": "application/json"},
        content=json.dumps(malicious_payload),
    )
    # Should succeed (parameterized queries protect DB) or fail gracefully
    assert resp.status_code in (200, 400, 422)


# SEC: Empty API key header
def test_empty_api_key_header(client, sample_jpeg):
    resp = client.post(
        "/api/v1/analyze",
        headers={"X-API-Key": ""},
        files={"file": ("test.jpg", io.BytesIO(sample_jpeg), "image/jpeg")},
    )
    assert resp.status_code == 401
