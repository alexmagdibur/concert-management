from contextlib import contextmanager
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.models.entities import AuditEvent, Counterparty, Employee, Venue
from app.repositories.concert import ConcertRepository
from app.schemas.concert import (
    ConcertCancel,
    ConcertCreate,
    ConcertFilter,
    ConcertResponse,
    ConcertTransition,
    ConcertUpdate,
)


class ConcertError(Exception):
    def __init__(self, status: int, detail: str):
        self.status = status
        self.detail = detail


class ConcertService:
    def __init__(self, session: Session):
        self.session = session
        self.repository = ConcertRepository(session)

    @contextmanager
    def _write(self):
        try:
            self.repository.lock_schedule()
            # Validate merged candidates before flushing any changes.
            with self.session.no_autoflush:
                yield
        except Exception:
            self.session.rollback()
            raise

    def _locked(self, identity: int, version: int):
        row = self.repository.get(identity, lock=True)
        if row is None:
            raise ConcertError(404, "Concert not found")
        if row.version != version:
            raise ConcertError(409, "Version conflict; reload the concert")
        return row

    def _validate_refs(self, values: dict, *, changed: set[str]):
        for field, model in [
            ("venue_id", Venue),
            ("proposed_organizer_id", Counterparty),
            ("responsible_id", Employee),
        ]:
            if field not in changed or values[field] is None:
                continue
            reference = self.repository.reference(model, values[field])
            if reference is None:
                raise ConcertError(422, f"{field} references a missing record")
            if field == "responsible_id":
                if not self.repository.responsible_is_manager(values[field]):
                    raise ConcertError(409, "Responsible employee must be an active manager")
            elif reference.archived:
                raise ConcertError(409, f"{field} cannot select an archived record")

    @staticmethod
    def _validate_main_organizer(values: dict, contracts):
        if contracts and (
            values["proposed_organizer_id"] is None
            or any(
                contract.counterparty_id != values["proposed_organizer_id"]
                for contract in contracts
            )
        ):
            raise ConcertError(409, "Main contract must match the concert organizer")

    def _validate_confirmed(self, values: dict, identity: int):
        if values["venue_id"] is None:
            raise ConcertError(409, "Confirmation requires a venue")
        if self.repository.reference(Venue, values["venue_id"]) is None:
            raise ConcertError(409, "Confirmation requires an existing venue")
        if not self.repository.responsible_is_manager(values["responsible_id"]):
            raise ConcertError(409, "Confirmation requires an active responsible manager")
        contracts = self.repository.active_main_contracts(identity)
        if len(contracts) != 1:
            raise ConcertError(409, "Confirmation requires exactly one ACTIVE MAIN_SHOW contract")
        contract = contracts[0]
        self._validate_main_organizer(values, contracts)
        if contract.direction != "IN":
            raise ConcertError(409, "Main show contract must have IN direction")
        if (
            self.repository.overlapping(identity, values["starts_at"], values["ends_at"])
            is not None
        ):
            raise ConcertError(409, "Concert overlaps another confirmed concert")

    def _save(self, row, actor_id: int, action: str, before, *, reason=None):
        self.session.flush()
        result = ConcertResponse.model_validate(row)
        self.session.add(
            AuditEvent(
                occurred_at=datetime.now(UTC),
                actor_id=actor_id,
                object_type="concert",
                object_id=row.id,
                action=action,
                before_data=before,
                after_data=result.model_dump(mode="json"),
                reason=reason,
            )
        )
        self.session.flush()
        self.session.commit()
        return result

    def get(self, identity: int) -> ConcertResponse:
        row = self.repository.get(identity)
        if row is None:
            raise ConcertError(404, "Concert not found")
        return ConcertResponse.model_validate(row)

    def list(self, filters: ConcertFilter):
        rows, total = self.repository.list(filters)
        return {
            "items": [ConcertResponse.model_validate(row) for row in rows],
            "total": total,
            "limit": filters.limit,
            "offset": filters.offset,
        }

    def create(self, payload: ConcertCreate, actor_id: int) -> ConcertResponse:
        with self._write():
            values = payload.model_dump()
            self._validate_refs(values, changed=set(values))
            now = datetime.now(UTC)
            row = self.repository.add(
                dict(
                    values,
                    status="NEGOTIATING",
                    cancel_reason=None,
                    version=1,
                    created_at=now,
                    updated_at=now,
                )
            )
            return self._save(row, actor_id, "CREATE", None)

    def update(self, identity: int, payload: ConcertUpdate, actor_id: int) -> ConcertResponse:
        with self._write():
            row = self._locked(identity, payload.version)
            before = ConcertResponse.model_validate(row).model_dump(mode="json")
            changes = payload.model_dump(exclude_unset=True, exclude={"version"})
            candidate = {column.name: getattr(row, column.name) for column in row.__table__.columns}
            candidate.update(changes)
            if candidate["ends_at"] <= candidate["starts_at"]:
                raise ConcertError(422, "ends_at must be later than starts_at")
            changed = {name for name in changes if candidate[name] != getattr(row, name)}
            self._validate_refs(candidate, changed=changed)
            if row.status == "CONFIRMED":
                self._validate_confirmed(candidate, identity)
            elif "proposed_organizer_id" in changed:
                self._validate_main_organizer(
                    candidate, self.repository.active_main_contracts(identity)
                )
            if row.status == "COMPLETED":
                if candidate["venue_id"] is None or candidate["proposed_organizer_id"] is None:
                    raise ConcertError(409, "Completed concert must retain its venue and organizer")
                if candidate["ends_at"] > datetime.now(UTC):
                    raise ConcertError(409, "Completed concert cannot end in the future")
            for key, value in changes.items():
                setattr(row, key, value)
            row.version += 1
            row.updated_at = datetime.now(UTC)
            return self._save(row, actor_id, "UPDATE", before)

    def transition(
        self, identity: int, payload: ConcertTransition, actor_id: int, target: str
    ) -> ConcertResponse:
        allowed = {
            "CONFIRMED": {"NEGOTIATING"},
            "COMPLETED": {"CONFIRMED"},
            "CANCELLED": {"NEGOTIATING", "CONFIRMED"},
        }
        with self._write():
            row = self._locked(identity, payload.version)
            if target not in allowed or row.status not in allowed[target]:
                raise ConcertError(409, "Invalid concert state transition")
            before = ConcertResponse.model_validate(row).model_dump(mode="json")
            if target == "CONFIRMED":
                self._validate_confirmed(
                    {column.name: getattr(row, column.name) for column in row.__table__.columns},
                    identity,
                )
            if target == "COMPLETED" and row.ends_at > datetime.now(UTC):
                raise ConcertError(409, "Cannot complete a concert before it has ended")
            reason = None
            if target == "CANCELLED":
                if not isinstance(payload, ConcertCancel) or not payload.reason.strip():
                    raise ConcertError(422, "Cancellation requires a reason")
                reason = payload.reason
                row.cancel_reason = reason
            row.status = target
            row.version += 1
            row.updated_at = datetime.now(UTC)
            return self._save(row, actor_id, target, before, reason=reason)
