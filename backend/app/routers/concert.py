from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query
from sqlalchemy.orm import Session

from app.core.database import get_session
from app.core.security import require_manager
from app.models.entities import Account
from app.schemas.catalog import Page
from app.schemas.concert import (
    ConcertCancel,
    ConcertCreate,
    ConcertFilter,
    ConcertResponse,
    ConcertTransition,
    ConcertUpdate,
)
from app.services.concert import ConcertService

router = APIRouter(prefix="/concert", tags=["concert"])
DB = Annotated[Session, Depends(get_session)]
Manager = Annotated[Account, Depends(require_manager)]
ID = Annotated[int, Path(ge=-9223372036854775808, le=9223372036854775807)]


@router.get("", response_model=Page[ConcertResponse])
def list_concerts(filters: Annotated[ConcertFilter, Query()], session: DB, manager: Manager):
    return ConcertService(session).list(filters)


@router.get("/{identity}", response_model=ConcertResponse)
def get_concert(identity: ID, session: DB, manager: Manager):
    return ConcertService(session).get(identity)


@router.post("", response_model=ConcertResponse, status_code=201)
def create_concert(payload: ConcertCreate, session: DB, manager: Manager):
    return ConcertService(session).create(payload, manager.id)


@router.patch("/{identity}", response_model=ConcertResponse)
def update_concert(identity: ID, payload: ConcertUpdate, session: DB, manager: Manager):
    return ConcertService(session).update(identity, payload, manager.id)


@router.post("/{identity}/confirm", response_model=ConcertResponse)
def confirm_concert(identity: ID, payload: ConcertTransition, session: DB, manager: Manager):
    return ConcertService(session).transition(identity, payload, manager.id, "CONFIRMED")


@router.post("/{identity}/complete", response_model=ConcertResponse)
def complete_concert(identity: ID, payload: ConcertTransition, session: DB, manager: Manager):
    return ConcertService(session).transition(identity, payload, manager.id, "COMPLETED")


@router.post("/{identity}/cancel", response_model=ConcertResponse)
def cancel_concert(identity: ID, payload: ConcertCancel, session: DB, manager: Manager):
    return ConcertService(session).transition(identity, payload, manager.id, "CANCELLED")
