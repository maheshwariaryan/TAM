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
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class DocumentInventory(BaseModel):
    deal_id: str
    documents: list[DocumentRecord] = Field(default_factory=list)
    missing_recommended: list[str] = Field(
        default_factory=list,
        description="Document types recommended but not yet uploaded",
    )
