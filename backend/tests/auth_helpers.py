"""
Shared test helper: authenticate a TestClient.

Every deal-scoped endpoint now requires a real session (see
app/api/v1/deps.py::require_deal_owner), so every test file that drives the
API through a TestClient needs a signed-up user before it can create/access
deals. TestClient persists cookies across requests made through the same
instance, so signing up once right after construction is enough — no need to
touch any individual test function.
"""

import uuid

from fastapi.testclient import TestClient


def authenticate(client: TestClient) -> dict:
    """Sign up a fresh, uniquely-named test user on this client and return
    the created user's public info. The session cookie is now set on `client`
    and will be sent automatically on every subsequent request."""
    email = f"test-{uuid.uuid4().hex[:12]}@example.com"
    resp = client.post(
        "/api/v1/auth/signup",
        json={"email": email, "password": "test-password-123", "full_name": "Test User"},
    )
    assert resp.status_code == 201, f"Test user signup failed: {resp.status_code} {resp.text}"
    return resp.json()
