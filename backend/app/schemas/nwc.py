"""Net Working Capital analysis schemas.

NWCDataPoint / NWCPeg mirror the shapes specified in plan.txt. All amounts are
Decimal; every data point is derived from the already-computed BalanceSheet
(itself traceable to source GL lines), so NWC figures inherit that audit trail.
"""

from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

PegMethod = Literal["ltm_average", "median_trailing_12", "seasonal_adjusted"]


class NWCDataPoint(BaseModel):
    period: date
    accounts_receivable: Decimal
    inventory: Decimal
    prepaid_expenses: Decimal
    other_current_assets: Decimal
    accounts_payable: Decimal
    accrued_liabilities: Decimal
    deferred_revenue: Decimal
    current_debt: Decimal
    other_current_liabilities: Decimal
    net_working_capital: Decimal
    nwc_as_pct_revenue: float | None = None


class NWCPeg(BaseModel):
    method: PegMethod
    peg_amount: Decimal
    confidence_interval_low: Decimal
    confidence_interval_high: Decimal
    seasonality_detected: bool
    recommended: bool
    rationale: str


class WorkingCapitalRatios(BaseModel):
    period: str  # latest YYYY-MM covered
    dso_days: float | None = None
    dpo_days: float | None = None
    dio_days: float | None = None
    cash_conversion_cycle_days: float | None = None
    ar_over_60d_pct: float | None = None
    ap_over_60d_pct: float | None = None


class NWCReport(BaseModel):
    deal_id: str
    status: Literal["complete", "partial", "skipped"]
    message: str
    has_ar_aging: bool = False
    has_ap_aging: bool = False
    data_points: list[NWCDataPoint] = Field(default_factory=list)
    pegs: list[NWCPeg] = Field(default_factory=list)
    peak_nwc: Decimal | None = None
    peak_period: str | None = None
    trough_nwc: Decimal | None = None
    trough_period: str | None = None
    nwc_volatility: float | None = Field(
        default=None, description="Coefficient of variation (stdev / mean) of monthly NWC"
    )
    ratios: WorkingCapitalRatios | None = None


class CommercialHealthReport(BaseModel):
    """Deterministic commercial-health metrics derivable without customer-level data.

    Customer concentration / churn / customer-count metrics are intentionally
    omitted here — this system does not ingest customer-level revenue data, and
    faking those figures would violate the no-invented-numbers rule. When a
    customer revenue schedule is ingested in a future iteration, extend this
    report rather than approximating from aggregate GL data.
    """

    deal_id: str
    status: Literal["complete", "partial", "skipped"]
    message: str
    revenue_growth_yoy_pct: dict[str, float] = Field(default_factory=dict)
    gross_margin_trend_pct: dict[str, float] = Field(default_factory=dict)
    ebitda_margin_trend_pct: dict[str, float] = Field(default_factory=dict)
    revenue_volatility: float | None = Field(
        default=None, description="Coefficient of variation of monthly revenue"
    )
    seasonality_detected: bool = False
    seasonality_note: str | None = None
    unavailable_metrics: list[str] = Field(
        default_factory=list,
        description="Metrics that require data not present in this deal (e.g. customer-level revenue)",
    )
