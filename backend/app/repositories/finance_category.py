from app.models.entities import FinanceCategory
from app.repositories.catalog import CatalogRepository


class FinanceCategoryRepository(CatalogRepository):
    model = FinanceCategory
    search_fields = ("code", "name")
    identity_fields = ("code",)
    lock_key = 810003
