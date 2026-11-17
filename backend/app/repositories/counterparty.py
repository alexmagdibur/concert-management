from app.models.entities import Counterparty
from app.repositories.catalog import CatalogRepository


class CounterpartyRepository(CatalogRepository):
    model = Counterparty
    search_fields = ("name", "kind", "phone", "email", "details")
    identity_fields = ("name", "kind")
    lock_key = 810002
