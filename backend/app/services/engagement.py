from contextlib import contextmanager
from datetime import UTC, datetime

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.entities import AuditEvent, Concert, Counterparty, Engagement
from app.repositories.concert import ConcertRepository
from app.repositories.contract import ContractRepository
from app.repositories.engagement import EngagementRepository
from app.schemas.engagement import (
    EngagementAgree,
    EngagementCancel,
    EngagementCreate,
    EngagementResponse,
    EngagementTransition,
)


class EngagementError(Exception):
    def __init__(self, status: int, detail: str):
        self.status = status
        self.detail = detail


class EngagementService:
    def __init__(self, session: Session):
        self.session = session
        self.repository = EngagementRepository(session)
        self.concerts = ConcertRepository(session)
        self.contracts = ContractRepository(session)

    @contextmanager
    def _write(self):
        try:
            yield
        except IntegrityError as exc:
            self.session.rollback()
            constraint = getattr(getattr(exc.orig, "diag", None), "constraint_name", None)
            if constraint == "engagement_contract_id_key":
                raise EngagementError(
                    409, "Contract is already linked to another engagement"
                ) from exc
            raise
        except Exception:
            self.session.rollback()
            raise

    def _save(
        self,
        row: Engagement,
        actor: int,
        action: str,
        before: EngagementResponse | None,
        *,
        reason: str | None = None,
    ) -> EngagementResponse:
        result = EngagementResponse.model_validate(row)
        self.session.add(
            AuditEvent(
                occurred_at=datetime.now(UTC),
                actor_id=actor,
                object_type="engagement",
                object_id=row.id,
                action=action,
                before_data=before.model_dump(mode="json") if before else None,
                after_data=result.model_dump(mode="json"),
                reason=reason,
            )
        )
        self.session.commit()
        return result

    def _for_transition(self, identity: int, version: int, *allowed: str) -> Engagement:
        row = self.repository.get(identity, lock=True)
        if row is None:
            raise EngagementError(404, "Engagement not found")
        if row.version != version:
            raise EngagementError(409, "Version conflict; reload the engagement")
        if row.status not in allowed:
            raise EngagementError(409, "Invalid engagement state transition")
        return row

    def _change_state(self, row: Engagement, status: str) -> None:
        row.status = status
        row.version += 1
        row.updated_at = datetime.now(UTC)

    def create(self, data: EngagementCreate, actor: int) -> EngagementResponse:
        with self._write():
            if self.concerts.reference(Concert, data.concert_id) is None:
                raise EngagementError(422, "concert_id references a missing concert")
            party = self.concerts.reference(Counterparty, data.counterparty_id)
            if party is None:
                raise EngagementError(422, "counterparty_id references a missing counterparty")
            if party.archived:
                raise EngagementError(409, "Cannot select an archived counterparty")
            now = datetime.now(UTC)
            row = Engagement(
                **data.model_dump(), status="PLANNED", version=1, created_at=now, updated_at=now
            )
            self.repository.add(row)
            return self._save(row, actor, "CREATE", None)

    def list_for_concert(self, concert_id: int, *, limit: int, offset: int):
        if self.concerts.get(concert_id) is None:
            raise EngagementError(404, "Concert not found")
        rows, total = self.repository.list_for_concert(concert_id, limit=limit, offset=offset)
        return {
            "items": [EngagementResponse.model_validate(row) for row in rows],
            "total": total,
            "limit": limit,
            "offset": offset,
        }

    def agree(self, identity: int, data: EngagementAgree, actor: int) -> EngagementResponse:
        with self._write():
            row = self._for_transition(identity, data.version, "PLANNED")
            # Hold the contract stable until the link and the audit event are committed.
            contract = self.contracts.get(data.contract_id, lock=True)
            if contract is None:
                raise EngagementError(422, "contract_id references a missing contract")
            if contract.kind != "SERVICE" or contract.direction != "OUT":
                raise EngagementError(409, "Agreement requires an outgoing service contract")
            for field, expected in (
                ("concert_id", row.concert_id),
                ("counterparty_id", row.counterparty_id),
                ("amount", row.agreed_amount),
            ):
                if getattr(contract, field) != expected:
                    raise EngagementError(409, f"Contract {field} does not match the engagement")
            before = EngagementResponse.model_validate(row)
            row.contract_id = contract.id
            self._change_state(row, "AGREED")
            return self._save(row, actor, "AGREE", before)

    def complete(self, identity: int, data: EngagementTransition, actor: int) -> EngagementResponse:
        with self._write():
            row = self._for_transition(identity, data.version, "AGREED")
            before = EngagementResponse.model_validate(row)
            self._change_state(row, "COMPLETED")
            return self._save(row, actor, "COMPLETE", before)

    def cancel(self, identity: int, data: EngagementCancel, actor: int) -> EngagementResponse:
        with self._write():
            row = self._for_transition(identity, data.version, "PLANNED", "AGREED")
            before = EngagementResponse.model_validate(row)
            self._change_state(row, "CANCELLED")
            row.cancel_reason = data.reason
            return self._save(row, actor, "CANCEL", before, reason=data.reason)
