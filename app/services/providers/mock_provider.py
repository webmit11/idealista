"""Mock provider: reads listings from a local JSON file."""
import json
from pathlib import Path
from typing import Optional

from app.core.config import settings
from app.services.providers.base import DataProvider, NormalizedListing, SearchInput


class MockProvider(DataProvider):
    name = "mock"

    def __init__(self, path: Optional[str] = None):
        self.path = path or settings.mock_data_path

    def fetch(self, search: Optional[SearchInput] = None) -> list[NormalizedListing]:
        raw = json.loads(Path(self.path).read_text(encoding="utf-8"))
        listings: list[NormalizedListing] = []
        for item in raw:
            item.setdefault("source", "mock")
            listings.append(NormalizedListing(**item))
        return listings
