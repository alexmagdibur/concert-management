from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    SecretStr,
    StringConstraints,
    field_validator,
)

from app.schemas.catalog import Input, Version
from app.schemas.concert import Identity

RoleCode = Literal["ADMIN", "MANAGER"]
LoginName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]
NewPassword = Annotated[SecretStr, Field(min_length=12, max_length=256)]


class Credentials(BaseModel):
    model_config = ConfigDict(extra="forbid")

    login: LoginName
    password: SecretStr = Field(min_length=1, max_length=256)


class SessionResponse(BaseModel):
    account_id: int
    login: str
    roles: list[RoleCode]
    csrf_token: str


class ProfileResponse(BaseModel):
    login: str
    full_name: str
    position: str
    roles: list[RoleCode]
    email: str | None
    phone: str | None


class PasswordChange(BaseModel):
    model_config = ConfigDict(extra="forbid")

    current_password: SecretStr = Field(min_length=1, max_length=256)
    new_password: NewPassword


class RoleSelection(BaseModel):
    roles: list[RoleCode] = Field(min_length=1, max_length=2)

    @field_validator("roles")
    @classmethod
    def unique_roles(cls, values: list[RoleCode]) -> list[RoleCode]:
        if len(set(values)) != len(values):
            raise ValueError("Roles must be unique")
        return values


class AccountCreate(Input, RoleSelection):
    full_name: str = Field(min_length=1, max_length=150)
    position: str = Field(min_length=1, max_length=80)
    phone: str | None = Field(default=None, min_length=1, max_length=32)
    email: EmailStr | None = Field(default=None, max_length=254)
    login: LoginName
    password: NewPassword


class AccountShow(BaseModel):
    id: int
    employee_id: int
    login: str
    active: bool
    full_name: str
    position: str
    phone: str | None
    email: str | None
    roles: list[RoleCode]
    version: int


class AccountBlock(Input):
    version: Version
    replacement_employee_id: Identity | None = None
    reason: str = Field(min_length=1)


class AccountRoles(AccountBlock, RoleSelection):
    pass
