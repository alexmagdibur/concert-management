from datetime import UTC, datetime

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.entities import AuditEvent


class CatalogError(Exception):
    def __init__(self, status: int, detail: str):
        self.status = status
        self.detail = detail


class CatalogService:
    repository_class = None
    response_class = None

    def __init__(self, session: Session):
        self.session = session
        self.repository = self.repository_class(session)

    def serialize(self, row):
        return self.response_class.model_validate(row)

    def get(self, identity: int):
        row = self.repository.get(identity)
        if row is None:
            raise CatalogError(404, "Record not found")
        return self.serialize(row)

    def list(self, **filters):
        items, total = self.repository.list(**filters)
        return {
            "items": [self.serialize(row) for row in items],
            "total": total,
            "limit": filters["limit"],
            "offset": filters["offset"],
        }

    def _lock(self):
        self.session.execute(
            text("SELECT pg_advisory_xact_lock(:key)"), {"key": self.repository.lock_key}
        )

    def _save(self, row, actor_id: int, action: str, before):
        self.session.flush()
        result = self.serialize(row)
        self.session.add(
            AuditEvent(
                occurred_at=datetime.now(UTC),
                actor_id=actor_id,
                object_type=self.repository.model.__tablename__,
                object_id=row.id,
                action=action,
                before_data=before,
                after_data=result.model_dump(mode="json"),
                reason="Directory archive" if action == "ARCHIVE" else None,
            )
        )
        self.session.flush()
        self.session.commit()
        return result

    def create(self, payload, actor_id: int):
        try:
            self._lock()
            values = payload.model_dump()
            if self.repository.duplicate(values):
                raise CatalogError(409, "Duplicate directory record")
            now = datetime.now(UTC)
            row = self.repository.add(
                dict(values, archived=False, version=1, created_at=now, updated_at=now)
            )
            return self._save(row, actor_id, "CREATE", None)
        except IntegrityError as exc:
            self.session.rollback()
            if exc.orig.sqlstate == "23505":
                raise CatalogError(409, "Duplicate directory record") from exc
            raise
        except Exception:
            self.session.rollback()
            raise

    def update(self, identity: int, payload, actor_id: int, *, archive: bool = False):
        try:
            self._lock()
            row = self.repository.get(identity, lock=True)
            if row is None:
                raise CatalogError(404, "Record not found")
            if row.version != payload.version:
                raise CatalogError(409, "Version conflict; reload the record")
            before = self.serialize(row).model_dump(mode="json")
            if archive and row.archived:
                return self.serialize(row)
            values = payload.model_dump(exclude_unset=True, exclude={"version"})
            merged = {column.name: getattr(row, column.name) for column in row.__table__.columns}
            merged.update(values)
            if not archive and self.repository.duplicate(merged, excluding=identity):
                raise CatalogError(409, "Duplicate directory record")
            for key, value in values.items():
                setattr(row, key, value)
            if archive:
                row.archived = True
            row.version += 1
            row.updated_at = datetime.now(UTC)
            return self._save(row, actor_id, "ARCHIVE" if archive else "UPDATE", before)
        except IntegrityError as exc:
            self.session.rollback()
            if exc.orig.sqlstate == "23505":
                raise CatalogError(409, "Duplicate directory record") from exc
            raise
        except Exception:
            self.session.rollback()
            raise
