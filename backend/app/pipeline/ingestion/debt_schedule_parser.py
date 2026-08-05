"""
Parser for Group B's debt_schedule.csv — structured lender/facility data the GL can't
provide (only aggregate current/long-term debt buckets). Parsed directly into
DebtInstrument records, deterministically (no LLM call), and merged with any PDF-derived
instruments — see ingestion/orchestrator.py and contracts/orchestrator.py.
"""

import logging
import uuid
from datetime import date, datetime

from app.pipeline.ingestion.loader import load_bytes
from app.pipeline.ingestion.normalizer import NormalizerError, _parse_decimal
from app.schemas.contracts import DebtInstrument

logger = logging.getLogger(__name__)

_FACILITY_TYPE_KEYWORDS: tuple[tuple[str, str], ...] = (
    ("revolver", "revolver"),
    ("term loan", "term_loan"),
    ("term_loan", "term_loan"),
    ("note", "note"),
    ("lease", "lease"),
)


def _map_facility_type(loan_type: str) -> str:
    lowered = loan_type.lower()
    for keyword, facility_type in _FACILITY_TYPE_KEYWORDS:
        if keyword in lowered:
            return facility_type
    return "other"


def _parse_maturity(raw: str) -> date | None:
    raw = raw.strip()
    if not raw:
        return None
    for fmt in ("%Y-%m-%d", "%Y-%m"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return None


def parse_debt_schedule_bytes(raw_bytes: bytes, filename: str, deal_id: str) -> list[DebtInstrument]:
    """Parse a debt_schedule.csv (one row per Period per lender/facility) directly into
    DebtInstrument records. Groups rows by (Lender, Loan Type) and uses each group's
    latest period as the instrument's current snapshot."""
    df = load_bytes(raw_bytes, filename)

    cols = {c.lower().strip().replace(" ", "_"): c for c in df.columns}
    if not {"lender", "loan_type", "period"}.issubset(cols):
        return []

    lender_col = cols["lender"]
    loan_type_col = cols["loan_type"]
    period_col = cols["period"]
    principal_col = cols.get("ending_principal_outstanding")
    rate_col = cols.get("implied_interest_rate_%")
    maturity_col = cols.get("maturity")

    groups: dict[tuple[str, str], list] = {}
    for idx, row in df.iterrows():
        key = (str(row[lender_col]).strip(), str(row[loan_type_col]).strip())
        groups.setdefault(key, []).append(idx)

    instruments: list[DebtInstrument] = []
    for (lender, loan_type), idxs in groups.items():
        latest_idx = max(idxs, key=lambda i: df.loc[i, period_col])
        latest = df.loc[latest_idx]

        principal_outstanding = None
        if principal_col:
            try:
                principal_outstanding = _parse_decimal(str(latest[principal_col]))
            except NormalizerError:
                pass

        interest_rate_pct = None
        if rate_col:
            try:
                interest_rate_pct = _parse_decimal(str(latest[rate_col]))
            except NormalizerError:
                pass

        instruments.append(
            DebtInstrument(
                instrument_id=f"DEBT-{uuid.uuid4().hex[:8].upper()}",
                deal_id=deal_id,
                facility_type=_map_facility_type(loan_type),
                lender=lender or None,
                principal_outstanding=principal_outstanding,
                interest_rate_pct=interest_rate_pct,
                maturity_date=_parse_maturity(str(latest[maturity_col])) if maturity_col else None,
                source_document=filename,
                extraction_confidence=1.0,
            )
        )

    logger.info("Parsed debt schedule '%s': %d instrument(s)", filename, len(instruments))
    return instruments
