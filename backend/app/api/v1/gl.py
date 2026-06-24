"""
GL inspection endpoints — query the normalised raw GL and validation report.
These are diagnostic endpoints for analysts to verify ingestion quality.

GET /api/v1/deals/{deal_id}/gl/lines        Paginated raw GL lines
GET /api/v1/deals/{deal_id}/gl/validation   Validation report
GET /api/v1/deals/{deal_id}/gl/periods      Summary by period
"""

import json
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query

from app.schemas.gl import ValidationReport
from app.storage import file_store

router = APIRouter(tags=["GL Inspection"])


def _raw_gl_path(deal_id: str) -> Path:
    return file_store.get_processed_dir(deal_id) / "raw_gl.json"


def _validation_path(deal_id: str) -> Path:
    return file_store.get_processed_dir(deal_id) / "validation_report.json"


def _load_raw_gl(deal_id: str) -> list[dict]:
    path = _raw_gl_path(deal_id)
    if not path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"No processed GL found for deal {deal_id}. Run /process first.",
        )
    with open(path, encoding="utf-8") as f:
        return json.load(f)


@router.get("/deals/{deal_id}/gl/lines")
def get_gl_lines(
    deal_id: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=100, ge=1, le=1000),
    account_code: str | None = Query(default=None),
    period: str | None = Query(default=None, description="Filter by period prefix e.g. '2023'"),
) -> dict:
    data = _load_raw_gl(deal_id)

    if account_code:
        data = [r for r in data if r["account_code"].startswith(account_code)]
    if period:
        data = [r for r in data if r["period"].startswith(period)]

    total = len(data)
    start = (page - 1) * page_size
    page_data = data[start : start + page_size]

    return {
        "deal_id": deal_id,
        "total": total,
        "page": page,
        "page_size": page_size,
        "lines": page_data,
    }


@router.get("/deals/{deal_id}/gl/validation", response_model=ValidationReport)
def get_validation_report(deal_id: str) -> ValidationReport:
    path = _validation_path(deal_id)
    if not path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"No validation report found for deal {deal_id}. Run /process first.",
        )
    with open(path, encoding="utf-8") as f:
        return ValidationReport.model_validate(json.load(f))


@router.get("/deals/{deal_id}/gl/periods")
def get_period_summary(deal_id: str) -> dict:
    """Summarise GL by period — useful for quickly checking data coverage."""
    data = _load_raw_gl(deal_id)

    from collections import defaultdict
    from decimal import Decimal

    by_period: dict[str, dict] = defaultdict(lambda: {"total_lines": 0, "total_debits": "0", "total_credits": "0"})

    for row in data:
        p = row["period"][:7]  # YYYY-MM
        amount = Decimal(str(row["amount"]))
        by_period[p]["total_lines"] += 1
        if amount > 0:
            by_period[p]["total_debits"] = str(Decimal(by_period[p]["total_debits"]) + amount)
        else:
            by_period[p]["total_credits"] = str(Decimal(by_period[p]["total_credits"]) + abs(amount))

    return {
        "deal_id": deal_id,
        "periods": [{"period": p, **v} for p, v in sorted(by_period.items())],
        "total_periods": len(by_period),
    }
