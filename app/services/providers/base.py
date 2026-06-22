"""DataProvider interface and the normalized listing schema.

All providers (mock, Apify, future official Idealista API / CASAFARI) must map
their source-specific payloads into `NormalizedListing` so the rest of the
pipeline stays source-agnostic.
"""
from abc import ABC, abstractmethod
from typing import Optional

from pydantic import BaseModel


class NormalizedListing(BaseModel):
    external_id: str
    source: str
    url: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = None
    price: Optional[float] = None
    previous_price: Optional[float] = None
    property_type: Optional[str] = None
    typology: Optional[str] = None  # T0/T1/T2/T3/T4...
    area_m2: Optional[float] = None
    rooms: Optional[int] = None
    bathrooms: Optional[int] = None
    floor: Optional[int] = None
    has_elevator: Optional[bool] = None
    has_garage: Optional[bool] = None
    has_balcony: Optional[bool] = None
    has_terrace: Optional[bool] = None
    condition: Optional[str] = None
    energy_certificate: Optional[str] = None
    address_raw: Optional[str] = None
    parish: Optional[str] = None
    municipality: Optional[str] = None
    district: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    exact_location: Optional[bool] = None
    listing_agency: Optional[str] = None
    images_count: Optional[int] = None
    thumbnail_url: Optional[str] = None
    image_urls: Optional[list[str]] = None


class SearchInput(BaseModel):
    urls: list[str] = []
    max_items: Optional[int] = None
    # When set, every listing from this search is tagged with this municipality
    # (concelho) and the source's own locality becomes the parish. Used for
    # per-municipality scrapes where the area is known up front.
    municipality_hint: Optional[str] = None
    extra: dict = {}


class DataProvider(ABC):
    name: str = "base"

    @abstractmethod
    def fetch(self, search: Optional[SearchInput] = None) -> list[NormalizedListing]:
        """Fetch listings and return them as normalized records."""
        raise NotImplementedError
