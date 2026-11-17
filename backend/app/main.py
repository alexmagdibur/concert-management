from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.core.config import get_settings
from app.routers import concert, counterparty, finance_category, venue
from app.routers.health import router as health_router
from app.services.catalog import CatalogError
from app.services.concert import ConcertError

app = FastAPI(title=get_settings().app_name)
app.include_router(health_router)
for catalog_router in (venue.router, counterparty.router, finance_category.router, concert.router):
    app.include_router(catalog_router)


@app.exception_handler(ConcertError)
@app.exception_handler(CatalogError)
async def domain_error_handler(request: Request, exc: CatalogError | ConcertError):
    return JSONResponse(status_code=exc.status, content={"detail": exc.detail})
