from contextlib import contextmanager
from datetime import UTC, datetime

from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.entities import AuditEvent, Concert, Contract, FinanceCategory, FinanceEntry
from app.repositories.concert import ConcertRepository
from app.repositories.finance import FinanceRepository
from app.schemas.finance import (
    FinanceCreate,
    FinancePost,
    FinanceRegister,
    FinanceResponse,
    FinanceUpdate,
    FinanceVoid,
)


class FinanceError(Exception):
    def __init__(self, status: int, detail: str):
        self.status = status
        self.detail = detail


class FinanceService:
    def __init__(self, session: Session):
        self.session = session
        self.repository = FinanceRepository(session)
        self.concerts = ConcertRepository(session)

    @contextmanager
    def _write(self):
        try:
            yield
        except IntegrityError as exc:
            self.session.rollback()
            constraint = getattr(getattr(exc.orig, "diag", None), "constraint_name", None)
            if constraint == "finance_entry_request_key_key":
                raise FinanceError(409, "Request key is already in use") from exc
            raise
        except Exception:
            self.session.rollback()
            raise

    def _validate(self, data: FinanceCreate) -> None:
        if data.occurred_on > datetime.now(UTC).date():
            raise FinanceError(422, "occurred_on cannot be in the future")
        if data.contract_id is not None:
            contract = self.concerts.reference(Contract, data.contract_id)
            if contract is None or contract.concert_id != data.concert_id:
                raise FinanceError(422, "Contract must belong to the operation's concert")
            if contract.direction != data.direction:
                raise FinanceError(422, "Contract direction must match operation direction")

        if self.concerts.reference(Concert, data.concert_id) is None:
            raise FinanceError(422, "concert_id references a missing concert")
        category = self.concerts.reference(FinanceCategory, data.category_id)
        if category is None or category.archived:
            raise FinanceError(422, "Select an existing, non-archived category")
        if category.normal_direction != data.direction:
            raise FinanceError(422, "Category direction must match operation direction")

    def _locked(self, identity: int, version: int, status: str) -> FinanceEntry:
        row = self.repository.get(identity, lock=True)
        if row is None:
            raise FinanceError(404, "Finance entry not found")
        if row.version != version:
            raise FinanceError(409, "Version conflict; reload the finance entry")
        if row.status != status:
            raise FinanceError(409, f"Operation requires status {status}")
        return row

    @staticmethod
    def _candidate(row: FinanceEntry, changes: dict) -> FinanceCreate:
        values = {field: getattr(row, field) for field in FinanceCreate.model_fields}
        try:
            return FinanceCreate.model_validate(values | changes)
        except ValidationError as exc:
            field = exc.errors()[0]["loc"][0]
            raise FinanceError(422, f"Invalid finance entry field: {field}") from exc

    def _save(
        self,
        row: FinanceEntry,
        actor: int,
        action: str,
        before: FinanceResponse | None,
        *,
        reason: str | None = None,
    ) -> FinanceResponse:
        result = FinanceResponse.model_validate(row)
        self.session.add(
            AuditEvent(
                occurred_at=datetime.now(UTC),
                actor_id=actor,
                object_type="finance_entry",
                object_id=row.id,
                action=action,
                before_data=before.model_dump(mode="json") if before else None,
                after_data=result.model_dump(mode="json"),
                reason=reason,
            )
        )
        self.session.commit()
        return result

    def _create(self, values: dict, actor: int, *, key: str | None = None) -> FinanceResponse:
        now = datetime.now(UTC)
        row = FinanceEntry(
            **values,
            created_by=actor,
            created_at=now,
            updated_at=now,
            version=1,
            status="POSTED" if key else "DRAFT",
            posted_at=now if key else None,
            request_key=key,
        )
        self.repository.add(row)
        return self._save(row, actor, "POST" if key else "CREATE", None)

    def register(self, data: FinanceRegister, actor: int) -> tuple[FinanceResponse, bool]:
        with self._write():
            self.repository.lock_request_key(data.request_key)
            values = data.model_dump(exclude={"request_key"})
            existing = self.repository.by_request_key(data.request_key)
            if existing is not None:
                if (
                    existing.created_by != actor
                    or existing.original_id is not None
                    or existing.status not in {"POSTED", "VOID"}
                    or any(getattr(existing, name) != value for name, value in values.items())
                ):
                    raise FinanceError(409, "Request key is already in use for another operation")
                result = FinanceResponse.model_validate(existing)
                self.session.commit()
                return result, False
            self._validate(data)
            return self._create(values, actor, key=data.request_key), True

    def draft(self, data: FinanceCreate, actor: int) -> FinanceResponse:
        with self._write():
            self._validate(data)
            return self._create(data.model_dump(), actor)

    def update(self, identity: int, data: FinanceUpdate, actor: int) -> FinanceResponse:
        with self._write():
            row = self._locked(identity, data.version, "DRAFT")
            changes = data.model_dump(exclude_unset=True, exclude={"version"})
            self._validate(self._candidate(row, changes))
            before = FinanceResponse.model_validate(row)
            for field, value in changes.items():
                setattr(row, field, value)
            row.version += 1
            row.updated_at = datetime.now(UTC)
            return self._save(row, actor, "UPDATE", before)

    def post(self, identity: int, data: FinancePost, actor: int) -> FinanceResponse:
        with self._write():
            self.repository.lock_request_key(data.request_key)
            existing = self.repository.by_request_key(data.request_key)
            if existing is not None:
                if existing.id != identity or existing.status not in {"POSTED", "VOID"}:
                    raise FinanceError(409, "Request key is already in use for another operation")
                result = FinanceResponse.model_validate(existing)
                self.session.commit()
                return result
            row = self._locked(identity, data.version, "DRAFT")
            self._validate(self._candidate(row, {}))
            before = FinanceResponse.model_validate(row)
            row.status = "POSTED"
            row.posted_at = row.updated_at = datetime.now(UTC)
            row.request_key = data.request_key
            row.version += 1
            return self._save(row, actor, "POST", before)

    def void(self, identity: int, data: FinanceVoid, actor: int) -> FinanceResponse:
        with self._write():
            row = self._locked(identity, data.version, "POSTED")
            if self.repository.has_posted_refunds(identity):
                raise FinanceError(409, "Cannot void an entry with posted refunds")
            before = FinanceResponse.model_validate(row)
            row.status = "VOID"
            row.void_reason = data.reason
            row.version += 1
            row.updated_at = datetime.now(UTC)
            return self._save(row, actor, "VOID", before, reason=data.reason)

    def list_for_concert(self, concert_id: int, *, status: str | None, limit: int, offset: int):
        if self.concerts.get(concert_id) is None:
            raise FinanceError(404, "Concert not found")
        rows, total = self.repository.list_for_concert(
            concert_id, status=status, limit=limit, offset=offset
        )
        return {
            "items": [FinanceResponse.model_validate(row) for row in rows],
            "total": total,
            "limit": limit,
            "offset": offset,
        }
