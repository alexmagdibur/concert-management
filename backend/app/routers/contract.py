from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query
from sqlalchemy.orm import Session

from app.core.database import get_session
from app.core.security import require_manager
from app.models.entities import Account
from app.schemas.catalog import Page
from app.schemas.contract import (
    ContractActivate,
    ContractCreate,
    ContractFilter,
    ContractResponse,
    ContractUpdate,
)
from app.services.contract import ContractService

router = APIRouter(prefix="/contract", tags=["contract"])
DB = Annotated[Session, Depends(get_session)]
Manager = Annotated[Account, Depends(require_manager)]
ID = Annotated[int, Path(ge=-9223372036854775808, le=9223372036854775807)]


@router.get("", response_model=Page[ContractResponse])
def list_contracts(filters: Annotated[ContractFilter, Query()], session: DB, manager: Manager):
    return ContractService(session).list(filters)


@router.get("/{identity}", response_model=ContractResponse)
def get_contract(identity: ID, session: DB, manager: Manager):
    return ContractService(session).get(identity)


@router.post("", response_model=ContractResponse, status_code=201)
def create_contract(data: ContractCreate, session: DB, manager: Manager):
    return ContractService(session).create(data, manager.id)


@router.patch("/{identity}", response_model=ContractResponse)
def update_contract(identity: ID, data: ContractUpdate, session: DB, manager: Manager):
    return ContractService(session).update(identity, data, manager.id)


@router.post("/{identity}/activate", response_model=ContractResponse)
def activate_contract(identity: ID, data: ContractActivate, session: DB, manager: Manager):
    return ContractService(session).activate(identity, data, manager.id)
