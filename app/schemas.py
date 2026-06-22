"""Pydantic request/response models for the API."""
from typing import Optional

from pydantic import BaseModel


class SearchProfileCreate(BaseModel):
    name: str
    municipalities: list[str] = []
    metro_stations: list[str] = []
    min_price: Optional[float] = None
    max_price: Optional[float] = None
    typologies: list[str] = []
    min_area_m2: Optional[float] = None
    max_distance_to_metro_m: Optional[float] = None
    require_elevator: bool = False
    require_garage: bool = False


class ImportMockRequest(BaseModel):
    path: Optional[str] = None


class ImportApifyRequest(BaseModel):
    urls: list[str] = []
    max_items: Optional[int] = None
    deactivate_missing: bool = False
