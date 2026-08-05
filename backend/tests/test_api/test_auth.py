"""Auth API tests — signup/login/me/logout and the forgot->reset->login flow."""

import re
import uuid

from fastapi.testclient import TestClient

from app.config import settings
from app.main import app


def _fresh_client() -> TestClient:
    return TestClient(app)


def _signup(client: TestClient, password: str = "test-password-123") -> tuple[dict, str]:
    email = f"test-{uuid.uuid4().hex[:12]}@example.com"
    resp = client.post(
        "/api/v1/auth/signup",
        json={"email": email, "password": password, "full_name": "Test User"},
    )
    assert resp.status_code == 201, resp.text
    return resp.json(), email


def _latest_reset_token_for(email: str) -> str | None:
    # No SMTP configured in tests, so forgot-password falls back to writing
    # the reset link to the dev outbox (see app/services/email.py) instead of
    # returning it in the API response — read it back from there.
    candidates = sorted(
        settings.dev_email_outbox_dir.glob(f"*__{email}.txt"),
        key=lambda p: p.stat().st_mtime,
    )
    if not candidates:
        return None
    body = candidates[-1].read_text(encoding="utf-8")
    match = re.search(r"[?&]token=([^\s&]+)", body)
    return match.group(1) if match else None


class TestSignup:
    def test_signup_returns_public_user_without_password_fields(self):
        client = _fresh_client()
        user, email = _signup(client)
        assert user["email"] == email
        assert "password" not in user
        assert "hashed_password" not in user

    def test_signup_sets_session_cookie(self):
        client = _fresh_client()
        _signup(client)
        assert "tam_session" in client.cookies

    def test_duplicate_email_rejected(self):
        client = _fresh_client()
        user, email = _signup(client)
        resp = client.post(
            "/api/v1/auth/signup",
            json={"email": email, "password": "another-password-123", "full_name": "Dup User"},
        )
        assert resp.status_code == 409

    def test_short_password_rejected(self):
        client = _fresh_client()
        email = f"test-{uuid.uuid4().hex[:12]}@example.com"
        resp = client.post(
            "/api/v1/auth/signup",
            json={"email": email, "password": "short", "full_name": "Test User"},
        )
        assert resp.status_code == 422


class TestLogin:
    def test_login_with_correct_credentials_succeeds(self):
        signup_client = _fresh_client()
        _, email = _signup(signup_client, password="correct-password-123")

        login_client = _fresh_client()
        resp = login_client.post(
            "/api/v1/auth/login", json={"email": email, "password": "correct-password-123"}
        )
        assert resp.status_code == 200
        assert resp.json()["email"] == email
        assert "tam_session" in login_client.cookies

    def test_login_with_wrong_password_rejected(self):
        signup_client = _fresh_client()
        _, email = _signup(signup_client, password="correct-password-123")

        login_client = _fresh_client()
        resp = login_client.post(
            "/api/v1/auth/login", json={"email": email, "password": "wrong-password"}
        )
        assert resp.status_code == 401

    def test_login_with_unknown_email_rejected(self):
        client = _fresh_client()
        resp = client.post(
            "/api/v1/auth/login",
            json={"email": "no-such-user@example.com", "password": "whatever-123"},
        )
        assert resp.status_code == 401


class TestMe:
    def test_me_returns_current_user_when_authenticated(self):
        client = _fresh_client()
        user, email = _signup(client)
        resp = client.get("/api/v1/auth/me")
        assert resp.status_code == 200
        assert resp.json()["id"] == user["id"]
        assert resp.json()["email"] == email

    def test_me_rejected_without_session(self):
        client = _fresh_client()
        resp = client.get("/api/v1/auth/me")
        assert resp.status_code == 401

    def test_me_rejected_with_garbage_cookie(self):
        client = _fresh_client()
        client.cookies.set("tam_session", "not-a-real-jwt")
        resp = client.get("/api/v1/auth/me")
        assert resp.status_code == 401


class TestLogout:
    def test_logout_clears_session(self):
        client = _fresh_client()
        _signup(client)
        assert client.get("/api/v1/auth/me").status_code == 200

        resp = client.post("/api/v1/auth/logout")
        assert resp.status_code == 200
        assert client.get("/api/v1/auth/me").status_code == 401


class TestForgotAndResetPassword:
    def test_forgot_password_for_unknown_email_is_generic(self):
        client = _fresh_client()
        resp = client.post(
            "/api/v1/auth/forgot-password", json={"email": "nobody-here@example.com"}
        )
        assert resp.status_code == 200
        body = resp.json()
        assert set(body.keys()) == {"message"}
        assert _latest_reset_token_for("nobody-here@example.com") is None

    def test_forgot_then_reset_then_login_with_new_password(self):
        signup_client = _fresh_client()
        _, email = _signup(signup_client, password="original-password-123")

        forgot_resp = signup_client.post("/api/v1/auth/forgot-password", json={"email": email})
        assert forgot_resp.status_code == 200
        assert set(forgot_resp.json().keys()) == {"message"}
        reset_token = _latest_reset_token_for(email)
        assert reset_token

        reset_resp = signup_client.post(
            "/api/v1/auth/reset-password",
            json={"token": reset_token, "new_password": "brand-new-password-456"},
        )
        assert reset_resp.status_code == 200

        # Old password no longer works.
        login_client = _fresh_client()
        old_login = login_client.post(
            "/api/v1/auth/login", json={"email": email, "password": "original-password-123"}
        )
        assert old_login.status_code == 401

        # New password does.
        new_login = login_client.post(
            "/api/v1/auth/login", json={"email": email, "password": "brand-new-password-456"}
        )
        assert new_login.status_code == 200

    def test_reset_with_invalid_token_rejected(self):
        client = _fresh_client()
        resp = client.post(
            "/api/v1/auth/reset-password",
            json={"token": "not-a-real-token", "new_password": "whatever-new-123"},
        )
        assert resp.status_code == 400

    def test_reset_token_is_single_use(self):
        signup_client = _fresh_client()
        _, email = _signup(signup_client, password="original-password-123")

        forgot_resp = signup_client.post("/api/v1/auth/forgot-password", json={"email": email})
        assert forgot_resp.status_code == 200
        reset_token = _latest_reset_token_for(email)
        assert reset_token

        first = signup_client.post(
            "/api/v1/auth/reset-password",
            json={"token": reset_token, "new_password": "first-new-password-123"},
        )
        assert first.status_code == 200

        second = signup_client.post(
            "/api/v1/auth/reset-password",
            json={"token": reset_token, "new_password": "second-new-password-456"},
        )
        assert second.status_code == 400
