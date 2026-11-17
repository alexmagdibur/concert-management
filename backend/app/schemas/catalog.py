from datetime import UTC, datetime
from typing import Annotated, ClassVar, TypeVar

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Version = Annotated[int, Field(strict=True, ge=1, le=9223372036854775807)]


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Patch(Input):
    version: Version
    nullable_fields: ClassVar[frozenset[str]] = frozenset()

    @model_validator(mode="after")
    def validate_patch(self):
        changed = self.model_fields_set - {"version"}
        if not changed:
            raise ValueError("Supply at least one field to update")
        for name in changed:
            if getattr(self, name) is None and name not in self.nullable_fields:
                raise ValueError(f"{name} cannot be null")
        return self


class Archive(Input):
    version: Version


class Record(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    archived: bool
    created_at: datetime
    updated_at: datetime
    version: int

    @field_validator("created_at", "updated_at")
    @classmethod
    def normalize_utc(cls, value: datetime) -> datetime:
        return value.astimezone(UTC)


T = TypeVar("T")


class Page[T](BaseModel):
    items: list[T]
    total: int
    limit: int
    offset: int
