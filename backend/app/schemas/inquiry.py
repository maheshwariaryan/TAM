"""
Deal-scoped PBC/inquiry tracker + derived Decision Queue.

InquiryItem mirrors the existing frontend `Inquiry` shape
(frontend/lib/schemas/types.ts InquirySchema) so the frontend model doesn't need to
change, only its data source (real CRUD instead of `/api/deal/inquiry` mock data).

DecisionQueueItem mirrors frontend/lib/schemas/types.ts DecisionQueueItemSchema.
Decision Queue items are never persisted — they're derived fresh on every request from
data that already exists (tie-out Fails, High-severity red flags, missing recommended
documents) plus blocking inquiries from the store below, the same principle
net_debt_bridge and cross_document_validator already apply: never invent a number,
only surface what's actually been computed elsewhere.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

InquiryStatus = Literal["Open", "In Progress", "Resolved", "Deferred"]


class InquiryItem(BaseModel):
    id: str
    deal_id: str
    request: str
    owner: str
    due_date: str
    status: InquiryStatus = "Open"
    blocking: bool = False
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class InquiryCreate(BaseModel):
    request: str = Field(..., min_length=1)
    owner: str = "Unassigned"
    due_date: str
    status: InquiryStatus = "Open"
    blocking: bool = False


class InquiryUpdate(BaseModel):
    request: str | None = None
    owner: str | None = None
    due_date: str | None = None
    status: InquiryStatus | None = None
    blocking: bool | None = None


DecisionQueueSourceTab = Literal["risk-assessment", "inquiry", "documents", "financial-analysis"]


class DecisionQueueItem(BaseModel):
    id: str
    title: str
    impact_area: str
    impact_score: float
    owner: str
    due_date: str
    status: InquiryStatus
    blocking: bool
    rationale: str
    source_tab: DecisionQueueSourceTab
    source_id: str
    source_label: str
    source_url: str


class DecisionQueueResponse(BaseModel):
    deal_id: str
    last_updated: datetime = Field(default_factory=datetime.utcnow)
    readiness: Literal["Ready", "Draft", "Blocked"]
    items: list[DecisionQueueItem]
