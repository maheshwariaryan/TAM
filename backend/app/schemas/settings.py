"""
Deal-scoped diligence settings — materiality, tie-out tolerance, and cash-conversion
severity bands. These actually drive downstream calculations (cross-document tie-outs,
schedule reconciliation, red-flag detection), not just inert saved metadata:
see cross_document_validator.validate_cross_documents/reconcile_schedules (tolerance)
and redflag_detector.rules.detect_all (materiality + cash-conversion bands).

All fields carry the same defaults the frontend Settings page has always shown, so a
deal with no settings ever saved behaves identically to today. tie_out_tolerance_pct
replaces the formerly-distinct AR/AP/schedule tolerance constants with one configurable
value; cash_conversion_*_pct define a 3-tier graduated severity scheme for
_rule_low_cash_conversion (below medium -> Medium, below high -> High, at/below
critical -> High with amplified "Critical" language — no new severity tier).
"""

from pydantic import BaseModel, Field, model_validator


class DealSettings(BaseModel):
    materiality_threshold: float = Field(default=75_000.0, ge=0)
    tie_out_tolerance_pct: float = Field(default=0.50, ge=0, le=100)
    cash_conversion_medium_pct: float = Field(default=60.0, ge=0, le=100)
    cash_conversion_high_pct: float = Field(default=30.0, ge=0, le=100)
    cash_conversion_critical_pct: float = Field(default=0.0, ge=0, le=100)

    @model_validator(mode="after")
    def _bands_are_ordered(self) -> "DealSettings":
        if not (
            self.cash_conversion_critical_pct
            <= self.cash_conversion_high_pct
            <= self.cash_conversion_medium_pct
        ):
            raise ValueError(
                "Cash conversion bands must satisfy critical <= high <= medium "
                f"(got critical={self.cash_conversion_critical_pct}, "
                f"high={self.cash_conversion_high_pct}, medium={self.cash_conversion_medium_pct})"
            )
        return self


class DealSettingsUpdate(BaseModel):
    materiality_threshold: float | None = Field(default=None, ge=0)
    tie_out_tolerance_pct: float | None = Field(default=None, ge=0, le=100)
    cash_conversion_medium_pct: float | None = Field(default=None, ge=0, le=100)
    cash_conversion_high_pct: float | None = Field(default=None, ge=0, le=100)
    cash_conversion_critical_pct: float | None = Field(default=None, ge=0, le=100)


def get_deal_settings(deal: dict | None) -> DealSettings:
    """Resolve a deal's effective settings, defaulting for deals created before this
    feature existed (no 'settings' key in the deal record) or when the deal itself
    couldn't be loaded — same numeric defaults as today's UI, so nothing changes for
    deals that never configured settings."""
    return DealSettings.model_validate((deal or {}).get("settings") or {})
