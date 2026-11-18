from contextlib import contextmanager
from datetime import UTC, datetime

from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.entities import AuditEvent, Contract, Counterparty
from app.repositories.concert import ConcertRepository
from app.repositories.contract import ContractRepository
from app.schemas.contract import (
    ContractActivate,
    ContractCreate,
    ContractFilter,
    ContractResponse,
    ContractUpdate,
)


class ContractError(Exception):
    def __init__(self, status: int, detail: str):
        self.status = status
        self.detail = detail


class ContractService:
    def __init__(self, session: Session):
        self.session = session
        self.repository = ContractRepository(session)
        self.concerts = ConcertRepository(session)

    @contextmanager
    def _write(self):
        try:
            # Match the concert writer order before acquiring any row locks.
            self.concerts.lock_schedule()
            yield
        except IntegrityError as exc:
            self.session.rollback()
            constraint = getattr(getattr(exc.orig, "diag", None), "constraint_name", None)
            if constraint == "uq_contract_identity":
                raise ContractError(
                    409, "Contract number already exists for this counterparty and date"
                ) from exc
            if constraint == "uq_contract_active_main":
                raise ContractError(409, "Concert already has an active main contract") from exc
            raise
        except Exception:
            self.session.rollback()
            raise

    def _draft(self, identity: int, version: int) -> Contract:
        row = self.repository.get(identity, lock=True)
        if row is None:
            raise ContractError(404, "Contract not found")
        if row.version != version:
            raise ContractError(409, "Version conflict; reload the contract")
        if row.status != "DRAFT":
            raise ContractError(409, "Only draft contracts can be edited or activated")
        return row

    def _validate(self, data: ContractCreate, *, new_counterparty: bool) -> None:
        concert = self.concerts.get(data.concert_id, lock=True)
        if concert is None:
            raise ContractError(422, "concert_id references a missing concert")
        party = self.concerts.reference(Counterparty, data.counterparty_id)
        if party is None:
            raise ContractError(422, "counterparty_id references a missing counterparty")
        if new_counterparty and party.archived:
            raise ContractError(409, "Cannot select an archived counterparty")
        if data.kind == "MAIN_SHOW" and data.counterparty_id != concert.proposed_organizer_id:
            raise ContractError(409, "Main contract must match the concert organizer")
        expected_direction = "IN" if data.kind == "MAIN_SHOW" else "OUT"
        if data.direction != expected_direction:
            raise ContractError(422, f"{data.kind} requires {expected_direction} direction")

    @staticmethod
    def _candidate(row: Contract, changes: dict) -> ContractCreate:
        values = {field: getattr(row, field) for field in ContractCreate.model_fields}
        try:
            return ContractCreate.model_validate(values | changes)
        except ValidationError as exc:
            field = exc.errors()[0]["loc"][0]
            raise ContractError(422, f"Invalid contract field: {field}") from exc

    def _save(self, row: Contract, actor: int, action: str, before: ContractResponse | None):
        result = ContractResponse.model_validate(row)
        self.session.add(
            AuditEvent(
                occurred_at=datetime.now(UTC),
                actor_id=actor,
                object_type="contract",
                object_id=row.id,
                action=action,
                before_data=before.model_dump(mode="json") if before else None,
                after_data=result.model_dump(mode="json"),
            )
        )
        self.session.commit()
        return result

    def get(self, identity: int) -> ContractResponse:
        row = self.repository.get(identity)
        if row is None:
            raise ContractError(404, "Contract not found")
        return ContractResponse.model_validate(row)

    def list(self, filters: ContractFilter):
        rows, total = self.repository.list(filters)
        return {
            "items": [ContractResponse.model_validate(row) for row in rows],
            "total": total,
            "limit": filters.limit,
            "offset": filters.offset,
        }

    def create(self, data: ContractCreate, actor: int) -> ContractResponse:
        with self._write():
            self._validate(data, new_counterparty=True)
            now = datetime.now(UTC)
            row = Contract(
                **data.model_dump(), status="DRAFT", version=1, created_at=now, updated_at=now
            )
            self.repository.add(row)
            return self._save(row, actor, "CREATE", None)

    def update(self, identity: int, data: ContractUpdate, actor: int) -> ContractResponse:
        with self._write():
            row = self._draft(identity, data.version)
            before = ContractResponse.model_validate(row)
            changes = data.model_dump(exclude_unset=True, exclude={"version"})
            candidate = self._candidate(row, changes)
            self._validate(
                candidate, new_counterparty=candidate.counterparty_id != row.counterparty_id
            )
            engagement = self.repository.linked_engagement(identity)
            if engagement is not None and (
                candidate.kind != "SERVICE"
                or candidate.counterparty_id != engagement.counterparty_id
                or candidate.amount != engagement.agreed_amount
            ):
                raise ContractError(409, "Draft changes must preserve the linked engagement")
            for field, value in changes.items():
                setattr(row, field, value)
            row.version += 1
            row.updated_at = datetime.now(UTC)
            return self._save(row, actor, "UPDATE", before)

    def activate(self, identity: int, data: ContractActivate, actor: int) -> ContractResponse:
        with self._write():
            row = self._draft(identity, data.version)
            candidate = self._candidate(row, {})
            self._validate(candidate, new_counterparty=False)
            before = ContractResponse.model_validate(row)
            if row.kind == "MAIN_SHOW" and self.repository.active_main(row.concert_id) is not None:
                raise ContractError(409, "Concert already has an active main contract")
            row.status = "ACTIVE"
            row.version += 1
            row.updated_at = datetime.now(UTC)
            return self._save(row, actor, "ACTIVATE", before)
