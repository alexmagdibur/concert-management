from app.repositories.counterparty import CounterpartyRepository
from app.schemas.counterparty import CounterpartyResponse
from app.services.catalog import CatalogService


class CounterpartyService(CatalogService):
    repository_class = CounterpartyRepository
    response_class = CounterpartyResponse
