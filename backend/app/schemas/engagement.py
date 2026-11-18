from datetime import UTC, datetime
from decimal import Decimal
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator

from app.schemas.catalog import Input, Version
from app.schemas.concert import Identity
from app.schemas.contract import Amount

EngagementStatus = Literal["PLANNED", "AGREED", "COMPLETED", "CANCELLED"]


class EngagementCreate(Input):
    concert_id: Identity
    counterparty_id: Identity
    description: str = Field(min_length=1)
    due_at: AwareDatetime
    agreed_amount: Amount


class EngagementTransition(Input):
    version: Version


class EngagementAgree(EngagementTransition):
    contract_id: Identity


class EngagementCancel(EngagementTransition):
    reason: str | None = Field(default=None, min_length=1)


class EngagementResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    concert_id: int
    counterparty_id: int
    description: str
    due_at: datetime
    agreed_amount: Decimal
    contract_id: int | None
    status: EngagementStatus
    cancel_reason: str | None
    version: int
    created_at: datetime
    updated_at: datetime

    @field_validator("due_at", "created_at", "updated_at")
    @classmethod
    def utc(cls, value: datetime) -> datetime:
        return value.astimezone(UTC)

    @field_validator("agreed_amount")
    @classmethod
    def cents(cls, value: Decimal) -> Decimal:
        return value.quantize(Decimal("0.01"))
