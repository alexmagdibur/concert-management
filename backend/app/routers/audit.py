from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from pydantic import BaseModel, ConfigDict, field_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.database import get_session
from app.core.security import Identity, require_identity
from app.models.entities import (
    Account,
    AuditEvent,
    Concert,
    Contract,
    Counterparty,
    Employee,
    Engagement,
    FinanceCategory,
    FinanceEntry,
    Role,
    Venue,
)
from app.schemas.catalog import Page

router = APIRouter(prefix="/audit", tags=["audit"])
DB = Annotated[Session, Depends(get_session)]
Current = Annotated[Identity, Depends(require_identity)]
ObjectType = Literal[
    "employee",
    "account",
    "role",
    "venue",
    "counterparty",
    "concert",
    "contract",
    "engagement",
    "finance_category",
    "finance_entry",
]
MODELS = {
    model.__tablename__: model
    for model in (
        Account,
        Concert,
        Contract,
        Counterparty,
        Employee,
        Engagement,
        FinanceCategory,
        FinanceEntry,
        Role,
        Venue,
    )
}
SENSITIVE = {"password", "password_hash", "session_tokens", "token", "session_token", "csrf_token"}


def _redact(value):
    if isinstance(value, dict):
        return {key: _redact(item) for key, item in value.items() if key.lower() not in SENSITIVE}
    if isinstance(value, list):
        return [_redact(item) for item in value]
    return value


class AuditResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    occurred_at: datetime
    actor_id: int
    object_type: str
    object_id: int
    action: str
    before_data: dict | None
    after_data: dict | None
    reason: str | None

    @field_validator("before_data", "after_data", mode="before")
    @classmethod
    def redact(cls, value):
        return _redact(value)


@router.get("/{object_type}/{object_id}", response_model=Page[AuditResponse])
def history(
    object_type: ObjectType,
    object_id: Annotated[int, Path(ge=-(2**63), lt=2**63)],
    session: DB,
    identity: Current,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0, lt=2**63)] = 0,
):
    role = "ADMIN" if object_type in {"employee", "account", "role"} else "MANAGER"
    if role not in identity.roles:
        raise HTTPException(403, "Object history is forbidden")
    if session.get(MODELS[object_type], object_id) is None:
        raise HTTPException(404, "Object not found")
    query = select(AuditEvent).where(
        AuditEvent.object_type == object_type, AuditEvent.object_id == object_id
    )
    total = session.scalar(select(func.count()).select_from(query.subquery()))
    rows = session.scalars(
        query.order_by(AuditEvent.occurred_at.desc(), AuditEvent.id.desc())
        .offset(offset)
        .limit(limit)
    )
    return Page[AuditResponse](
        items=[AuditResponse.model_validate(row) for row in rows],
        total=total,
        limit=limit,
        offset=offset,
    )
