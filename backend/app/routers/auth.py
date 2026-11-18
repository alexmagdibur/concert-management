from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.database import get_session
from app.core.security import COOKIE_NAME, Identity, require_identity
from app.schemas.access import Credentials, SessionResponse
from app.services.auth import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])
DB = Annotated[Session, Depends(get_session)]
Current = Annotated[Identity, Depends(require_identity)]
Config = Annotated[Settings, Depends(get_settings)]


@router.post("/login", response_model=SessionResponse)
def login(data: Credentials, request: Request, response: Response, session: DB, settings: Config):
    # A browser must preflight a cross-origin request with this custom header.
    if (
        request.headers.get("X-Requested-With") != "ConcertCRM"
        or request.headers.get("Sec-Fetch-Site") == "cross-site"
        or request.headers.get("Content-Type", "").partition(";")[0].strip().lower()
        != "application/json"
    ):
        raise HTTPException(403, "Invalid login request")
    result, cookie = AuthService(session).login(data, settings, request.cookies.get(COOKIE_NAME))
    response.set_cookie(
        COOKIE_NAME,
        cookie,
        max_age=settings.session_ttl_seconds,
        secure=settings.session_cookie_secure,
        httponly=True,
        samesite=settings.session_cookie_samesite,
    )
    response.headers["Cache-Control"] = "no-store"
    return result


@router.get("/me", response_model=SessionResponse)
def me(identity: Current, response: Response):
    response.headers["Cache-Control"] = "no-store"
    return AuthService.describe(identity)


@router.post("/logout", status_code=204)
def logout(identity: Current, session: DB, settings: Config):
    AuthService(session).logout(identity)
    response = Response(status_code=204, headers={"Cache-Control": "no-store"})
    response.delete_cookie(
        COOKIE_NAME,
        secure=settings.session_cookie_secure,
        httponly=True,
        samesite=settings.session_cookie_samesite,
    )
    return response
