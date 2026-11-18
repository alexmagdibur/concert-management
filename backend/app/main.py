from fastapi import FastAPI, Request
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.core.config import get_settings
from app.routers import (
    audit,
    auth,
    concert,
    contract,
    counterparty,
    engagement,
    finance,
    finance_category,
    report,
    users,
    venue,
)
from app.routers.health import router as health_router
from app.services.catalog import CatalogError
from app.services.concert import ConcertError
from app.services.contract import ContractError
from app.services.engagement import EngagementError
from app.services.finance import FinanceError

app = FastAPI(title=get_settings().app_name)
app.include_router(health_router)
for catalog_router in (
    venue.router,
    counterparty.router,
    finance_category.router,
    concert.router,
    contract.router,
    engagement.router,
    finance.router,
    report.router,
    auth.router,
    users.router,
    audit.router,
):
    app.include_router(catalog_router)


@app.exception_handler(FinanceError)
@app.exception_handler(EngagementError)
@app.exception_handler(ContractError)
@app.exception_handler(ConcertError)
@app.exception_handler(CatalogError)
async def domain_error_handler(
    request: Request,
    exc: CatalogError | ConcertError | ContractError | EngagementError | FinanceError,
):
    return JSONResponse(status_code=exc.status, content={"detail": exc.detail})


@app.exception_handler(RequestValidationError)
async def safe_validation_error(request: Request, exc: RequestValidationError):
    if request.url.path.startswith(("/auth/", "/admin/accounts")):
        return JSONResponse(
            status_code=422,
            content={
                "detail": [
                    {key: error[key] for key in ("loc", "msg", "type")} for error in exc.errors()
                ]
            },
        )
    return await request_validation_exception_handler(request, exc)
