import re
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, field_validator

from app.schemas.catalog import Input, Patch, Version
from app.schemas.concert import Identity

Kind = Literal["MAIN_SHOW", "SERVICE"]
Direction = Literal["IN", "OUT"]
Amount = Annotated[Decimal, Field(gt=0, max_digits=14, decimal_places=2, allow_inf_nan=False)]


def require_calendar_date(value):
    if type(value) is date or (
        isinstance(value, str) and re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value)
    ):
        return value
    raise ValueError("Use a calendar date in YYYY-MM-DD format")


CalendarDate = Annotated[date, BeforeValidator(require_calendar_date)]


class ContractCreate(Input):
    number: str = Field(min_length=1, max_length=80)
    signed_on: CalendarDate
    concert_id: Identity
    counterparty_id: Identity
    kind: Kind
    subject: str = Field(min_length=1)
    amount: Amount
    direction: Direction


class ContractUpdate(Patch):
    number: str | None = Field(default=None, min_length=1, max_length=80)
    signed_on: CalendarDate | None = None
    counterparty_id: Identity | None = None
    kind: Kind | None = None
    subject: str | None = Field(default=None, min_length=1)
    amount: Amount | None = None
    direction: Direction | None = None


class ContractActivate(Input):
    version: Version


class ContractFilter(Input):
    number: str | None = Field(default=None, min_length=1, max_length=80)
    counterparty: str | None = Field(default=None, min_length=1, max_length=200)
    concert_id: int | None = Field(default=None, ge=-9223372036854775808, le=9223372036854775807)
    limit: int = Field(default=20, ge=1, le=100)
    offset: int = Field(default=0, ge=0, le=9223372036854775807)


class ContractResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    number: str
    signed_on: date
    concert_id: int
    counterparty_id: int
    kind: Kind
    subject: str
    amount: Decimal
    direction: Direction
    status: str
    close_reason: str | None
    version: int
    created_at: datetime
    updated_at: datetime

    @field_validator("created_at", "updated_at")
    @classmethod
    def utc(cls, value: datetime) -> datetime:
        return value.astimezone(UTC)

    @field_validator("amount")
    @classmethod
    def cents(cls, value: Decimal) -> Decimal:
        return value.quantize(Decimal("0.01"))
