"""note_store round-trip tests — fast, disk-only, no LLM."""

import uuid

import pytest

from app.storage import note_store

pytestmark = pytest.mark.unit


def _deal_id() -> str:
    return f"test-note-store-{uuid.uuid4()}"


def test_get_notes_returns_empty_defaults_when_none_saved():
    deal_id = _deal_id()
    result = note_store.get_notes(deal_id)
    assert result.deal_id == deal_id
    assert result.notes == ""
    assert result.report_draft == []


def test_save_then_get_round_trips():
    deal_id = _deal_id()
    saved = note_store.save_notes(deal_id, "assumption: revenue is cash-basis", ["snippet one"])
    assert saved.notes == "assumption: revenue is cash-basis"
    assert saved.report_draft == ["snippet one"]

    loaded = note_store.get_notes(deal_id)
    assert loaded.notes == saved.notes
    assert loaded.report_draft == saved.report_draft


def test_save_is_a_full_replace_not_a_merge():
    deal_id = _deal_id()
    note_store.save_notes(deal_id, "first draft", ["a", "b"])
    note_store.save_notes(deal_id, "second draft", ["c"])

    loaded = note_store.get_notes(deal_id)
    assert loaded.notes == "second draft"
    assert loaded.report_draft == ["c"]
