"""
Red Flag API endpoints.

GET /api/v1/deals/{deal_id}/redflags               Full report, filterable
GET /api/v1/deals/{deal_id}/redflags/summary       Counts only (fast)
"""

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.v1.deps import require_deal_owner
from app.pipeline.redflag_detector.orchestrator import load_redflag_report
from app.schemas.redflags import RedFlagReport, RedFlagSummary

router = APIRouter(tags=["Red Flags"])


@router.get("/deals/{deal_id}/redflags", response_model=RedFlagReport)
def get_redflags(
    deal_id: str,
    severity: str | None = Query(
        default=None,
        description="Comma-separated filter: High,Medium,Low,Informational",
    ),
    category: str | None = Query(default=None),
    _owned_deal: dict = Depends(require_deal_owner),
) -> RedFlagReport:
    try:
        report = load_redflag_report(deal_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    flags = report.flags

    if severity:
        allowed = {s.strip() for s in severity.split(",")}
        flags = [f for f in flags if f.severity in allowed]

    if category:
        flags = [f for f in flags if category.lower() in f.category.lower()]

    summary = RedFlagSummary(
        high=sum(1 for f in flags if f.severity == "High"),
        medium=sum(1 for f in flags if f.severity == "Medium"),
        low=sum(1 for f in flags if f.severity == "Low"),
        informational=sum(1 for f in flags if f.severity == "Informational"),
        total=len(flags),
    )

    return RedFlagReport(deal_id=deal_id, flags=flags, summary=summary)


@router.get("/deals/{deal_id}/redflags/summary", response_model=RedFlagSummary)
def get_redflag_summary(deal_id: str, _owned_deal: dict = Depends(require_deal_owner)) -> RedFlagSummary:
    try:
        report = load_redflag_report(deal_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return report.summary
