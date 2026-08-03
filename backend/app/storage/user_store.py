"""
JSON-file-backed user store.

One file per user: data/users/{user_id}.json — encrypted at rest, same pattern
as app/storage/deal_store.py. Email lookup iterates all user files rather than
maintaining a separate index — fine at POC scale (a handful to low hundreds of
users); swap for an indexed/DB lookup before that stops being true.
"""

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from app.config import settings
from app.security.file_crypto import FileCryptoError
from app.storage.json_io import try_read_json_encrypted, write_json_encrypted

logger = logging.getLogger(__name__)


class UserStoreError(Exception):
    """Raised when a user file exists but cannot be read (corrupted/unreadable/
    undecryptable)."""


def _user_path(user_id: str):
    return settings.user_store_dir / f"{user_id}.json"


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _normalize_email(email: str) -> str:
    return email.strip().lower()


def create_user(email: str, hashed_password: str, full_name: str) -> dict:
    user_id = str(uuid.uuid4())
    user = {
        "id": user_id,
        "email": _normalize_email(email),
        "hashed_password": hashed_password,
        "full_name": full_name,
        "created_at": _now(),
        "updated_at": _now(),
        "reset_token_hash": None,
        "reset_token_expires_at": None,
    }
    write_json_encrypted(_user_path(user_id), user)
    return user


def get_user_by_id(user_id: str) -> dict | None:
    path = _user_path(user_id)
    try:
        return try_read_json_encrypted(path)
    except (FileCryptoError, ValueError, OSError) as exc:
        logger.error(
            "Corrupted or unreadable user file %s: %s", path, exc,
            extra={"event": "user_file_corrupted", "user_id": user_id, "error": str(exc)},
        )
        raise UserStoreError(f"User {user_id} exists but its data file is corrupted: {exc}") from exc


def get_user_by_email(email: str) -> dict | None:
    target = _normalize_email(email)
    for path in settings.user_store_dir.glob("*.json"):
        try:
            user = try_read_json_encrypted(path)
        except (FileCryptoError, ValueError, OSError) as exc:
            logger.error(
                "Skipping corrupted or unreadable user file %s: %s", path, exc,
                extra={"event": "user_file_corrupted", "path": str(path), "error": str(exc)},
            )
            continue
        if user and user.get("email") == target:
            return user
    return None


def update_user(user_id: str, updates: dict[str, Any]) -> dict:
    user = get_user_by_id(user_id)
    if user is None:
        raise KeyError(f"User {user_id} not found")
    user.update(updates)
    user["updated_at"] = _now()
    write_json_encrypted(_user_path(user_id), user)
    return user


def find_user_by_reset_token_hash(token_hash: str) -> dict | None:
    """Iterate users looking for a matching, unexpired reset token hash.
    POC-scale; see module docstring."""
    now = datetime.now(UTC)
    for path in settings.user_store_dir.glob("*.json"):
        try:
            user = try_read_json_encrypted(path)
        except (FileCryptoError, ValueError, OSError):
            continue
        if not user or user.get("reset_token_hash") != token_hash:
            continue
        expires_at = user.get("reset_token_expires_at")
        if not expires_at or datetime.fromisoformat(expires_at) < now:
            continue
        return user
    return None
