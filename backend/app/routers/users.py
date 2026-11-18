from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query
from sqlalchemy.orm import Session

from app.core.database import get_session
from app.core.security import require_admin
from app.models.entities import Account
from app.schemas.access import AccountBlock, AccountCreate, AccountRoles, AccountShow
from app.schemas.catalog import Page
from app.services.users import UserService

router = APIRouter(prefix="/admin/accounts", tags=["accounts"])
DB = Annotated[Session, Depends(get_session)]
Admin = Annotated[Account, Depends(require_admin)]
ID = Annotated[int, Path(ge=-(2**63), lt=2**63)]


@router.get("", response_model=Page[AccountShow])
def list_accounts(
    session: DB,
    admin: Admin,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0, lt=2**63)] = 0,
):
    return UserService(session).list(limit, offset)


@router.post("", response_model=AccountShow, status_code=201)
def create_account(data: AccountCreate, session: DB, admin: Admin):
    return UserService(session).create(data, admin.id)


@router.post("/{identity}/block", response_model=AccountShow)
def block_account(identity: ID, data: AccountBlock, session: DB, admin: Admin):
    return UserService(session).block(identity, data, admin.id)


@router.put("/{identity}/roles", response_model=AccountShow)
def set_roles(identity: ID, data: AccountRoles, session: DB, admin: Admin):
    return UserService(session).set_roles(identity, data, admin.id)
