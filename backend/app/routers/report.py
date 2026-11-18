from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query
from sqlalchemy.orm import Session

from app.core.database import get_session
from app.core.security import require_manager
from app.models.entities import Account
from app.schemas.report import (
    ConcertRanking,
    ConcertReport,
    DashboardQuery,
    DashboardSummary,
    ExpenseForecast,
    Period,
    ReportQuery,
)
from app.services.report import ReportService

router = APIRouter(tags=["reports"])
DB = Annotated[Session, Depends(get_session)]
Manager = Annotated[Account, Depends(require_manager)]
ID = Annotated[int, Path(ge=-9223372036854775808, le=9223372036854775807)]


@router.get("/dashboard", response_model=DashboardSummary)
def dashboard(query: Annotated[DashboardQuery, Query()], session: DB, manager: Manager):
    return ReportService(session).dashboard(query)


@router.get("/concert/{concert_id}/finance/report", response_model=ConcertReport)
def concert_report(
    concert_id: ID, query: Annotated[ReportQuery, Query()], session: DB, manager: Manager
):
    return ReportService(session).concert_report(concert_id, query)


@router.get("/analytics/ranking", response_model=ConcertRanking)
def ranking(query: Annotated[Period, Query()], session: DB, manager: Manager):
    return ReportService(session).ranking(query)


@router.get("/concert/{concert_id}/finance/forecast", response_model=ExpenseForecast)
def expense_forecast(
    concert_id: ID, query: Annotated[Period, Query()], session: DB, manager: Manager
):
    return ReportService(session).forecast(concert_id, query)
