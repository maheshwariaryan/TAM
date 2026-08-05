"""AR/AP aging summary schemas."""

from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class AgingSummary(BaseModel):
    deal_id: str
    document_type: Literal["ar_aging", "ap_aging"]
    period: date
    entity: str | None = None
    bucket_0_30: Decimal
    bucket_31_60: Decimal
    bucket_61_90: Decimal
    bucket_90_plus: Decimal
    total: Decimal
    source_file: str
    source_row: int

    @model_validator(mode="after")
    def period_is_first_of_month(self) -> "AgingSummary":
        if self.period.day != 1:
            object.__setattr__(self, "period", self.period.replace(day=1))
        return self


class AgingReport(BaseModel):
    deal_id: str
    document_type: Literal["ar_aging", "ap_aging"]
    summaries: list[AgingSummary] = Field(default_factory=list)


class TieOutResult(BaseModel):
    name: str
    expected: Decimal
    observed: Decimal
    difference: Decimal
    variance_pct: float
    tolerance_pct: float
    status: Literal["Pass", "Warn", "Fail"]
    source_documents: list[str] = Field(default_factory=list)


class CrossDocumentValidation(BaseModel):
    deal_id: str
    tie_outs: list[TieOutResult] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
