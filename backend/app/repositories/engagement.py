from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.entities import Engagement


class EngagementRepository:
    def __init__(self, session: Session):
        self.session = session

    def get(self, identity: int, *, lock: bool = False) -> Engagement | None:
        statement = select(Engagement).where(Engagement.id == identity)
        if lock:
            statement = statement.with_for_update().execution_options(populate_existing=True)
        return self.session.scalar(statement)

    def list_for_concert(self, concert_id: int, *, limit: int, offset: int):
        scope = Engagement.concert_id == concert_id
        total = self.session.scalar(select(func.count()).select_from(Engagement).where(scope))
        rows = self.session.scalars(
            select(Engagement).where(scope).order_by(Engagement.id).limit(limit).offset(offset)
        ).all()
        return rows, total

    def add(self, row: Engagement) -> None:
        self.session.add(row)
        self.session.flush()
