from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query
from sqlalchemy.orm import Session

from app.core.database import get_session
from app.core.security import require_manager
from app.models.entities import Account
from app.schemas.catalog import Archive, Page
from app.schemas.counterparty import CounterpartyCreate, CounterpartyResponse, CounterpartyUpdate
from app.services.counterparty import CounterpartyService

router = APIRouter(prefix="/counterparty", tags=["counterparty"])
DB = Annotated[Session, Depends(get_session)]
Manager = Annotated[Account, Depends(require_manager)]
ID = Annotated[int, Path(ge=-9223372036854775808, le=9223372036854775807)]


@router.get("", response_model=Page[CounterpartyResponse])
def list_records(
    session: DB,
    manager: Manager,
    q: Annotated[str | None, Query(min_length=1, max_length=300)] = None,
    archived: bool = False,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0, le=9223372036854775807)] = 0,
):
    return CounterpartyService(session).list(q=q, archived=archived, limit=limit, offset=offset)


@router.get("/{identity}", response_model=CounterpartyResponse)
def get_record(identity: ID, session: DB, manager: Manager):
    return CounterpartyService(session).get(identity)


@router.post("", response_model=CounterpartyResponse, status_code=201)
def create_record(payload: CounterpartyCreate, session: DB, manager: Manager):
    return CounterpartyService(session).create(payload, manager.id)


@router.patch("/{identity}", response_model=CounterpartyResponse)
def update_record(identity: ID, payload: CounterpartyUpdate, session: DB, manager: Manager):
    return CounterpartyService(session).update(identity, payload, manager.id)


@router.post("/{identity}/archive", response_model=CounterpartyResponse)
def archive_record(identity: ID, payload: Archive, session: DB, manager: Manager):
    return CounterpartyService(session).update(identity, payload, manager.id, archive=True)
