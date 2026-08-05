"""Management projections parser."""

import logging
from datetime import date
from decimal import Decimal

import pandas as pd
from dateutil import parser as dateutil_parser

from app.pipeline.ingestion.loader import LoaderError, load_bytes, load_file
from app.pipeline.ingestion.normalizer import DATE_FORMATS, NormalizerError, _parse_decimal
from app.schemas.projections import ProjectionLine

logger = logging.getLogger(__name__)


def infer_projection_column_map(df: pd.DataFrame) -> dict[str, str]:
    cols_lower = {c.lower().strip(): c for c in df.columns}

    def find(candidates: list[str]) -> str | None:
        for cand in candidates:
            if cand in cols_lower:
                return cols_lower[cand]
        return None

    mapping: dict[str, str] = {}
    period_col = find(["period", "date", "month", "year", "fiscal period", "forecast period"])
    if period_col:
        mapping[period_col] = "period"

    for canonical, candidates in [
        ("revenue", ["revenue", "sales", "top line", "total revenue"]),
        ("cogs", ["cogs", "cost of goods sold", "cost of sales", "direct costs"]),
        ("opex", ["opex", "operating expenses", "sg&a", "sga", "operating expense"]),
        ("ebitda", ["ebitda", "adjusted ebitda", "operating profit"]),
        ("capex", ["capex", "capital expenditure", "capital expenditures", "capex spend"]),
        ("entity", ["entity", "company", "subsidiary"]),
    ]:
        col = find(candidates)
        if col:
            mapping[col] = canonical

    if not period_col:
        raise LoaderError(f"Could not identify period column. Columns: {list(df.columns)}")
    metric_cols = {"revenue", "cogs", "opex", "ebitda", "capex"} & set(mapping.values())
    if not metric_cols:
        raise LoaderError(f"Could not identify projection metric columns. Columns: {list(df.columns)}")

    return mapping


def _parse_period(raw: str) -> date:
    raw = raw.strip()
    for fmt in DATE_FORMATS:
        try:
            dt = pd.to_datetime(raw, format=fmt)
            return dt.date().replace(day=1)
        except (ValueError, TypeError):
            continue
    try:
        dt = dateutil_parser.parse(raw, dayfirst=False)
        return dt.date().replace(day=1)
    except Exception:
        raise NormalizerError(f"Cannot parse projection period: '{raw}'")


def _optional_decimal(row: pd.Series, key: str) -> Decimal | None:
    raw = str(row.get(key, "")).strip()
    if not raw or raw in ("", "-", "N/A"):
        return None
    return _parse_decimal(raw)


def parse_projections(path, deal_id: str) -> list[ProjectionLine]:
    """Load and normalise a management projections file from a plaintext path
    on disk (test fixtures and other non-encrypted callers)."""
    from pathlib import Path
    p = Path(path)
    df = load_file(p)
    return _parse_projections_df(df, p.name, deal_id)


def parse_projections_bytes(raw_bytes: bytes, filename: str, deal_id: str) -> list[ProjectionLine]:
    """Load and normalise a management projections file from already-in-memory
    bytes (e.g. decrypted upload content)."""
    df = load_bytes(raw_bytes, filename)
    return _parse_projections_df(df, filename, deal_id)


def _parse_projections_df(df: pd.DataFrame, filename: str, deal_id: str) -> list[ProjectionLine]:
    col_map = infer_projection_column_map(df)
    df = df.rename(columns=col_map)
    lines: list[ProjectionLine] = []
    blank_period_rows = 0
    all_blank_metric_rows = 0

    for raw_row_idx, row in df.iterrows():
        source_row = int(raw_row_idx) + 2
        period_raw = str(row.get("period", "")).strip()
        if not period_raw:
            blank_period_rows += 1
            continue
        try:
            period = _parse_period(period_raw)
            revenue = _optional_decimal(row, "revenue")
            cogs = _optional_decimal(row, "cogs")
            opex = _optional_decimal(row, "opex")
            ebitda = _optional_decimal(row, "ebitda")
            capex = _optional_decimal(row, "capex")
            entity = str(row.get("entity", "")).strip() or None

            if ebitda is None and revenue is not None and cogs is not None and opex is not None:
                ebitda = revenue - cogs - opex

            if not any(v is not None for v in (revenue, cogs, opex, ebitda, capex)):
                all_blank_metric_rows += 1
                logger.warning(
                    "Projection row %d (period=%s) skipped: no metric columns had a parseable value",
                    source_row, period_raw,
                )
                continue

            lines.append(
                ProjectionLine(
                    period=period,
                    entity=entity,
                    revenue=revenue,
                    cogs=cogs,
                    opex=opex,
                    ebitda=ebitda,
                    capex=capex,
                    source_file=filename,
                    source_row=source_row,
                )
            )
        except (NormalizerError, Exception) as exc:
            logger.warning("Projection row %d skipped: %s", source_row, exc)

    if not lines:
        raise NormalizerError(f"No usable projection rows in '{filename}'")

    if blank_period_rows:
        logger.warning(
            "Projections parser: %d row(s) in '%s' skipped for blank period",
            blank_period_rows, filename,
            extra={"event": "projection_rows_blank_period_skipped", "source_file": filename,
                   "blank_period_rows": blank_period_rows},
        )
    logger.info(
        "Parsed %d projection lines from '%s' (%d skipped for blank period, %d skipped for no parseable metrics)",
        len(lines), filename, blank_period_rows, all_blank_metric_rows,
    )
    return lines
