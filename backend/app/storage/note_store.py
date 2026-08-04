"""
JSON-file-backed notes store.

One file per deal: data/notes/{deal_id}.json — encrypted at rest, same
pattern as app/storage/deal_store.py. Ownership is enforced at the API layer
via require_deal_owner (keyed by deal_id), so this module doesn't duplicate
an owner_user_id check — it just reads/writes whatever deal_id it's given.
"""

from datetime import UTC, datetime
from pathlib import Path

from app.config import settings
from app.schemas.notes import DealNotes
from app.storage.json_io import try_read_json_encrypted, write_json_encrypted


def _notes_path(deal_id: str) -> Path:
    return settings.notes_dir / f"{deal_id}.json"


def get_notes(deal_id: str) -> DealNotes:
    """Returns empty defaults if nothing has been saved yet for this deal."""
    data = try_read_json_encrypted(_notes_path(deal_id))
    if data is None:
        return DealNotes(deal_id=deal_id)
    return DealNotes.model_validate(data)


def save_notes(deal_id: str, notes: str, report_draft: list[str]) -> DealNotes:
    """Full replace — matches the frontend's existing overwrite-on-save semantics."""
    record = DealNotes(
        deal_id=deal_id,
        notes=notes,
        report_draft=report_draft,
        updated_at=datetime.now(UTC),
    )
    write_json_encrypted(_notes_path(deal_id), record.model_dump(mode="json"))
    return record
