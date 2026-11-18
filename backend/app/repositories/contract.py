from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.entities import Contract, Counterparty, Engagement
from app.schemas.contract import ContractFilter


class ContractRepository:
    def __init__(self, session: Session):
        self.session = session

    def get(self, identity: int, *, lock: bool = False) -> Contract | None:
        statement = select(Contract).where(Contract.id == identity)
        if lock:
            statement = statement.with_for_update().execution_options(populate_existing=True)
        return self.session.scalar(statement)

    def add(self, row: Contract) -> None:
        self.session.add(row)
        self.session.flush()

    def linked_engagement(self, contract_id: int) -> Engagement | None:
        return self.session.scalar(select(Engagement).where(Engagement.contract_id == contract_id))

    def active_main(self, concert_id: int) -> Contract | None:
        return self.session.scalars(
            select(Contract)
            .where(
                Contract.concert_id == concert_id,
                Contract.kind == "MAIN_SHOW",
                Contract.status == "ACTIVE",
            )
            .with_for_update(read=True)
            .execution_options(populate_existing=True)
        ).one_or_none()

    def list(self, filters: ContractFilter):
        statement = select(Contract)
        if filters.number is not None:
            statement = statement.where(
                func.lower(Contract.number.collate("pg_unicode_fast")).contains(
                    filters.number.lower(), autoescape=True
                )
            )
        if filters.counterparty is not None:
            statement = statement.join(Counterparty, Contract.counterparty_id == Counterparty.id)
            statement = statement.where(
                func.lower(Counterparty.name.collate("pg_unicode_fast")).contains(
                    filters.counterparty.lower(), autoescape=True
                )
            )
        if filters.concert_id is not None:
            statement = statement.where(Contract.concert_id == filters.concert_id)
        total = self.session.scalar(select(func.count()).select_from(statement.subquery()))
        rows = self.session.scalars(
            statement.order_by(Contract.id).limit(filters.limit).offset(filters.offset)
        ).all()
        return rows, total
