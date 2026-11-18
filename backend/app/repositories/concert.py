from datetime import datetime

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.models.entities import (
    Account,
    AccountRole,
    Concert,
    Employee,
    Role,
    Venue,
)
from app.schemas.concert import ConcertFilter

# One artist: every concert writer must acquire this lock BEFORE any concert row lock.
# Future contract/assignment services must follow the same protocol when changing prerequisites.
CONCERT_SCHEDULE_LOCK = 810004


class ConcertRepository:
    def __init__(self, session: Session):
        self.session = session

    def lock_schedule(self):
        self.session.execute(
            text("SELECT pg_advisory_xact_lock(:key)"), {"key": CONCERT_SCHEDULE_LOCK}
        )

    def get(self, identity: int, *, lock: bool = False):
        statement = select(Concert).where(Concert.id == identity)
        if lock:
            statement = statement.with_for_update().execution_options(populate_existing=True)
        return self.session.scalar(statement)

    def list(self, filters: ConcertFilter):
        conditions = []
        if filters.starts_from is not None:
            conditions.append(Concert.starts_at >= filters.starts_from)
        if filters.starts_before is not None:
            conditions.append(Concert.starts_at < filters.starts_before)
        if filters.city is not None:
            conditions.append(
                func.lower(Venue.city.collate("pg_unicode_fast")).contains(
                    filters.city.lower(), autoescape=True
                )
            )
        if filters.status is not None:
            conditions.append(Concert.status == filters.status)
        if filters.q is not None:
            conditions.append(
                func.lower(Concert.name.collate("pg_unicode_fast")).contains(
                    filters.q.lower(), autoescape=True
                )
            )
        statement = (
            select(Concert).outerjoin(Venue, Concert.venue_id == Venue.id).where(*conditions)
        )
        total = self.session.scalar(select(func.count()).select_from(statement.subquery()))
        items = self.session.scalars(
            statement.order_by(Concert.starts_at, Concert.id)
            .limit(filters.limit)
            .offset(filters.offset)
        ).all()
        return items, total

    def reference(self, model, identity: int):
        return self.session.scalar(
            select(model)
            .where(model.id == identity)
            .with_for_update(read=True)
            .execution_options(populate_existing=True)
        )

    def responsible_is_manager(self, identity: int) -> bool:
        statement = (
            select(Employee.id)
            .join(Account, Account.employee_id == Employee.id)
            .join(AccountRole, AccountRole.account_id == Account.id)
            .join(Role, Role.id == AccountRole.role_id)
            .where(
                Employee.id == identity,
                Employee.active.is_(True),
                Account.active.is_(True),
                Role.code == "MANAGER",
            )
            .with_for_update(read=True)
        )
        return self.session.scalar(statement) is not None

    def list_responsibles(self, limit: int, offset: int):
        query = (
            select(Employee.id, Employee.full_name)
            .join(Account, Account.employee_id == Employee.id)
            .join(AccountRole, AccountRole.account_id == Account.id)
            .join(Role, Role.id == AccountRole.role_id)
            .where(Employee.active.is_(True), Account.active.is_(True), Role.code == "MANAGER")
        )
        total = self.session.scalar(select(func.count()).select_from(query.subquery()))
        rows = self.session.execute(
            query.order_by(Employee.full_name, Employee.id).limit(limit).offset(offset)
        )
        return rows, total

    def overlapping(self, identity: int, starts_at: datetime, ends_at: datetime):
        return self.session.scalar(
            select(Concert.id)
            .where(
                Concert.id != identity,
                Concert.status == "CONFIRMED",
                Concert.starts_at < ends_at,
                Concert.ends_at > starts_at,
            )
            .order_by(Concert.id)
            .limit(1)
        )

    def add(self, values: dict):
        row = Concert(**values)
        self.session.add(row)
        self.session.flush()
        return row
