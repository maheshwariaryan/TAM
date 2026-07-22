"""
Narrative report schemas.

The narrative drafter never computes figures — it only phrases sections from a
fact sheet of already-computed numbers (financials, QoE, red flags, NWC, net
debt). `figures_used` is persisted verbatim alongside the drafted prose so a
reviewer can always check every number mentioned in the narrative traces back
to a source report, never to the LLM itself.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

SectionId = Literal[
    "executive_summary", "key_risks", "qoe_highlights", "working_capital", "recommendations"
]


class NarrativeSection(BaseModel):
    section_id: SectionId
    title: str
    content: str


class NarrativeReport(BaseModel):
    deal_id: str
    status: Literal["complete", "partial", "skipped"]
    message: str
    generated_at: datetime = Field(default_factory=datetime.utcnow)
    sections: list[NarrativeSection] = Field(default_factory=list)
    figures_used: dict[str, str] = Field(
        default_factory=dict,
        description="Every figure supplied to the drafter, verbatim — the audit trail for the narrative.",
    )
    data_gaps: list[str] = Field(
        default_factory=list, description="Reports unavailable when this narrative was generated"
    )
