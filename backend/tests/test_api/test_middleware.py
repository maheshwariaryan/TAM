"""
Tests for the request logging middleware behaviour.

Validates that:
- X-Request-ID is present in every response.
- A caller-supplied X-Request-ID is echoed back (not replaced).
- The middleware does not swallow errors — error responses still carry the header.
"""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app, raise_server_exceptions=False)


class TestRequestIdHeader:
    def test_health_response_has_request_id(self):
        response = client.get("/health")
        assert response.status_code == 200
        assert "x-request-id" in response.headers, "X-Request-ID must be present in all responses"
        assert len(response.headers["x-request-id"]) > 0

    def test_caller_supplied_request_id_is_echoed(self):
        custom_id = "test-correlation-abc-123"
        response = client.get("/health", headers={"X-Request-ID": custom_id})
        assert response.headers.get("x-request-id") == custom_id

    def test_404_response_has_request_id(self):
        response = client.get("/api/v1/deals/nonexistent-deal-id")
        assert response.status_code == 404
        assert "x-request-id" in response.headers

    def test_request_id_is_unique_per_request(self):
        r1 = client.get("/health")
        r2 = client.get("/health")
        id1 = r1.headers.get("x-request-id")
        id2 = r2.headers.get("x-request-id")
        assert id1 != id2, "Each request should receive a distinct auto-generated request ID"
