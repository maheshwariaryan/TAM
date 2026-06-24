"""
JSON-file-backed deal store.

One file per deal: data/deals/{deal_id}.json
Designed for easy swap to PostgreSQL/DynamoDB when moving to cloud.
All write operations are atomic (write-then-rename) to prevent corruption.
"""

import json
import os
import tempfile
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.config import settings


def _deal_path(deal_id: str) -> Path:
    return settings.deal_store_dir / f"{deal_id}.json"


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _atomic_write(path: Path, data: dict) -> None:
    """Write JSON atomically using a temp file + rename to prevent partial writes."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, default=str)
        os.replace(tmp_path, path)
    except Exception:
        os.unlink(tmp_path)
        raise


def create_deal(company_name: str, deal_name: str, currency: str = "USD") -> dict:
    deal_id = str(uuid.uuid4())
    deal = {
        "deal_id": deal_id,
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
    _atomic_write(_deal_path(deal_id), deal)
    return deal


def get_deal(deal_id: str) -> dict | None:
    path = _deal_path(deal_id)
    if not path.exists():
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def update_deal(deal_id: str, updates: dict[str, Any]) -> dict:
    deal = get_deal(deal_id)
    if deal is None:
        raise KeyError(f"Deal {deal_id} not found")
    deal.update(updates)
    deal["updated_at"] = _now()
    _atomic_write(_deal_path(deal_id), deal)
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
    _atomic_write(_deal_path(deal_id), deal)
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
    _atomic_write(_deal_path(deal_id), deal)
    return deal


def list_deals() -> list[dict]:
    deals = []
    for path in sorted(settings.deal_store_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            with open(path, encoding="utf-8") as f:
                deals.append(json.load(f))
        except (json.JSONDecodeError, OSError):
            continue
    return deals
