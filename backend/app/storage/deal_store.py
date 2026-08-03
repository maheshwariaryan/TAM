"""
JSON-file-backed deal store.

One file per deal: data/deals/{deal_id}.json — encrypted at rest (AES-256-GCM,
see app/storage/json_io.py). Designed for easy swap to PostgreSQL/DynamoDB when
moving to cloud. All write operations are atomic (write-then-rename) to
prevent corruption.
"""

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from app.config import settings
from app.security.file_crypto import FileCryptoError
from app.storage.json_io import read_json_encrypted, write_json_encrypted

logger = logging.getLogger(__name__)


class DealStoreError(Exception):
    """Raised when a deal file exists but cannot be read (corrupted/unreadable/
    undecryptable) — distinct from a deal simply not existing, which returns
    None instead."""


def _deal_path(deal_id: str):
    return settings.deal_store_dir / f"{deal_id}.json"


def _now() -> str:
    return datetime.now(UTC).isoformat()


def create_deal(
    company_name: str, deal_name: str, currency: str = "USD", owner_user_id: str | None = None
) -> dict:
    deal_id = str(uuid.uuid4())
    deal = {
        "deal_id": deal_id,
        "owner_user_id": owner_user_id,
        "company_name": company_name,
        "deal_name": deal_name,
        "currency": currency,
        "created_at": _now(),
        "updated_at": _now(),
        "stages": {
            "ingestion": "pending",
            "coa_mapping": "pending",
            "financial_builder": "pending",
            "qoe_engine": "pending",
            "redflag_detector": "pending",
            "nwc_analyzer": "pending",
            "dcf_engine": "pending",
            "net_debt_bridge": "pending",
        },
        "progress_pct": 0,
        "uploaded_files": [],
        "error": None,
    }
    write_json_encrypted(_deal_path(deal_id), deal)
    return deal


def get_deal(deal_id: str) -> dict | None:
    path = _deal_path(deal_id)
    if not path.exists():
        return None
    try:
        return read_json_encrypted(path)
    except (FileCryptoError, ValueError, OSError) as exc:
        logger.error(
            "Corrupted or unreadable deal file %s: %s", path, exc,
            extra={"event": "deal_file_corrupted", "deal_id": deal_id, "path": str(path),
                   "error": str(exc)},
        )
        raise DealStoreError(f"Deal {deal_id} exists but its data file is corrupted: {exc}") from exc


def update_deal(deal_id: str, updates: dict[str, Any]) -> dict:
    deal = get_deal(deal_id)
    if deal is None:
        raise KeyError(f"Deal {deal_id} not found")
    deal.update(updates)
    deal["updated_at"] = _now()
    write_json_encrypted(_deal_path(deal_id), deal)
    return deal


def set_stage_status(deal_id: str, stage: str, status: str) -> dict:
    deal = get_deal(deal_id)
    if deal is None:
        raise KeyError(f"Deal {deal_id} not found")
    deal["stages"][stage] = status

    # Recompute overall progress
    stage_order = [
        "ingestion", "coa_mapping", "financial_builder", "qoe_engine", "redflag_detector",
        "nwc_analyzer", "dcf_engine", "net_debt_bridge",
    ]
    completed = sum(1 for s in stage_order if deal["stages"].get(s) == "complete")
    deal["progress_pct"] = int((completed / len(stage_order)) * 100)

    deal["updated_at"] = _now()
    write_json_encrypted(_deal_path(deal_id), deal)
    return deal


def add_uploaded_file(deal_id: str, filename: str, stored_path: str, size_bytes: int) -> dict:
    deal = get_deal(deal_id)
    if deal is None:
        raise KeyError(f"Deal {deal_id} not found")
    deal["uploaded_files"].append({
        "filename": filename,
        "stored_path": stored_path,
        "size_bytes": size_bytes,
        "uploaded_at": _now(),
    })
    deal["updated_at"] = _now()
    write_json_encrypted(_deal_path(deal_id), deal)
    return deal


def list_deals(owner_user_id: str | None = None) -> list[dict]:
    """List deals, newest first. When owner_user_id is given, only that
    user's deals are returned — callers must always pass it for any
    user-facing listing; the unfiltered form exists for internal/admin use."""
    deals = []
    for path in sorted(settings.deal_store_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            deal = read_json_encrypted(path)
        except (FileCryptoError, ValueError, OSError) as exc:
            logger.error(
                "Skipping corrupted or unreadable deal file %s: %s", path, exc,
                extra={"event": "deal_file_corrupted", "path": str(path), "error": str(exc)},
            )
            continue
        if owner_user_id is not None and deal.get("owner_user_id") != owner_user_id:
            continue
        deals.append(deal)
    return deals
