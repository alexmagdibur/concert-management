from decimal import ROUND_HALF_UP, Decimal

from scipy.stats import t
from sqlalchemy.orm import Session

from app.repositories.report import ZERO, ReportRepository
from app.schemas.catalog import Page
from app.schemas.finance import FinanceResponse
from app.schemas.report import (
    ConcertRanking,
    ConcertReport,
    ContractBalance,
    DashboardMonth,
    DashboardQuery,
    DashboardSummary,
    ExpenseForecast,
    ForecastEstimate,
    Period,
    RankEntry,
    ReportQuery,
)
from app.services.finance import FinanceError


def _money(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _estimate(ratios: list[Decimal], budget: Decimal) -> ForecastEstimate:
    n = Decimal(len(ratios))
    mean = sum(ratios, ZERO) / n
    variance = sum(((ratio - mean) ** 2 for ratio in ratios), ZERO) / (n - 1)
    critical = Decimal(str(t.ppf(0.975, len(ratios) - 1)))
    margin = critical * variance.sqrt() / n.sqrt()
    lower, upper = mean - margin, mean + margin
    return ForecastEstimate(
        mean_ratio=mean,
        ratio_ci_lower=lower,
        ratio_ci_upper=upper,
        expected_expenses=_money(mean * budget),
        ci_lower=_money(lower * budget),
        ci_upper=_money(upper * budget),
        interpretation="95% confidence interval for mean expenses, not a prediction interval for one concert.",
    )


class ReportService:
    def __init__(self, session: Session):
        self.repository = ReportRepository(session)

    def _concert(self, concert_id: int):
        concert = self.repository.concert(concert_id)
        if concert is None:
            raise FinanceError(404, "Concert not found")
        return concert

    def dashboard(self, query: DashboardQuery) -> DashboardSummary:
        months = [
            DashboardMonth(
                month=month,
                income=_money(income),
                expenses=_money(expenses),
                net=_money(income - expenses),
            )
            for month, income, expenses in self.repository.monthly_totals(query)
        ]
        return DashboardSummary(
            upcoming_count=self.repository.upcoming_count(),
            income=sum((month.income for month in months), ZERO),
            expenses=sum((month.expenses for month in months), ZERO),
            net=sum((month.net for month in months), ZERO),
            months=months,
        )

    def concert_report(self, concert_id: int, query: ReportQuery) -> ConcertReport:
        concert = self._concert(concert_id)
        period = Period.model_validate(query.model_dump(include={"date_from", "date_to", "as_of"}))
        income, expenses, actual = self.repository.period_totals(concert_id, period)
        rows, total = self.repository.period_operations(concert_id, query)
        contracts = [
            ContractBalance(
                contract_id=contract.id,
                number=contract.number,
                direction=contract.direction,
                amount=contract.amount,
                net_paid=paid,
                unpaid=max(contract.amount - paid, ZERO),
                overpaid=max(paid - contract.amount, ZERO),
            )
            for contract, paid in self.repository.contract_balances(concert_id, period.as_of)
        ]
        return ConcertReport(
            period=period,
            concert_id=concert_id,
            income=_money(income),
            expenses=_money(expenses),
            net=_money(income - expenses),
            expense_budget=concert.expense_budget,
            actual_expenses=_money(actual),
            budget_remaining=_money(concert.expense_budget - actual),
            contracts=contracts,
            operations=Page[FinanceResponse](
                items=[FinanceResponse.model_validate(row) for row in rows],
                total=total,
                limit=query.limit,
                offset=query.offset,
            ),
        )

    def ranking(self, period: Period) -> ConcertRanking:
        rows = self.repository.ranking(period)

        def ordered(field: str):
            top = sorted((row for row in rows if row[field] <= 3), key=lambda row: row[field])
            return [RankEntry.model_validate(dict(row)) for row in top]

        return ConcertRanking(
            period=period,
            count=rows[0]["total"] if rows else 0,
            best=ordered("best_rank"),
            worst=ordered("worst_rank"),
        )

    def forecast(self, concert_id: int, history: Period) -> ExpenseForecast:
        concert = self._concert(concert_id)
        if concert.status not in {"NEGOTIATING", "CONFIRMED"}:
            raise FinanceError(409, "Forecast requires a planned concert")
        ratios = []
        incomplete = 0
        for _, budget, actual, posted, drafts in self.repository.historical_expenses(history):
            if posted == 0 or drafts or actual < 0:
                incomplete += 1
            else:
                ratios.append(actual / budget)
        result = ExpenseForecast(
            history=history,
            concert_id=concert_id,
            budget=concert.expense_budget,
            n=len(ratios),
            incomplete_count=incomplete,
        )
        if result.budget <= 0:
            result.reason, result.message = (
                "budget_required",
                "A positive target budget is required.",
            )
        elif incomplete:
            result.reason, result.message = (
                "incomplete_history",
                "Historical expense data are incomplete.",
            )
        elif result.n < 10:
            result.reason, result.message = (
                "insufficient_observations",
                "At least 10 eligible observations are required.",
            )
        else:
            result.forecast = _estimate(ratios, result.budget)
        return result
