from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session


class CatalogRepository:
    model = None
    search_fields = ()
    identity_fields = ()
    lock_key = 0

    def __init__(self, session: Session):
        self.session = session

    def get(self, identity: int, *, lock: bool = False):
        statement = select(self.model).where(self.model.id == identity)
        if lock:
            statement = statement.with_for_update()
        return self.session.scalar(statement)

    def list(self, *, q: str | None, archived: bool, limit: int, offset: int):
        conditions = [self.model.archived == archived]
        if q:
            conditions.append(
                or_(
                    *(
                        func.lower(getattr(self.model, field).collate("pg_unicode_fast")).contains(
                            q.lower(), autoescape=True
                        )
                        for field in self.search_fields
                    )
                )
            )
        total = self.session.scalar(select(func.count()).select_from(self.model).where(*conditions))
        items = self.session.scalars(
            select(self.model)
            .where(*conditions)
            .order_by(self.model.id)
            .limit(limit)
            .offset(offset)
        ).all()
        return items, total

    def duplicate(self, values: dict, excluding: int | None = None) -> bool:
        # Compare Unicode casefolded identities, including archived rows.
        # A module-level transaction lock serializes all catalog API writers.
        statement = select(*(getattr(self.model, field) for field in self.identity_fields))
        if excluding is not None:
            statement = statement.where(self.model.id != excluding)
        key = tuple(values[field].strip().casefold() for field in self.identity_fields)
        return any(
            tuple(value.strip().casefold() for value in row) == key
            for row in self.session.execute(statement)
        )

    def add(self, values: dict):
        row = self.model(**values)
        self.session.add(row)
        self.session.flush()
        return row
