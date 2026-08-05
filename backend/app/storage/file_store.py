"""
Manages uploaded file storage on disk.

Structure: data/uploads/{deal_id}/{original_filename}
Designed so the directory can be swapped for S3/Blob storage when moving to cloud.
"""

import logging
import shutil
from pathlib import Path

from app.config import settings
from app.security.access_log import log_document_access
from app.security.file_crypto import decrypt_bytes, encrypt_bytes

logger = logging.getLogger(__name__)


def get_upload_dir(deal_id: str) -> Path:
    path = settings.upload_dir / deal_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def save_upload(deal_id: str, filename: str, content: bytes) -> tuple[Path, int]:
    """
    Encrypts and saves uploaded file bytes to disk. Returns (stored_path,
    plaintext_size_bytes) — the size is the original document size, not the
    (slightly larger) encrypted blob size, since that's what's meaningful to
    show a user. If a file with the same name already exists, it is overwritten.
    """
    upload_dir = get_upload_dir(deal_id)

    # Sanitize filename: strip path traversal characters
    safe_name = Path(filename).name
    dest = upload_dir / safe_name

    try:
        encrypted = encrypt_bytes(content, settings.file_encryption_key)
        dest.write_bytes(encrypted)
    except OSError as exc:
        logger.error(
            "Failed to write upload %s for deal %s: %s", safe_name, deal_id, exc,
            extra={"event": "upload_write_failed", "deal_id": deal_id,
                   "doc_filename": safe_name, "error": str(exc)},
        )
        raise
    return dest, len(content)


def read_upload_decrypted(path: Path) -> bytes:
    """Decrypt an uploaded file into memory. Never writes plaintext to disk —
    callers that need to hand a file to a third-party parser (pandas,
    pdfplumber, zipfile) should wrap this in BytesIO rather than write it back
    out to a temp file. Every call is recorded in the access log — uploads
    live at data/uploads/{deal_id}/{filename}, so both are derived from the
    path itself rather than threading extra params through every parser."""
    plaintext = decrypt_bytes(path.read_bytes(), settings.file_encryption_key)

    deal_id = path.parent.name
    from app.storage import deal_store  # local import: avoids a circular import at module load

    owner_user_id = None
    try:
        deal = deal_store.get_deal(deal_id)
        if deal:
            owner_user_id = deal.get("owner_user_id")
    except Exception:
        pass  # best-effort — never let access logging break the actual read
    log_document_access(
        user_id=owner_user_id, deal_id=deal_id, action="decrypt", filename=path.name
    )

    return plaintext


def list_uploads(deal_id: str) -> list[Path]:
    upload_dir = settings.upload_dir / deal_id
    if not upload_dir.exists():
        return []
    return sorted(upload_dir.iterdir())


def get_processed_dir(deal_id: str) -> Path:
    path = settings.processed_dir / deal_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def delete_deal_files(deal_id: str) -> None:
    """Remove all uploaded and processed files for a deal."""
    for base in (settings.upload_dir, settings.processed_dir):
        deal_dir = base / deal_id
        if deal_dir.exists():
            try:
                shutil.rmtree(deal_dir)
            except OSError as exc:
                logger.error(
                    "Failed to delete %s for deal %s: %s", deal_dir, deal_id, exc,
                    extra={"event": "delete_deal_files_failed", "deal_id": deal_id,
                           "path": str(deal_dir), "error": str(exc)},
                )
                raise
