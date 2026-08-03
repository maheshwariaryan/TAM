"""
Encrypted, atomic JSON file I/O — the single choke point every module that
persists JSON under data/ should go through.

Every pipeline stage orchestrator previously had its own tiny ad-hoc
`open()`/`json.load`/`json.dump` helper. This module replaces all of them with
one implementation: JSON is encrypted (AES-256-GCM, see security/file_crypto.py)
before it touches disk, and writes are atomic (temp file + rename) so a crash
mid-write never leaves a corrupted or half-encrypted file behind — the same
safety property app/storage/deal_store.py already had for plaintext writes,
now generalized to cover encryption too.
"""

import json
import os
import tempfile
from pathlib import Path
from typing import Any

from app.config import settings
from app.security.file_crypto import decrypt_bytes, encrypt_bytes


class JsonIOError(Exception):
    pass


def write_json_encrypted(path: Path, data: Any) -> None:
    """Serialize `data` to JSON, encrypt it, and write atomically."""
    plaintext = json.dumps(data, indent=2, default=str).encode("utf-8")
    blob = encrypt_bytes(plaintext, settings.file_encryption_key)

    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(blob)
        os.replace(tmp_path, path)
    except Exception:
        os.unlink(tmp_path)
        raise


def read_json_encrypted(path: Path) -> Any:
    """Read and decrypt a JSON file written by write_json_encrypted."""
    blob = path.read_bytes()
    plaintext = decrypt_bytes(blob, settings.file_encryption_key)
    return json.loads(plaintext)


def try_read_json_encrypted(path: Path) -> Any | None:
    """Same as read_json_encrypted, but returns None if the file doesn't exist —
    the common "load this optional report if the stage has run" pattern used
    throughout the pipeline orchestrators."""
    if not path.exists():
        return None
    return read_json_encrypted(path)
