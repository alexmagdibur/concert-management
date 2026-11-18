from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query
from sqlalchemy.orm import Session

from app.core.database import get_session
from app.core.security import require_manager
from app.models.entities import Account
from app.schemas.catalog import Page
from app.schemas.engagement import (
    EngagementAgree,
    EngagementCancel,
    EngagementCreate,
    EngagementResponse,
    EngagementTransition,
)
from app.services.engagement import EngagementService

router = APIRouter(tags=["engagement"])
DB = Annotated[Session, Depends(get_session)]
Manager = Annotated[Account, Depends(require_manager)]
ID = Annotated[int, Path(ge=-9223372036854775808, le=9223372036854775807)]


@router.get("/concert/{concert_id}/engagement", response_model=Page[EngagementResponse])
def list_engagements(
    concert_id: ID,
    session: DB,
    manager: Manager,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0, le=9223372036854775807)] = 0,
):
    return EngagementService(session).list_for_concert(concert_id, limit=limit, offset=offset)


@router.post("/engagement", response_model=EngagementResponse, status_code=201)
def create_engagement(data: EngagementCreate, session: DB, manager: Manager):
    return EngagementService(session).create(data, manager.id)


@router.post("/engagement/{identity}/agree", response_model=EngagementResponse)
def agree_engagement(identity: ID, data: EngagementAgree, session: DB, manager: Manager):
    return EngagementService(session).agree(identity, data, manager.id)


@router.post("/engagement/{identity}/complete", response_model=EngagementResponse)
def complete_engagement(identity: ID, data: EngagementTransition, session: DB, manager: Manager):
    return EngagementService(session).complete(identity, data, manager.id)


@router.post("/engagement/{identity}/cancel", response_model=EngagementResponse)
def cancel_engagement(identity: ID, data: EngagementCancel, session: DB, manager: Manager):
    return EngagementService(session).cancel(identity, data, manager.id)
