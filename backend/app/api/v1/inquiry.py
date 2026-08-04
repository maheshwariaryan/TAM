"""
Inquiry (PBC tracker) CRUD + derived Decision Queue.

GET/POST    /api/v1/deals/{deal_id}/inquiries
PATCH/DELETE /api/v1/deals/{deal_id}/inquiries/{inquiry_id}
GET         /api/v1/deals/{deal_id}/decision-queue

Decision Queue items are never persisted — every request derives them fresh from
cross_document_validation.json (tie-out Fails), redflag_report.json (High-severity
flags), document_inventory.json (missing recommended documents), and blocking
inquiries from the store above. impact_score is a UI prioritization weight, not a
financial figure: fixed per source-type tier, except tie-out fails which use the
real variance_pct so ordering among tie-outs reflects actual severity.
"""

import logging
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException

from app.api.v1.deps import require_deal_owner
from app.schemas.aging import CrossDocumentValidation
from app.schemas.documents import DocumentInventory
from app.schemas.inquiry import (
    DecisionQueueItem,
    DecisionQueueResponse,
    InquiryCreate,
    InquiryItem,
    InquiryUpdate,
)
from app.schemas.redflags import RedFlagReport
from app.storage import file_store, inquiry_store
from app.storage.json_io import try_read_json_encrypted

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Inquiry"])

TIEOUT_IMPACT_SCORE_CAP = 99.0
HIGH_REDFLAG_IMPACT_SCORE = 85.0
BLOCKING_INQUIRY_IMPACT_SCORE = 75.0
MISSING_DOC_IMPACT_SCORE = 60.0
_UNSCHEDULED = "Unscheduled"
_OPEN_INQUIRY_STATUSES = {"Open", "In Progress"}


@router.get("/deals/{deal_id}/inquiries", response_model=list[InquiryItem])
def get_inquiries(deal: dict = Depends(require_deal_owner)) -> list[InquiryItem]:
    return inquiry_store.list_inquiries(deal["deal_id"])


@router.post("/deals/{deal_id}/inquiries", response_model=InquiryItem, status_code=201)
def create_inquiry(body: InquiryCreate, deal: dict = Depends(require_deal_owner)) -> InquiryItem:
    return inquiry_store.create_inquiry(deal["deal_id"], body)


@router.patch("/deals/{deal_id}/inquiries/{inquiry_id}", response_model=InquiryItem)
def update_inquiry(
    inquiry_id: str, body: InquiryUpdate, deal: dict = Depends(require_deal_owner)
) -> InquiryItem:
    updated = inquiry_store.update_inquiry(deal["deal_id"], inquiry_id, body)
    if updated is None:
        raise HTTPException(status_code=404, detail=f"Inquiry {inquiry_id} not found")
    return updated


