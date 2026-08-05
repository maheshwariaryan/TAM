"""
Deal-scoped analyst notes — a single free-text blob plus the report-draft
snippet list, matching the shape the frontend's notes page already edits
(see frontend/lib/store/use-global-store.ts). No per-note id/author model:
the UI is a single textarea + a snippet list, not a list of discrete notes.
"""

from datetime import datetime

from pydantic import BaseModel, Field


class DealNotes(BaseModel):
    deal_id: str
    notes: str = ""
    report_draft: list[str] = Field(default_factory=list)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class DealNotesUpdate(BaseModel):
    notes: str = ""
    report_draft: list[str] = Field(default_factory=list)
