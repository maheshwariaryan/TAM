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
    change_of_control_clause: str | None = None
    prepayment_terms: str | None = None
    events_of_default: str | None = None
    material_obligations: list[str] = Field(default_factory=list)
    source_document: str
    extraction_confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class DebtSchedule(BaseModel):
    deal_id: str
    instruments: list[DebtInstrument] = Field(default_factory=list)


ClauseType = Literal[
    "change_of_control", "prepayment", "event_of_default", "material_obligation", "covenant"
]


class ContractClause(BaseModel):
    """A single extracted clause, independent of any specific debt instrument.

    Lets the Documents/Risk UI list clauses across all uploaded agreements without
    needing to know which instrument they belong to, while DebtInstrument keeps the
    per-facility view (clause fields above) for the drill-through/audit trail.
    """

    clause_type: ClauseType
    summary: str
    source_document: str
    instrument_id: str | None = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class ContractAnalysisReport(BaseModel):
    deal_id: str
    status: Literal["complete", "partial", "skipped"]
    message: str
    instruments: list[DebtInstrument] = Field(default_factory=list)
    clauses: list[ContractClause] = Field(default_factory=list)
