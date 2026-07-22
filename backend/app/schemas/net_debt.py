"""Net Debt Bridge schemas.

Deterministic totals (cash, current/long-term debt, net debt) are computed
purely from the balance sheet — Decimal arithmetic, traceable to source GL
lines through the existing balance sheet builder. Per-instrument detail
(lender, rate, maturity, covenants) comes from PDF contract extraction and is
presented as supplementary schedule detail, never used to recompute the
GL-derived totals — this avoids double-counting risk between two different
sources of truth (ledger vs. contract text).
"""

from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field


class DebtBridgeComponent(BaseModel):
    label: str
    amount: Decimal
    is_subtotal: bool = False


class NetDebtInstrumentDetail(BaseModel):
    instrument_id: str
    facility_type: str
    lender: str | None = None
    principal_outstanding: Decimal | None = None
    interest_rate_pct: Decimal | None = None
    maturity_date: date | None = None
    covenants_summary: str | None = None
    source_document: str
    extraction_confidence: float = 0.0


class NetDebtReport(BaseModel):
    deal_id: str
    status: Literal["complete", "partial", "skipped"]
    message: str
    period: str | None = None
    cash_and_equivalents: Decimal | None = None
    current_debt: Decimal | None = None
    long_term_debt: Decimal | None = None
    total_debt: Decimal | None = None
    net_debt: Decimal | None = None
    net_debt_to_ebitda: float | None = None
    bridge: list[DebtBridgeComponent] = Field(default_factory=list)
    instruments: list[NetDebtInstrumentDetail] = Field(default_factory=list)
    instrument_principal_total: Decimal | None = None
    reconciliation_variance: Decimal | None = None
    reconciliation_note: str | None = None
