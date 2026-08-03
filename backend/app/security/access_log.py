"""
Lightweight document access audit log — who read/downloaded/decrypted what,
and when. Due-diligence engagements need this trail; a simple append-only
JSON-lines file is enough for a local POC, no need for a database table here.
"""

import json
import logging
from datetime import UTC, datetime
from pathlib import Path

from app.config import settings

logger = logging.getLogger(__name__)


def _log_path() -> Path:
    return settings.deal_store_dir.parent / "access.log"


def log_document_access(
    *, user_id: str | None, deal_id: str | None, action: str, filename: str | None = None
) -> None:
    """Append one JSON line recording a document read/download/decrypt event.
    Never raises — a logging failure must not break the request it's logging."""
    entry = {
        "timestamp": datetime.now(UTC).isoformat(),
        "user_id": user_id,
        "deal_id": deal_id,
        "action": action,
        "filename": filename,
    }
    try:
        path = _log_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, default=str) + "\n")
    except OSError as exc:
        logger.error("Failed to write access log entry %r: %s", entry, exc)
