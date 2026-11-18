from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Annotated, ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.catalog import Input, Patch, Version
from app.schemas.concert import Identity
from app.schemas.contract import Amount, CalendarDate, Direction

FinanceStatus = Literal["DRAFT", "POSTED", "VOID"]
RequestKey = Annotated[str, Field(min_length=1, max_length=80)]


class FinanceCreate(Input):
    concert_id: Identity
    contract_id: Identity | None = None
    category_id: Identity
    occurred_on: CalendarDate
    amount: Amount
    direction: Direction
    basis: str = Field(min_length=1)


class FinanceRegister(FinanceCreate):
    request_key: RequestKey


class FinanceUpdate(Patch):
    nullable_fields: ClassVar[frozenset[str]] = frozenset({"contract_id"})
    contract_id: Identity | None = None
    category_id: Identity | None = None
    occurred_on: CalendarDate | None = None
    amount: Amount | None = None
    direction: Direction | None = None
    basis: str | None = Field(default=None, min_length=1)


class FinancePost(Input):
    version: Version
    request_key: RequestKey


class FinanceVoid(Input):
    version: Version
    reason: str = Field(min_length=1)


class FinanceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    concert_id: int
    contract_id: int | None
    category_id: int
    occurred_on: date
    amount: Decimal
    direction: Direction
    basis: str
    original_id: int | None
    status: FinanceStatus
    void_reason: str | None
    created_by: int
    posted_at: datetime | None
    request_key: str | None
    created_at: datetime
    updated_at: datetime
    version: int

    @field_validator("posted_at", "created_at", "updated_at")
    @classmethod
    def utc(cls, value: datetime | None) -> datetime | None:
        return value.astimezone(UTC) if value is not None else None

    @field_validator("amount")
    @classmethod
    def cents(cls, value: Decimal) -> Decimal:
        return value.quantize(Decimal("0.01"))
