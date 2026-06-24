"""
Red Flag schemas.

Each RedFlag is a discrete, actionable risk item with severity, estimated financial
impact, source data links, and LLM-generated diligence questions.
"""

from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

Severity = Literal["High", "Medium", "Low", "Informational"]
FlagSource = Literal["rule_engine", "llm_analysis", "contract_parser", "manual"]


class RedFlag(BaseModel):
    flag_id: str
    deal_id: str
    severity: Severity
    category: str                           # "Revenue Quality", "Cost Structure", etc.
    title: str = Field(max_length=100)      # Short headline for the table
    description: str                        # 1-2 sentence explanation
    financial_impact_low: Decimal | None = None
    financial_impact_high: Decimal | None = None
    affected_periods: list[str] = Field(default_factory=list)  # YYYY-MM strings
    source: FlagSource
    rule_id: str | None = None
    source_gl_line_ids: list[str] = Field(default_factory=list)
    source_document: str | None = None
    diligence_questions: list[str] = Field(default_factory=list)
    llm_context: str | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class RedFlagSummary(BaseModel):
    high: int
    medium: int
    low: int
    informational: int
    total: int


class RedFlagReport(BaseModel):
    deal_id: str
    flags: list[RedFlag]
    summary: RedFlagSummary
