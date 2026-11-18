from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.schemas.catalog import Input, Page
from app.schemas.contract import CalendarDate, Direction
from app.schemas.finance import FinanceResponse, FinanceTotals


class Period(Input):
    date_from: CalendarDate
    date_to: CalendarDate
    as_of: CalendarDate

    @model_validator(mode="after")
    def chronological(self):
        if self.date_to < self.date_from:
            raise ValueError("date_to must be on or after date_from")
        return self


class ReportQuery(Period):
    limit: int = Field(default=20, ge=1, le=100)
    offset: int = Field(default=0, ge=0, le=9223372036854775807)


class ContractBalance(BaseModel):
    contract_id: int
    number: str
    direction: Direction
    amount: Decimal
    net_paid: Decimal
    unpaid: Decimal
    overpaid: Decimal


class ConcertReport(FinanceTotals):
    period: Period
    concert_id: int
    expense_budget: Decimal
    actual_expenses: Decimal
    budget_remaining: Decimal
    contracts: list[ContractBalance]
    operations: Page[FinanceResponse]


class RankEntry(FinanceTotals):
    concert_id: int
    name: str
    starts_at: datetime


class ConcertRanking(BaseModel):
    period: Period
    count: int
    best: list[RankEntry]
    worst: list[RankEntry]


class ForecastEstimate(BaseModel):
    mean_ratio: Decimal
    ratio_ci_lower: Decimal
    ratio_ci_upper: Decimal
    expected_expenses: Decimal
    ci_lower: Decimal
    ci_upper: Decimal
    interval_kind: Literal["confidence_interval_for_mean"] = "confidence_interval_for_mean"
    confidence_level: Literal[0.95] = 0.95
    interpretation: str


class ExpenseForecast(BaseModel):
    history: Period
    concert_id: int
    budget: Decimal
    n: int
    incomplete_count: int
    forecast: ForecastEstimate | None = None
    reason: Literal["budget_required", "insufficient_observations", "incomplete_history"] | None = (
        None
    )
    message: str | None = None
