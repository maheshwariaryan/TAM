"""Debt instrument and contract extraction schemas."""

from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field


class DebtInstrument(BaseModel):
    instrument_id: str
    deal_id: str
    facility_type: Literal["term_loan", "revolver", "note", "lease", "other"]
    lender: str | None = None
    principal_outstanding: Decimal | None = None
    interest_rate_pct: Decimal | None = None
    maturity_date: date | None = None
    covenants_summary: str | None = None
    source_document: str
    extraction_confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class DebtSchedule(BaseModel):
    deal_id: str
    instruments: list[DebtInstrument] = Field(default_factory=list)
