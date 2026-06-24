"""Normalize AR/AP aging DataFrames to AgingSummary models."""

import logging
from datetime import date

import pandas as pd
from dateutil import parser as dateutil_parser

from app.pipeline.ingestion.normalizer import DATE_FORMATS, NormalizerError, _parse_decimal
from app.schemas.aging import AgingSummary

logger = logging.getLogger(__name__)


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
        raise NormalizerError(f"Cannot parse aging period: '{raw}'")


def normalise_aging(
    df: pd.DataFrame,
    column_map: dict[str, str],
    source_file: str,
    deal_id: str,
    document_type: str,
) -> list[AgingSummary]:
    """Convert aging DataFrame to AgingSummary list."""
    df = df.rename(columns=column_map)
    summaries: list[AgingSummary] = []

    for raw_row_idx, row in df.iterrows():
        source_row = int(raw_row_idx) + 2
        period_raw = str(row.get("period", "")).strip()
        if not period_raw:
            continue

        try:
            period = _parse_period(period_raw)
            b0 = _parse_decimal(str(row.get("bucket_0_30", "0")).strip() or "0")
            b1 = _parse_decimal(str(row.get("bucket_31_60", "0")).strip() or "0")
            b2 = _parse_decimal(str(row.get("bucket_61_90", "0")).strip() or "0")
            b3 = _parse_decimal(str(row.get("bucket_90_plus", "0")).strip() or "0")
            total_raw = str(row.get("total", "")).strip()
            total = _parse_decimal(total_raw) if total_raw else b0 + b1 + b2 + b3
            entity = str(row.get("entity", "")).strip() or None

            summaries.append(
                AgingSummary(
                    deal_id=deal_id,
                    document_type=document_type,  # type: ignore[arg-type]
                    period=period,
                    entity=entity,
                    bucket_0_30=b0,
                    bucket_31_60=b1,
                    bucket_61_90=b2,
                    bucket_90_plus=b3,
                    total=total,
                    source_file=source_file,
                    source_row=source_row,
                )
            )
        except (NormalizerError, Exception) as exc:
            logger.warning("Aging row %d skipped: %s", source_row, exc)

    if not summaries:
        raise NormalizerError(f"No usable aging rows in '{source_file}'")

    logger.info("Normalised %d aging rows from '%s'", len(summaries), source_file)
    return summaries
