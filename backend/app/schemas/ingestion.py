"""
Pydantic schemas for the ingestion API layer.
These are the request/response contracts — not the internal pipeline models.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class CreateDealRequest(BaseModel):
    company_name: str = Field(..., min_length=1, max_length=200)
    deal_name: str = Field(..., min_length=1, max_length=200)
    currency: str = Field(default="USD", pattern=r"^[A-Z]{3}$")


class UploadedFileInfo(BaseModel):
    filename: str
    stored_path: str
    size_bytes: int
    uploaded_at: datetime
    document_type: str | None = None
    parse_status: str | None = None
    parse_error: str | None = None
    confidence: float | None = None


class DealResponse(BaseModel):
    deal_id: str
    company_name: str
    deal_name: str
    currency: str
    created_at: datetime
    updated_at: datetime
    stages: dict[str, str]
    progress_pct: int
    uploaded_files: list[UploadedFileInfo]
    error: str | None


class UploadResponse(BaseModel):
    deal_id: str
    files_received: int
    files: list[UploadedFileInfo]


ProcessingStage = Literal[
    "ingestion",
    "coa_mapping",
    "financial_builder",
    "qoe_engine",
    "redflag_detector",
    "nwc_analyzer",
    "dcf_engine",
    "net_debt_bridge",
]


class ProcessRequest(BaseModel):
    stages: list[ProcessingStage] | None = Field(
        default=None,
        description="Stages to run. Omit to run all stages in order.",
    )


class ProcessResponse(BaseModel):
    deal_id: str
    message: str
    stages_queued: list[str]


class ErrorResponse(BaseModel):
    detail: str
    error_code: str
