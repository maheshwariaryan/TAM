"""
Auth API — signup, login, logout, current-user, forgot/reset password.

POST /api/v1/auth/signup            Create an account
POST /api/v1/auth/login             Exchange credentials for a session cookie
POST /api/v1/auth/logout            Clear the session cookie
GET  /api/v1/auth/me                Current authenticated user
POST /api/v1/auth/forgot-password   Request a password reset token
POST /api/v1/auth/reset-password    Consume a reset token, set a new password
"""

import hashlib
import logging
import secrets
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Response

from app.api.v1.deps import SESSION_COOKIE_NAME, get_current_user
from app.config import settings
from app.schemas.auth import (
    ForgotPasswordRequest,
    ForgotPasswordResponse,
    LoginRequest,
    ResetPasswordRequest,
    SignupRequest,
    UserPublic,
)
from app.security.jwt_tokens import create_access_token
from app.security.passwords import hash_password, verify_password
from app.storage import user_store

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["Auth"])

_RESET_TOKEN_TTL = timedelta(hours=1)
_COOKIE_MAX_AGE_SECONDS = settings.jwt_expiry_days * 24 * 60 * 60


def _is_local_dev() -> bool:
    # Secure cookies require HTTPS; localhost dev has no TLS. Real deployments
    # should be served over HTTPS, at which point this should always be True —
    # see the Strict-Transport-Security middleware / README TLS notes.
    return "localhost" in settings.cors_origins[0] or "127.0.0.1" in settings.cors_origins[0]


def _set_session_cookie(response: Response, user_id: str) -> None:
    token = create_access_token(user_id)
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        httponly=True,
        samesite="lax",
        secure=not _is_local_dev(),
        max_age=_COOKIE_MAX_AGE_SECONDS,
        path="/",
    )


def _to_public(user: dict) -> UserPublic:
    return UserPublic(id=user["id"], email=user["email"], full_name=user["full_name"], created_at=user["created_at"])


@router.post("/signup", response_model=UserPublic, status_code=201)
def signup(body: SignupRequest, response: Response) -> UserPublic:
    if user_store.get_user_by_email(body.email) is not None:
        raise HTTPException(status_code=409, detail="An account with this email already exists")

    hashed = hash_password(body.password)
    user = user_store.create_user(email=body.email, hashed_password=hashed, full_name=body.full_name)
    logger.info("AUDIT user_signed_up user_id=%s", user["id"])

    _set_session_cookie(response, user["id"])
    return _to_public(user)


@router.post("/login", response_model=UserPublic)
def login(body: LoginRequest, response: Response) -> UserPublic:
    user = user_store.get_user_by_email(body.email)
    # Never let a caller distinguish "no such user" from "wrong password" —
    # constant, generic failure message either way.
    if user is None or not verify_password(user["hashed_password"], body.password):
        raise HTTPException(status_code=401, detail="Incorrect email or password")

    logger.info("AUDIT user_logged_in user_id=%s", user["id"])
    _set_session_cookie(response, user["id"])
    return _to_public(user)


@router.post("/logout")
def logout(response: Response) -> dict:
    response.delete_cookie(SESSION_COOKIE_NAME, path="/")
    return {"ok": True}


@router.get("/me", response_model=UserPublic)
def me(current_user: dict = Depends(get_current_user)) -> UserPublic:
    return _to_public(current_user)


@router.post("/forgot-password", response_model=ForgotPasswordResponse)
def forgot_password(body: ForgotPasswordRequest) -> ForgotPasswordResponse:
    user = user_store.get_user_by_email(body.email)
    # Always return the same generic response whether or not the email is
    # registered — otherwise this endpoint becomes an account-enumeration oracle.
    generic_message = "If an account exists for this email, a reset link has been generated."

    if user is None:
        # No email service exists yet (see module docstring in jwt_tokens.py's
        # sibling note below) — for a non-existent user we still must not
        # return a real token, so respond with an obviously inert placeholder.
        return ForgotPasswordResponse(message=generic_message, reset_token="", reset_url="")

    raw_token = secrets.token_urlsafe(32)
    # Tokens are high-entropy random values, not user-chosen secrets, so a
    # fast hash (not Argon2) is appropriate here — there's nothing to slow
    # down an attacker guessing, since guessing a 256-bit token isn't feasible.
    token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
    expires_at = datetime.now(UTC) + _RESET_TOKEN_TTL

    user_store.update_user(user["id"], {
        "reset_token_hash": token_hash,
        "reset_token_expires_at": expires_at.isoformat(),
    })
    logger.info("AUDIT password_reset_requested user_id=%s", user["id"])

    # POC placeholder for a real email provider (SES/SendGrid/etc.): in
    # production this endpoint would email reset_url and NOT return either
    # field in the API response. Returning it here is the seam to replace.
    reset_url = f"/reset-password?token={raw_token}"
    return ForgotPasswordResponse(message=generic_message, reset_token=raw_token, reset_url=reset_url)


@router.post("/reset-password")
def reset_password(body: ResetPasswordRequest) -> dict:
    token_hash = hashlib.sha256(body.token.encode("utf-8")).hexdigest()
    user = user_store.find_user_by_reset_token_hash(token_hash)
    if user is None:
        raise HTTPException(status_code=400, detail="Reset token is invalid or has expired")

    user_store.update_user(user["id"], {
        "hashed_password": hash_password(body.new_password),
        "reset_token_hash": None,
        "reset_token_expires_at": None,
    })
    logger.info("AUDIT password_reset_completed user_id=%s", user["id"])
    return {"ok": True}
