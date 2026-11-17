from app.repositories.venue import VenueRepository
from app.schemas.venue import VenueResponse
from app.services.catalog import CatalogService


class VenueService(CatalogService):
    repository_class = VenueRepository
    response_class = VenueResponse
