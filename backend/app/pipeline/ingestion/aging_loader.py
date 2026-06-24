"""Column inference for AR/AP aging files."""

import logging

import pandas as pd

from app.pipeline.ingestion.loader import LoaderError

logger = logging.getLogger(__name__)


def infer_aging_column_map(df: pd.DataFrame, doc_type: str) -> dict[str, str]:
    """Map raw columns to canonical aging fields."""
    cols_lower = {c.lower().strip(): c for c in df.columns}

    def find(candidates: list[str]) -> str | None:
        for cand in candidates:
            if cand in cols_lower:
                return cols_lower[cand]
        return None

    mapping: dict[str, str] = {}

    period_col = find(["period", "date", "as of", "as_of", "report date", "month"])
    if period_col:
        mapping[period_col] = "period"

    entity_col = find(["entity", "company", "subsidiary"])
    if entity_col:
        mapping[entity_col] = "entity"

    b0 = find(["0-30", "0_30", "0 - 30", "current", "bucket_0_30", "0 to 30"])
    b1 = find(["31-60", "31_60", "31 - 60", "bucket_31_60"])
    b2 = find(["61-90", "61_90", "61 - 90", "bucket_61_90"])
    b3 = find(["90+", "90 plus", "90_plus", "91+", "over 90", "bucket_90_plus"])
    total_col = find(["total", "total_ar", "total_ap", "total ar", "total ap", "balance"])

    if b0:
        mapping[b0] = "bucket_0_30"
    if b1:
        mapping[b1] = "bucket_31_60"
    if b2:
        mapping[b2] = "bucket_61_90"
    if b3:
        mapping[b3] = "bucket_90_plus"
    if total_col:
        mapping[total_col] = "total"

    if not period_col:
        raise LoaderError(f"Could not identify period column for {doc_type}. Columns: {list(df.columns)}")
    if not (b0 or b1 or b2 or b3):
        raise LoaderError(f"Could not identify aging bucket columns for {doc_type}. Columns: {list(df.columns)}")

    return mapping
