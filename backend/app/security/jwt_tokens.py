"""
JWT session tokens (HS256, via PyJWT).

Tradeoff vs. an opaque server-side session token, noted here rather than
re-litigated at every call site: a JWT is stateless — no session store to
persist/clean up, which fits this project's local-JSON-file storage model.
The cost is that a JWT can't be revoked before it expires without maintaining
a blocklist (which would reintroduce the server-side state a JWT is meant to
avoid). For a short-lived local POC session, an unrevocable-until-expiry token
is an acceptable tradeoff; a real deployment with logout-everywhere or
compromised-token-revocation requirements should move to server-side sessions
or a JWT blocklist.
"""

from datetime import UTC, datetime, timedelta
from typing import Any

import jwt

from app.config import settings

_ALGORITHM = "HS256"


class TokenError(Exception):
    pass


def create_access_token(user_id: str) -> str:
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": user_id,
        "iat": now,
        "exp": now + timedelta(days=settings.jwt_expiry_days),
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=_ALGORITHM)


def decode_access_token(token: str) -> str:
    """Returns the user_id ("sub" claim). Raises TokenError if the token is
    missing, malformed, expired, or has an invalid signature."""
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[_ALGORITHM])
    except jwt.PyJWTError as exc:
        raise TokenError(f"Invalid or expired session token: {exc}") from exc
    user_id = payload.get("sub")
    if not user_id:
        raise TokenError("Session token missing subject claim")
    return user_id
