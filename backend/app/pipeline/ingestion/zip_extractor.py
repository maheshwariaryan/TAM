"""Safe ZIP extraction for data room uploads."""

import logging
import zipfile
from io import BytesIO
from pathlib import Path

from app.config import settings
from app.security.file_crypto import encrypt_bytes
from app.storage import file_store

logger = logging.getLogger(__name__)

MAX_ZIP_SIZE_BYTES = 200 * 1024 * 1024
MAX_UNCOMPRESSED_BYTES = 500 * 1024 * 1024
MAX_FILES_IN_ZIP = 200


class ZipExtractorError(Exception):
    pass


def extract_zip(zip_path: Path, dest_dir: Path) -> list[Path]:
    """
    Extract a ZIP archive into dest_dir with path-traversal protection.
    The zip itself is encrypted at rest (see file_store.save_upload) and is
    decrypted into memory here — never to a plaintext temp file. Each
    extracted member is likewise encrypted before it touches disk, so a
    plaintext copy of any data-room document never exists on the filesystem.
    Returns list of extracted file paths (files only, not directories).
    """
    if not zip_path.exists():
        raise ZipExtractorError(f"ZIP not found: {zip_path}")

    if zip_path.stat().st_size > MAX_ZIP_SIZE_BYTES:
        raise ZipExtractorError(
            f"ZIP exceeds {MAX_ZIP_SIZE_BYTES // (1024 * 1024)} MB limit"
        )

    dest_dir.mkdir(parents=True, exist_ok=True)
    extracted: list[Path] = []
    total_uncompressed = 0

    zip_bytes = file_store.read_upload_decrypted(zip_path)

    try:
        with zipfile.ZipFile(BytesIO(zip_bytes)) as zf:
            members = [m for m in zf.infolist() if not m.is_dir()]
            if len(members) > MAX_FILES_IN_ZIP:
                raise ZipExtractorError(f"ZIP contains more than {MAX_FILES_IN_ZIP} files")

            for member in members:
                total_uncompressed += member.file_size
                if total_uncompressed > MAX_UNCOMPRESSED_BYTES:
                    raise ZipExtractorError("ZIP uncompressed size exceeds limit")

                # Reject path traversal
                target = (dest_dir / member.filename).resolve()
                if not str(target).startswith(str(dest_dir.resolve())):
                    raise ZipExtractorError(f"Unsafe path in ZIP: {member.filename}")

                member_bytes = zf.read(member)
                target.parent.mkdir(parents=True, exist_ok=True)
                encrypted = encrypt_bytes(member_bytes, settings.file_encryption_key)
                target.write_bytes(encrypted)
                extracted.append(target)
                logger.debug("Extracted %s", target.name)
    except zipfile.BadZipFile as exc:
        raise ZipExtractorError(f"Invalid ZIP file: {exc}") from exc

    logger.info("Extracted %d files from %s", len(extracted), zip_path.name)
    return extracted
