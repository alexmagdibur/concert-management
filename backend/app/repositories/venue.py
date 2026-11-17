from app.models.entities import Venue
from app.repositories.catalog import CatalogRepository


class VenueRepository(CatalogRepository):
    model = Venue
    search_fields = ("name", "city", "address")
    identity_fields = ("name", "city", "address")
    lock_key = 810001
