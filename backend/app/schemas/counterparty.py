from typing import ClassVar

from pydantic import EmailStr, Field

from app.schemas.catalog import Input, Patch, Record


class CounterpartyCreate(Input):
    name: str = Field(min_length=1, max_length=200)
    kind: str = Field(min_length=1, max_length=20)
    phone: str | None = Field(default=None, min_length=1, max_length=32)
    email: EmailStr | None = Field(default=None, min_length=1, max_length=254)
    details: str | None = None


class CounterpartyUpdate(Patch):
    nullable_fields: ClassVar[frozenset[str]] = frozenset(["phone", "email", "details"])
    name: str | None = Field(default=None, min_length=1, max_length=200)
    kind: str | None = Field(default=None, min_length=1, max_length=20)
    phone: str | None = Field(default=None, min_length=1, max_length=32)
    email: EmailStr | None = Field(default=None, min_length=1, max_length=254)
    details: str | None = None


class CounterpartyResponse(Record):
    name: str
    kind: str
    phone: str | None
    email: EmailStr | None
    details: str | None
