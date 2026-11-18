from sqlalchemy import exists, func, select, text
from sqlalchemy.orm import Session

from app.models.entities import FinanceEntry


class FinanceRepository:
    def __init__(self, session: Session):
        self.session = session

    def lock_request_key(self, key: str) -> None:
        self.session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
            {"key": f"concert-crm:finance:{key}"},
        )

    def by_request_key(self, key: str) -> FinanceEntry | None:
        return self.session.scalar(select(FinanceEntry).where(FinanceEntry.request_key == key))

    def get(self, identity: int, *, lock: bool = False) -> FinanceEntry | None:
        statement = select(FinanceEntry).where(FinanceEntry.id == identity)
        if lock:
            statement = statement.with_for_update().execution_options(populate_existing=True)
        return self.session.scalar(statement)

    def add(self, row: FinanceEntry) -> None:
        self.session.add(row)
        self.session.flush()

    def has_posted_refunds(self, identity: int) -> bool:
        return bool(
            self.session.scalar(
                select(
                    exists().where(
                        FinanceEntry.original_id == identity,
                        FinanceEntry.status == "POSTED",
                    )
                )
            )
        )

    def list_for_concert(self, concert_id: int, *, status: str | None, limit: int, offset: int):
        statement = select(FinanceEntry).where(FinanceEntry.concert_id == concert_id)
        if status is not None:
            statement = statement.where(FinanceEntry.status == status)
        total = self.session.scalar(select(func.count()).select_from(statement.subquery()))
        rows = self.session.scalars(
            statement.order_by(FinanceEntry.occurred_on.desc(), FinanceEntry.id.desc())
            .limit(limit)
            .offset(offset)
        ).all()
        return rows, total
