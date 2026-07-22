"""
Simple DCF schemas.

This is intentionally a *simple* DCF, not a full valuation model: unlevered FCF
is approximated as EBITDA - Capex (no tax or NWC-change adjustment), and the
discount rate / terminal growth rate are disclosed, overridable default
assumptions rather than deal-specific WACC — because this system has no
capital-structure or cost-of-capital inputs to derive one from. Every
simplification is listed in `limitations` so nothing looks more precise than
it is. Prefer the net debt bridge and NWC peg over this for headline deal
metrics; this exists as a directional cross-check only.
"""

from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field


class DCFAssumptions(BaseModel):
    discount_rate_annual: float = Field(
        description="Default assumption, not deal-specific WACC — override if a cost of capital is known."
    )
    terminal_growth_rate_annual: float = Field(
        description="Default assumption for Gordon growth terminal value."
    )


class DCFReport(BaseModel):
    deal_id: str
    status: Literal["complete", "skipped"]
    message: str
    projection_periods: int = 0
    assumptions: DCFAssumptions | None = None
    projected_fcf: dict[str, Decimal] = Field(default_factory=dict)
    pv_of_fcf: dict[str, Decimal] = Field(default_factory=dict)
    sum_pv_of_fcf: Decimal | None = None
    terminal_value: Decimal | None = None
    pv_of_terminal_value: Decimal | None = None
    enterprise_value: Decimal | None = None
    limitations: list[str] = Field(default_factory=list)
