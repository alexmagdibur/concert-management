from app.repositories.finance_category import FinanceCategoryRepository
from app.schemas.finance_category import FinanceCategoryResponse
from app.services.catalog import CatalogService


class FinanceCategoryService(CatalogService):
    repository_class = FinanceCategoryRepository
    response_class = FinanceCategoryResponse
