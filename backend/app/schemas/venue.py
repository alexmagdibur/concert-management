from typing import ClassVar

from pydantic import Field

from app.schemas.catalog import Input, Patch, Record


class VenueCreate(Input):
    name: str = Field(min_length=1, max_length=200)
    city: str = Field(min_length=1, max_length=100)
    address: str = Field(min_length=1, max_length=300)
    capacity: int | None = Field(default=None, strict=True, ge=0, le=2147483647)


class VenueUpdate(Patch):
    nullable_fields: ClassVar[frozenset[str]] = frozenset(["capacity"])
    name: str | None = Field(default=None, min_length=1, max_length=200)
    city: str | None = Field(default=None, min_length=1, max_length=100)
    address: str | None = Field(default=None, min_length=1, max_length=300)
    capacity: int | None = Field(default=None, strict=True, ge=0, le=2147483647)


class VenueResponse(Record):
    name: str
    city: str
    address: str
    capacity: int | None
