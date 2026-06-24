"""
GL Normalizer — transforms a raw DataFrame into a list of RawGLLine Pydantic models.

Responsibilities:
  - Apply the column mapping from loader.infer_column_map()
  - Parse dates (handles many formats accounting systems produce)
  - Normalise amounts to a single signed Decimal:
      positive = economically debit-normal (expense, asset)
      negative = economically credit-normal (revenue, liability)
  - Strip whitespace from string fields
  - Assign UUIDs to each line for audit trail
  - Coerce period to first-of-month (GL is always monthly)

This module emits RawGLLine objects — no accounting logic, no classification.
"""

import logging
import uuid
from datetime import date
from decimal import Decimal, InvalidOperation

import pandas as pd
from dateutil import parser as dateutil_parser

from app.pipeline.ingestion.loader import LoaderError
from app.schemas.gl import RawGLLine

logger = logging.getLogger(__name__)


class NormalizerError(Exception):
    pass


# Common date formats seen in accounting GL exports (tried in order before dateutil fallback)
DATE_FORMATS = [
    "%Y-%m-%d",    # 2024-01-31  (ISO, most common in modern systems)
    "%Y-%m",       # 2024-01     (period-level, no day)
    "%m/%d/%Y",    # 01/31/2024  (US)
    "%d/%m/%Y",    # 31/01/2024  (UK / AUS)
    "%d-%m-%Y",    # 31-01-2024
    "%Y%m%d",      # 20240131    (SAP / Oracle)
    "%b %Y",       # Jan 2024
    "%B %Y",       # January 2024
    "%m/%Y",       # 01/2024
]


def _parse_date(raw: str) -> date:
    raw = raw.strip()
    for fmt in DATE_FORMATS:
        try:
            dt = pd.to_datetime(raw, format=fmt)
            return dt.date().replace(day=1)  # coerce to first-of-month
        except (ValueError, TypeError):
            continue
    # Fallback: dateutil is very permissive but can misinterpret ambiguous dates
    try:
        dt = dateutil_parser.parse(raw, dayfirst=False)
        return dt.date().replace(day=1)
    except Exception:
        raise NormalizerError(f"Cannot parse date: '{raw}'")


def _parse_decimal(raw: str) -> Decimal:
    """Parse a numeric string to Decimal, handling common accounting formats."""
    cleaned = raw.strip().replace(",", "").replace(" ", "").replace("(", "-").replace(")", "")
    if cleaned in ("", "-", "—", "N/A", "n/a"):
        return Decimal("0")
    try:
        return Decimal(cleaned)
    except InvalidOperation:
        raise NormalizerError(f"Cannot parse amount: '{raw}'")


def normalise(
    df: pd.DataFrame,
    column_map: dict[str, str],
    source_file: str,
    deal_id: str,
) -> list[RawGLLine]:
    """
    Convert a raw DataFrame (from loader.py) into a validated list of RawGLLine.

    Args:
        df:          Raw DataFrame from loader.load_file()
        column_map:  Mapping from raw column names to canonical names (from loader.infer_column_map)
        source_file: Original filename for audit trail
        deal_id:     Deal identifier

    Returns:
        List of RawGLLine Pydantic models, one per non-empty source row.

    Raises:
        NormalizerError: if critical fields cannot be parsed for a row.
    """
    # Rename to canonical column names
    df = df.rename(columns=column_map)
    canonical = set(column_map.values())

    # Determine amount sign convention
    has_debit_credit = "debit" in canonical and "credit" in canonical
    has_net_amount = "amount" in canonical

    errors: list[str] = []
    lines: list[RawGLLine] = []

    for raw_row_idx, row in df.iterrows():
        source_row = int(raw_row_idx) + 2  # +2: header row + 0-indexed → 1-indexed

        # Skip entirely blank rows
        non_empty = [str(v).strip() for v in row.values if str(v).strip()]
        if not non_empty:
            continue

        try:
            # ── Date ─────────────────────────────────────────────────────────
            period_raw = str(row.get("period", "")).strip()
            if not period_raw:
                errors.append(f"Row {source_row}: empty period — skipped")
                continue
            period = _parse_date(period_raw)

            # ── Account code and description ──────────────────────────────────
            account_code = str(row.get("account_code", "")).strip()
            account_description = str(row.get("account_description", "")).strip()

            if not account_code and not account_description:
                errors.append(f"Row {source_row}: no account code or description — skipped")
                continue

            # Fallback: if code is missing use description as code
            if not account_code:
                account_code = account_description[:20]

            # ── Amount — convert debit/credit columns to signed net amount ────
            if has_debit_credit:
                debit_raw = str(row.get("debit", "0")).strip() or "0"
                credit_raw = str(row.get("credit", "0")).strip() or "0"
                debit = _parse_decimal(debit_raw)
                credit = _parse_decimal(credit_raw)
                # Convention: debit positive, credit negative
                amount = debit - credit
            elif has_net_amount:
                amount_raw = str(row.get("amount", "0")).strip() or "0"
                amount = _parse_decimal(amount_raw)
            else:
                errors.append(f"Row {source_row}: no amount column found — skipped")
                continue

            # ── Optional fields ───────────────────────────────────────────────
            entity = str(row.get("entity", "")).strip() or None
            cost_center = str(row.get("cost_center", "")).strip() or None
            note = str(row.get("note", "")).strip() or None
            # Also capture statement hint if the source file includes it
            # (used in our fixture; real client data may not have this)
            _stmt_hint = str(row.get("statement", "")).strip() or None

            lines.append(
                RawGLLine(
                    line_id=f"GL-{uuid.uuid4().hex[:12].upper()}",
                    deal_id=deal_id,
                    period=period,
                    account_code=account_code,
                    account_description=account_description,
                    amount=amount,
                    entity=entity,
                    cost_center=cost_center,
                    source_file=source_file,
                    source_row=source_row,
                    note=note,
                )
            )

        except (NormalizerError, LoaderError) as exc:
            errors.append(f"Row {source_row}: {exc}")
        except Exception as exc:
            errors.append(f"Row {source_row}: unexpected error — {exc}")

    if errors:
        # Log all errors; raise only if we got zero usable rows
        for err in errors:
            logger.warning(err)
        if not lines:
            raise NormalizerError(
                f"No usable rows found in '{source_file}'. "
                f"Errors ({len(errors)}): {errors[:5]}"
            )

    logger.info(
        "Normalised %d rows from '%s' (%d skipped)",
        len(lines), source_file, len(errors),
    )
    return lines
