"""Document inventory schemas for multi-document data room ingestion."""

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field


class DocumentType(StrEnum):
    GENERAL_LEDGER = "general_ledger"
    TRIAL_BALANCE = "trial_balance"
    AR_AGING = "ar_aging"
    AP_AGING = "ap_aging"
    MANAGEMENT_PROJECTIONS = "management_projections"
    DEBT_AGREEMENT = "debt_agreement"
    CONTRACT_OTHER = "contract_other"

    # Group A — wide/period-row restatements of GL-derived figures. Parsed and
    # reconciled (tie-out) against the corresponding GL-derived statement; never
    # used to recompute it. See cross_document_validator.py::reconcile_schedules.
    BALANCE_SHEET_SCHEDULE = "balance_sheet_schedule"
    INCOME_STATEMENT_SCHEDULE = "income_statement_schedule"
    CASH_FLOW_SCHEDULE = "cash_flow_schedule"
    REVENUE_SCHEDULE = "revenue_schedule"
    COGS_SCHEDULE = "cogs_schedule"
    OPEX_SCHEDULE = "opex_schedule"
    WORKING_CAPITAL_SCHEDULE = "working_capital_schedule"
    INVENTORY_ROLLFORWARD = "inventory_rollforward"

    # Group B — structured data the GL can't provide. Parsed directly into
    # DebtInstrument records, merged with any PDF-derived instruments.
    DEBT_SCHEDULE = "debt_schedule"

    # Group C — recognized, parsed, and persisted for viewing, but not analyzed
    # by any pipeline stage (no lease/cap-table/fixed-asset/payroll/bank module
    # exists yet — each would be its own feature).
    LEASE_SCHEDULE = "lease_schedule"
    FIXED_ASSET_REGISTER = "fixed_asset_register"
    EQUITY_ROLLFORWARD = "equity_rollforward"
    PAYROLL_SCHEDULE = "payroll_schedule"
    BANK_STATEMENT = "bank_statement"

    UNCLASSIFIED = "unclassified"


ParseStatus = Literal["pending", "parsed", "failed", "skipped"]


class DocumentRecord(BaseModel):
    filename: str
    stored_path: str
    size_bytes: int
    uploaded_at: datetime | None = None
    document_type: DocumentType = DocumentType.UNCLASSIFIED
    parse_status: ParseStatus = "pending"
    parse_error: str | None = None
    detail: str | None = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class DocumentInventory(BaseModel):
    deal_id: str
    documents: list[DocumentRecord] = Field(default_factory=list)
    missing_recommended: list[str] = Field(
        default_factory=list,
        description="Document types recommended but not yet uploaded",
    )
    warnings: list[str] = Field(default_factory=list)
