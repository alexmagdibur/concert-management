from datetime import date
from decimal import Decimal

from sqlalchemy import Date, and_, case, cast, func, or_, select
from sqlalchemy.orm import Session, aliased

from app.models.entities import Concert, Contract, FinanceEntry
from app.schemas.report import Period, ReportQuery

ZERO = Decimal("0.00")


def _sum_amount(*criteria):
    return func.coalesce(func.sum(FinanceEntry.amount).filter(*criteria), ZERO)


def _actual_expenses(original):
    expenses = _sum_amount(
        FinanceEntry.status == "POSTED",
        FinanceEntry.direction == "OUT",
        FinanceEntry.original_id.is_(None),
    )
    refunds = _sum_amount(
        FinanceEntry.status == "POSTED", FinanceEntry.direction == "IN", original.direction == "OUT"
    )
    return expenses - refunds


def _utc_date(column):
    return cast(func.timezone("UTC", column), Date)


class ReportRepository:
    def __init__(self, session: Session):
        self.session = session

    def concert(self, concert_id: int) -> Concert | None:
        return self.session.get(Concert, concert_id)

    def period_totals(self, concert_id: int, period: Period):
        original = aliased(FinanceEntry)
        return self.session.execute(
            select(
                _sum_amount(FinanceEntry.direction == "IN"),
                _sum_amount(FinanceEntry.direction == "OUT"),
                _actual_expenses(original),
            )
            .select_from(FinanceEntry)
            .outerjoin(original, original.id == FinanceEntry.original_id)
            .where(
                FinanceEntry.concert_id == concert_id,
                FinanceEntry.status == "POSTED",
                FinanceEntry.occurred_on.between(period.date_from, period.date_to),
            )
        ).one()

    def period_operations(self, concert_id: int, query: ReportQuery):
        selection = select(FinanceEntry).where(
            FinanceEntry.concert_id == concert_id,
            FinanceEntry.status == "POSTED",
            FinanceEntry.occurred_on.between(query.date_from, query.date_to),
        )
        total = self.session.scalar(select(func.count()).select_from(selection.subquery()))
        rows = self.session.scalars(
            selection.order_by(FinanceEntry.occurred_on, FinanceEntry.id)
            .limit(query.limit)
            .offset(query.offset)
        ).all()
        return rows, total

    def contract_balances(self, concert_id: int, as_of: date):
        signed_amount = case(
            (FinanceEntry.direction == Contract.direction, FinanceEntry.amount),
            else_=-FinanceEntry.amount,
        )
        return self.session.execute(
            select(Contract, func.coalesce(func.sum(signed_amount), ZERO))
            .outerjoin(
                FinanceEntry,
                and_(
                    FinanceEntry.contract_id == Contract.id,
                    FinanceEntry.concert_id == Contract.concert_id,
                    FinanceEntry.status == "POSTED",
                    FinanceEntry.occurred_on <= as_of,
                ),
            )
            .where(Contract.concert_id == concert_id, Contract.signed_on <= as_of)
            .group_by(Contract.id)
            .order_by(Contract.id)
        ).all()

    def ranking(self, period: Period):
        scores = (
            select(
                Concert.id.label("concert_id"),
                Concert.name,
                Concert.starts_at,
                _sum_amount(FinanceEntry.direction == "IN").label("income"),
                _sum_amount(FinanceEntry.direction == "OUT").label("expenses"),
            )
            .outerjoin(
                FinanceEntry,
                and_(
                    FinanceEntry.concert_id == Concert.id,
                    FinanceEntry.status == "POSTED",
                    FinanceEntry.occurred_on.between(
                        period.date_from, min(period.date_to, period.as_of)
                    ),
                ),
            )
            .where(
                Concert.status == "COMPLETED",
                _utc_date(Concert.starts_at).between(period.date_from, period.date_to),
            )
            .group_by(Concert.id)
            .subquery()
        )
        net = scores.c.income - scores.c.expenses
        tie = (scores.c.starts_at, scores.c.concert_id)
        ranked = select(
            scores,
            net.label("net"),
            func.count().over().label("total"),
            func.row_number().over(order_by=(net.desc(), *tie)).label("best_rank"),
            func.row_number().over(order_by=(net.asc(), *tie)).label("worst_rank"),
        ).subquery()
        return (
            self.session.execute(
                select(ranked).where(or_(ranked.c.best_rank <= 3, ranked.c.worst_rank <= 3))
            )
            .mappings()
            .all()
        )

    def historical_expenses(self, period: Period):
        original = aliased(FinanceEntry)
        posted_count = func.count(FinanceEntry.id).filter(FinanceEntry.status == "POSTED")
        draft_expenses = func.count(FinanceEntry.id).filter(
            FinanceEntry.status == "DRAFT",
            or_(FinanceEntry.direction == "OUT", original.direction == "OUT"),
        )
        return self.session.execute(
            select(
                Concert.id,
                Concert.expense_budget,
                _actual_expenses(original),
                posted_count,
                draft_expenses,
            )
            .outerjoin(
                FinanceEntry,
                and_(
                    FinanceEntry.concert_id == Concert.id,
                    FinanceEntry.occurred_on <= period.as_of,
                ),
            )
            .outerjoin(original, original.id == FinanceEntry.original_id)
            .where(
                Concert.status == "COMPLETED",
                Concert.expense_budget > 0,
                _utc_date(Concert.starts_at).between(period.date_from, period.date_to),
                _utc_date(Concert.ends_at) <= period.as_of,
            )
            .group_by(Concert.id)
            .order_by(Concert.id)
        ).all()
