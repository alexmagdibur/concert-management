from typing import ClassVar, Literal

from pydantic import Field

from app.schemas.catalog import Input, Patch, Record


class FinanceCategoryCreate(Input):
    code: str = Field(min_length=1, max_length=40)
    name: str = Field(min_length=1, max_length=100)
    normal_direction: Literal["IN", "OUT"]


class FinanceCategoryUpdate(Patch):
    nullable_fields: ClassVar[frozenset[str]] = frozenset([])
    code: str | None = Field(default=None, min_length=1, max_length=40)
    name: str | None = Field(default=None, min_length=1, max_length=100)
    normal_direction: Literal["IN", "OUT"] | None = None


class FinanceCategoryResponse(Record):
    code: str
    name: str
    normal_direction: Literal["IN", "OUT"]
