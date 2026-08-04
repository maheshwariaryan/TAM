"""
JSON-file-backed inquiry (PBC tracker) store.

One file per deal: data/inquiries/{deal_id}.json — a list of InquiryItem, same
per-deal-JSON-file pattern as app/storage/note_store.py. Ownership is enforced at the
API layer via require_deal_owner, so this module doesn't duplicate an owner_user_id
check — it just reads/writes whatever deal_id it's given.
"""

import uuid
from datetime import UTC, datetime
from pathlib import Path

from app.config import settings
from app.schemas.inquiry import InquiryCreate, InquiryItem, InquiryUpdate
from app.storage.json_io import try_read_json_encrypted, write_json_encrypted


def _inquiries_path(deal_id: str) -> Path:
    return settings.inquiries_dir / f"{deal_id}.json"


def list_inquiries(deal_id: str) -> list[InquiryItem]:
    data = try_read_json_encrypted(_inquiries_path(deal_id))
    if data is None:
        return []
    return [InquiryItem.model_validate(item) for item in data]


def _save_all(deal_id: str, items: list[InquiryItem]) -> None:
    write_json_encrypted(
        _inquiries_path(deal_id), [item.model_dump(mode="json") for item in items]
    )


def create_inquiry(deal_id: str, body: InquiryCreate) -> InquiryItem:
    now = datetime.now(UTC)
    item = InquiryItem(
        id=str(uuid.uuid4()),
        deal_id=deal_id,
        request=body.request,
        owner=body.owner,
        due_date=body.due_date,
        status=body.status,
        blocking=body.blocking,
        created_at=now,
        updated_at=now,
    )
    items = list_inquiries(deal_id)
    items.append(item)
    _save_all(deal_id, items)
    return item


def update_inquiry(deal_id: str, inquiry_id: str, body: InquiryUpdate) -> InquiryItem | None:
    """Partial update. Returns None if no inquiry with that id exists for this deal."""
    items = list_inquiries(deal_id)
    for idx, item in enumerate(items):
        if item.id != inquiry_id:
            continue
        updates = body.model_dump(exclude_none=True)
        updated = item.model_copy(update={**updates, "updated_at": datetime.now(UTC)})
        items[idx] = updated
        _save_all(deal_id, items)
        return updated
    return None


def delete_inquiry(deal_id: str, inquiry_id: str) -> bool:
    """Returns False if no inquiry with that id exists for this deal."""
    items = list_inquiries(deal_id)
    remaining = [item for item in items if item.id != inquiry_id]
    if len(remaining) == len(items):
        return False
    _save_all(deal_id, remaining)
    return True
