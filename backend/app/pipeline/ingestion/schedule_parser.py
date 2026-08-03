"""
Parsers for Group A "restatement" schedules — wide financial-statement/account-level
files (balance sheet, income statement, cash flow, revenue, COGS, opex) and long
period-row files (working capital, inventory rollforward).

Both parsers return the same shape — dict[label_or_metric, dict[period "YYYY-MM", Decimal]]
— so cross_document_validator.py::reconcile_schedules can treat every schedule uniformly
regardless of whether the source file was wide or long. These files are never used to
recompute GL-derived statements; they're only reconciled against them (see
net_debt_bridge/orchestrator.py's docstring for why — same principle applies here).
"""

import logging
import re
from decimal import Decimal

from app.pipeline.ingestion.loader import load_bytes
from app.pipeline.ingestion.normalizer import NormalizerError, _parse_decimal

logger = logging.getLogger(__name__)

_PERIOD_COL_RE = re.compile(r"^\d{4}-\d{2}$")


def parse_wide_schedule_bytes(raw_bytes: bytes, filename: str) -> dict[str, dict[str, Decimal]]:
    """Parse a wide schedule (first column = label, one column per period, optional
    trailing FY* annual columns which are ignored) into {label: {period: value}}."""
    df = load_bytes(raw_bytes, filename)
    label_col = df.columns[0]
    period_cols = [c for c in df.columns if _PERIOD_COL_RE.match(str(c).strip())]

    result: dict[str, dict[str, Decimal]] = {}
    for _, row in df.iterrows():
        label = str(row[label_col]).strip()
        if not label:
            continue
        period_values: dict[str, Decimal] = {}
        for pcol in period_cols:
            try:
                period_values[pcol] = _parse_decimal(str(row[pcol]))
            except NormalizerError:
                continue
        if period_values:
            result[label] = period_values

    logger.info("Parsed wide schedule '%s': %d labels across %d periods", filename, len(result), len(period_cols))
    return result


def parse_period_row_schedule_bytes(
    raw_bytes: bytes, filename: str, period_col: str = "Period"
) -> dict[str, dict[str, Decimal]]:
    """Parse a long schedule (one row per period, metrics as columns) into
    {metric_column: {period: value}} — the transpose of the wide shape above."""
    df = load_bytes(raw_bytes, filename)
    if period_col not in df.columns:
        return {}

    metric_cols = [c for c in df.columns if c != period_col]
    result: dict[str, dict[str, Decimal]] = {c: {} for c in metric_cols}

    for _, row in df.iterrows():
        period = str(row[period_col]).strip()
        if not _PERIOD_COL_RE.match(period):
            continue
        for mcol in metric_cols:
            try:
                result[mcol][period] = _parse_decimal(str(row[mcol]))
            except NormalizerError:
                continue

    result = {k: v for k, v in result.items() if v}
    logger.info("Parsed period-row schedule '%s': %d metrics across %d rows", filename, len(result), len(df))
    return result
