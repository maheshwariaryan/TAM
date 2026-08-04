"""inquiry_store round-trip tests — fast, disk-only, no LLM."""

import uuid

import pytest

from app.schemas.inquiry import InquiryCreate, InquiryUpdate
from app.storage import inquiry_store

pytestmark = pytest.mark.unit


def _deal_id() -> str:
    return f"test-inquiry-store-{uuid.uuid4()}"


def test_list_returns_empty_when_none_saved():
    assert inquiry_store.list_inquiries(_deal_id()) == []


def test_create_then_list_round_trips():
    deal_id = _deal_id()
    created = inquiry_store.create_inquiry(
        deal_id, InquiryCreate(request="Provide AP aging detail", owner="Data Room Owner", due_date="2026-03-01")
    )
    assert created.deal_id == deal_id
    assert created.request == "Provide AP aging detail"
    assert created.status == "Open"
    assert created.blocking is False

    listed = inquiry_store.list_inquiries(deal_id)
    assert len(listed) == 1
    assert listed[0].id == created.id


def test_create_defaults_owner_and_blocking():
    deal_id = _deal_id()
    created = inquiry_store.create_inquiry(deal_id, InquiryCreate(request="X", due_date="2026-03-01"))
    assert created.owner == "Unassigned"
    assert created.blocking is False


def test_update_partial_merges_onto_existing():
    deal_id = _deal_id()
    created = inquiry_store.create_inquiry(
        deal_id, InquiryCreate(request="Provide bank statements", owner="Data Room Owner", due_date="2026-03-01")
    )
    updated = inquiry_store.update_inquiry(deal_id, created.id, InquiryUpdate(status="Resolved"))
    assert updated is not None
    assert updated.status == "Resolved"
    assert updated.request == "Provide bank statements"  # untouched field preserved
    assert updated.updated_at >= created.updated_at


def test_update_unknown_id_returns_none():
    deal_id = _deal_id()
    inquiry_store.create_inquiry(deal_id, InquiryCreate(request="X", due_date="2026-03-01"))
    assert inquiry_store.update_inquiry(deal_id, "no-such-id", InquiryUpdate(status="Resolved")) is None


def test_delete_removes_only_the_targeted_item():
    deal_id = _deal_id()
    a = inquiry_store.create_inquiry(deal_id, InquiryCreate(request="A", due_date="2026-03-01"))
    b = inquiry_store.create_inquiry(deal_id, InquiryCreate(request="B", due_date="2026-03-01"))

    assert inquiry_store.delete_inquiry(deal_id, a.id) is True
    remaining = inquiry_store.list_inquiries(deal_id)
    assert [item.id for item in remaining] == [b.id]


def test_delete_unknown_id_returns_false():
    deal_id = _deal_id()
    assert inquiry_store.delete_inquiry(deal_id, "no-such-id") is False
