"""
QoE API endpoints.

GET /api/v1/deals/{deal_id}/qoe                              Full QoE report + waterfall
GET /api/v1/deals/{deal_id}/qoe/adjustments/{adj_id}/source  GL line drill-through
"""


from fastapi import APIRouter, HTTPException

from app.pipeline.financial_builder.orchestrator import load_mapped_gl
from app.pipeline.qoe_engine.orchestrator import load_qoe_report
from app.schemas.qoe import QoEReport

router = APIRouter(tags=["Quality of Earnings"])


@router.get("/deals/{deal_id}/qoe", response_model=QoEReport)
def get_qoe(deal_id: str) -> QoEReport:
    try:
        return load_qoe_report(deal_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.get("/deals/{deal_id}/qoe/adjustments/{adjustment_id}/source")
def get_adjustment_source(deal_id: str, adjustment_id: str) -> dict:
    """Return the source GL lines for a specific adjustment — the audit drill-through."""
    try:
        report = load_qoe_report(deal_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    adj = next((a for a in report.adjustments if a.adjustment_id == adjustment_id), None)
    if adj is None:
        raise HTTPException(status_code=404, detail=f"Adjustment {adjustment_id} not found")

    try:
        mapped = load_mapped_gl(deal_id)
    except Exception as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    source_ids = set(adj.source_gl_line_ids)
    source_lines = [gl.model_dump(mode="json") for gl in mapped if gl.line_id in source_ids]

    return {
        "adjustment_id": adjustment_id,
        "label": adj.label,
        "adjustment_amount": str(adj.adjustment_amount),
        "source_line_count": len(source_lines),
        "gl_lines": source_lines,
    }
