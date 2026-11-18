from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Response
from sqlalchemy.orm import Session

from app.core.database import get_session
from app.core.security import require_manager
from app.models.entities import Account
from app.schemas.catalog import Page
from app.schemas.finance import (
    FinanceCreate,
    FinancePost,
    FinanceRegister,
    FinanceResponse,
    FinanceStatus,
    FinanceUpdate,
    FinanceVoid,
)
from app.services.finance import FinanceService

router = APIRouter(tags=["finance"])
DB = Annotated[Session, Depends(get_session)]
Manager = Annotated[Account, Depends(require_manager)]
ID = Annotated[int, Path(ge=-9223372036854775808, le=9223372036854775807)]


@router.get("/concert/{concert_id}/finance", response_model=Page[FinanceResponse])
def list_finance(
    concert_id: ID,
    session: DB,
    manager: Manager,
    status: FinanceStatus | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0, le=9223372036854775807)] = 0,
):
    return FinanceService(session).list_for_concert(
        concert_id, status=status, limit=limit, offset=offset
    )


@router.post(
    "/finance",
    response_model=FinanceResponse,
    status_code=201,
    responses={200: {"model": FinanceResponse}},
)
def register_finance(data: FinanceRegister, response: Response, session: DB, manager: Manager):
    entry, created = FinanceService(session).register(data, manager.id)
    if not created:
        response.status_code = 200
    return entry


@router.post("/finance/draft", response_model=FinanceResponse, status_code=201)
def draft_finance(data: FinanceCreate, session: DB, manager: Manager):
    return FinanceService(session).draft(data, manager.id)


@router.patch("/finance/{identity}", response_model=FinanceResponse)
def update_finance(identity: ID, data: FinanceUpdate, session: DB, manager: Manager):
    return FinanceService(session).update(identity, data, manager.id)


@router.post("/finance/{identity}/post", response_model=FinanceResponse)
def post_finance(identity: ID, data: FinancePost, session: DB, manager: Manager):
    return FinanceService(session).post(identity, data, manager.id)


@router.post("/finance/{identity}/void", response_model=FinanceResponse)
def void_finance(identity: ID, data: FinanceVoid, session: DB, manager: Manager):
    return FinanceService(session).void(identity, data, manager.id)