@router.delete("/deals/{deal_id}/inquiries/{inquiry_id}", status_code=204)
def delete_inquiry(inquiry_id: str, deal: dict = Depends(require_deal_owner)) -> None:
    deleted = inquiry_store.delete_inquiry(deal["deal_id"], inquiry_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Inquiry {inquiry_id} not found")


def _load_cross_validation(deal_id: str) -> CrossDocumentValidation | None:
    path = file_store.get_processed_dir(deal_id) / "cross_document_validation.json"
    data = try_read_json_encrypted(path)
    return CrossDocumentValidation.model_validate(data) if data is not None else None


def _load_redflags(deal_id: str) -> RedFlagReport | None:
    path = file_store.get_processed_dir(deal_id) / "redflag_report.json"
    data = try_read_json_encrypted(path)
    return RedFlagReport.model_validate(data) if data is not None else None


def _load_document_inventory(deal_id: str) -> DocumentInventory | None:
    path = file_store.get_processed_dir(deal_id) / "document_inventory.json"
    data = try_read_json_encrypted(path)
    return DocumentInventory.model_validate(data) if data is not None else None


def _derive_decision_queue(deal_id: str) -> DecisionQueueResponse:
    cross_validation = _load_cross_validation(deal_id)
    redflags = _load_redflags(deal_id)
    inventory = _load_document_inventory(deal_id)
    inquiries = inquiry_store.list_inquiries(deal_id)

    fail_tie_outs = [t for t in cross_validation.tie_outs if t.status == "Fail"] if cross_validation else []
    warn_tie_outs = [t for t in cross_validation.tie_outs if t.status == "Warn"] if cross_validation else []
    high_flags = [f for f in redflags.flags if f.severity == "High"] if redflags else []
    medium_flags = [f for f in redflags.flags if f.severity == "Medium"] if redflags else []
    missing_docs = inventory.missing_recommended if inventory else []
    blocking_inquiries = [
        i for i in inquiries if i.blocking and i.status in _OPEN_INQUIRY_STATUSES
    ]

    items: list[DecisionQueueItem] = []

    for tie in fail_tie_outs:
        items.append(DecisionQueueItem(
            id=f"dq-tieout-{tie.name}",
            title=f"Resolve tie-out failure: {tie.name}",
            impact_area="Risk / Tie-out",
            impact_score=min(TIEOUT_IMPACT_SCORE_CAP, round(tie.variance_pct, 1)),
            owner="Finance Controller",
            due_date=_UNSCHEDULED,
            status="Open",
            blocking=True,
            rationale=(
                f"{tie.name} is failing at {tie.variance_pct:.2f}% variance vs a "
                f"{tie.tolerance_pct:.2f}% tolerance."
            ),
            source_tab="risk-assessment",
            source_id=tie.name,
            source_label=tie.name,
            source_url=f"/risk-assessment?focus=tieout&name={tie.name}",
        ))

    for flag in high_flags:
        items.append(DecisionQueueItem(
            id=f"dq-redflag-{flag.flag_id}",
            title=f"Address red flag: {flag.title}",
            impact_area="Risk / Red Flag",
            impact_score=HIGH_REDFLAG_IMPACT_SCORE,
            owner="Deal Team",
            due_date=_UNSCHEDULED,
            status="Open",
            blocking=True,
            rationale=flag.description,
            source_tab="risk-assessment",
            source_id=flag.flag_id,
            source_label=flag.title,
            source_url=f"/risk-assessment?focus=redflag&id={flag.flag_id}",
        ))

    for inq in blocking_inquiries:
        items.append(DecisionQueueItem(
            id=f"dq-inquiry-{inq.id}",
            title=f"Close blocking inquiry: {inq.request}",
            impact_area="Inquiry / Readiness",
            impact_score=BLOCKING_INQUIRY_IMPACT_SCORE,
            owner=inq.owner,
            due_date=inq.due_date,
            status=inq.status,
            blocking=True,
            rationale="Blocking inquiry directly gates report readiness and IC package quality.",
            source_tab="inquiry",
            source_id=inq.id,
            source_label=inq.id,
            source_url=f"/inquiry?focus=inquiry&id={inq.id}",
        ))

    for doc_type in missing_docs:
        items.append(DecisionQueueItem(
            id=f"dq-docs-{doc_type}",
            title=f"Provide missing document: {doc_type}",
            impact_area="Documents / Data Integrity",
            impact_score=MISSING_DOC_IMPACT_SCORE,
            owner="Data Room Owner",
            due_date=_UNSCHEDULED,
            status="Open",
            blocking=False,
            rationale=f"{doc_type} is a recommended document type that has not been uploaded yet.",
            source_tab="documents",
            source_id=doc_type,
            source_label=doc_type,
            source_url="/documents",
        ))

    items.sort(key=lambda item: item.impact_score, reverse=True)

    blocking_count = sum(1 for item in items if item.blocking)
    if blocking_count > 0 or fail_tie_outs:
        readiness: Literal["Ready", "Draft", "Blocked"] = "Blocked"
    elif warn_tie_outs or medium_flags:
        readiness = "Draft"
    else:
        readiness = "Ready"

    logger.info(
        "decision_queue_derived deal_id=%s items=%d readiness=%s",
        deal_id, len(items), readiness,
        extra={"event": "decision_queue_derived", "deal_id": deal_id,
               "item_count": len(items), "readiness": readiness},
    )

    return DecisionQueueResponse(deal_id=deal_id, readiness=readiness, items=items)


@router.get("/deals/{deal_id}/decision-queue", response_model=DecisionQueueResponse)
def get_decision_queue(deal: dict = Depends(require_deal_owner)) -> DecisionQueueResponse:
    return _derive_decision_queue(deal["deal_id"])
