from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated, ClassVar, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.catalog import Input, Patch, Version

Identity = Annotated[int, Field(strict=True, ge=-9223372036854775808, le=9223372036854775807)]
Budget = Annotated[Decimal, Field(ge=0, max_digits=14, decimal_places=2, allow_inf_nan=False)]
ConcertStatus = Literal["NEGOTIATING", "CONFIRMED", "COMPLETED", "CANCELLED"]


class ConcertCreate(Input):
    name: str = Field(min_length=1, max_length=200)
    starts_at: AwareDatetime
    ends_at: AwareDatetime
    venue_id: Identity | None = None
    proposed_organizer_id: Identity | None = None
    responsible_id: Identity
    expense_budget: Budget

    @model_validator(mode="after")
    def validate_interval(self):
        if self.ends_at <= self.starts_at:
            raise ValueError("ends_at must be later than starts_at")
        return self


class ConcertUpdate(Patch):
    nullable_fields: ClassVar[frozenset[str]] = frozenset({"venue_id", "proposed_organizer_id"})
    name: str | None = Field(default=None, min_length=1, max_length=200)
    starts_at: AwareDatetime | None = None
    ends_at: AwareDatetime | None = None
    venue_id: Identity | None = None
    proposed_organizer_id: Identity | None = None
    responsible_id: Identity | None = None
    expense_budget: Budget | None = None

    @model_validator(mode="after")
    def validate_interval(self):
        if (
            self.starts_at is not None
            and self.ends_at is not None
            and self.ends_at <= self.starts_at
        ):
            raise ValueError("ends_at must be later than starts_at")
        return self


class ConcertTransition(Input):
    version: Version


class ConcertCancel(ConcertTransition):
    reason: str = Field(min_length=1)


class ConcertFilter(Input):
    starts_from: AwareDatetime | None = None
    starts_before: AwareDatetime | None = None
    city: str | None = Field(default=None, min_length=1, max_length=100)
    q: str | None = Field(default=None, min_length=1, max_length=200)
    status: ConcertStatus | None = None
    limit: int = Field(default=20, ge=1, le=100)
    offset: int = Field(default=0, ge=0, le=9223372036854775807)

    @model_validator(mode="after")
    def validate_period(self):
        if (
            self.starts_from is not None
            and self.starts_before is not None
            and self.starts_before <= self.starts_from
        ):
            raise ValueError("starts_before must be later than starts_from")
        return self


class ResponsibleOption(BaseModel):
    id: int
    full_name: str


class ConcertResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    starts_at: datetime
    ends_at: datetime
    venue_id: int | None
    proposed_organizer_id: int | None
    responsible_id: int
    expense_budget: Decimal
    status: ConcertStatus
    cancel_reason: str | None
    created_at: datetime
    updated_at: datetime
    version: int

    @field_validator("starts_at", "ends_at", "created_at", "updated_at")
    @classmethod
    def normalize_utc(cls, value: datetime) -> datetime:
        return value.astimezone(UTC)

    @field_validator("expense_budget")
    @classmethod
    def format_budget(cls, value: Decimal) -> Decimal:
        return value.quantize(Decimal("0.01"))
