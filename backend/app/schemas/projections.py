"""Management projections schemas for DCF inputs."""

from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field, model_validator


class ProjectionLine(BaseModel):
    period: date
    entity: str | None = None
    revenue: Decimal | None = None
    cogs: Decimal | None = None
    opex: Decimal | None = None
    ebitda: Decimal | None = None
    capex: Decimal | None = None
    source_file: str
    source_row: int

    @model_validator(mode="after")
    def period_is_first_of_month(self) -> "ProjectionLine":
        if self.period.day != 1:
            object.__setattr__(self, "period", self.period.replace(day=1))
        return self


class ProjectionSchedule(BaseModel):
    deal_id: str
    lines: list[ProjectionLine] = Field(default_factory=list)
