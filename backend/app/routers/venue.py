from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query
from sqlalchemy.orm import Session

from app.core.database import get_session
from app.core.security import require_manager
from app.models.entities import Account
from app.schemas.catalog import Archive, Page
from app.schemas.venue import VenueCreate, VenueResponse, VenueUpdate
from app.services.venue import VenueService

router = APIRouter(prefix="/venue", tags=["venue"])
DB = Annotated[Session, Depends(get_session)]
Manager = Annotated[Account, Depends(require_manager)]
ID = Annotated[int, Path(ge=-9223372036854775808, le=9223372036854775807)]


@router.get("", response_model=Page[VenueResponse])
def list_records(
    session: DB,
    manager: Manager,
    q: Annotated[str | None, Query(min_length=1, max_length=300)] = None,
    archived: bool = False,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0, le=9223372036854775807)] = 0,
):
    return VenueService(session).list(q=q, archived=archived, limit=limit, offset=offset)


@router.get("/{identity}", response_model=VenueResponse)
def get_record(identity: ID, session: DB, manager: Manager):
    return VenueService(session).get(identity)


@router.post("", response_model=VenueResponse, status_code=201)
def create_record(payload: VenueCreate, session: DB, manager: Manager):
    return VenueService(session).create(payload, manager.id)


@router.patch("/{identity}", response_model=VenueResponse)
def update_record(identity: ID, payload: VenueUpdate, session: DB, manager: Manager):
    return VenueService(session).update(identity, payload, manager.id)


@router.post("/{identity}/archive", response_model=VenueResponse)
def archive_record(identity: ID, payload: Archive, session: DB, manager: Manager):
    return VenueService(session).update(identity, payload, manager.id, archive=True)
