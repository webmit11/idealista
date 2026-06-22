"""Apify Idealista scraper provider.

Tailored to the Apify actor **dz_omar~idealista-scraper-api** (id oJTRDX4iyfR3erNnv),
which returns Idealista's raw API JSON. Input schema:
  - Property_urls (array of {"url": ...}, required) — search or property URLs
  - desiredResults (integer, min 10)            — max items per search URL

If you switch to a different actor, adjust `_build_input` (input keys) and
`_normalize` (output field names). The raw JSON response is stored under
settings.raw_data_dir for debugging.

Legal note: do not point this at Idealista in ways that violate their Terms of
Service. Prefer official APIs (Idealista API, CASAFARI) where possible.
"""
import json
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

import httpx

from app.core.config import settings
from app.services.providers.base import DataProvider, NormalizedListing, SearchInput

logger = logging.getLogger("apify")

# Map Idealista geography to a real Porto-area concelho (municipality).
# Idealista returns a freguesia in `municipality` for Porto-city listings, so we
# infer the concelho from the combined location text.
_CONCELHO_KEYWORDS = [
    ("maia", "Maia"),
    ("senhora da hora", "Matosinhos"),
    ("são mamede de infesta", "Matosinhos"),
    ("sao mamede", "Matosinhos"),
    ("leça", "Matosinhos"),
    ("leca", "Matosinhos"),
    ("custóias", "Matosinhos"),
    ("custoias", "Matosinhos"),
    ("perafita", "Matosinhos"),
    ("matosinhos", "Matosinhos"),
    ("rio tinto", "Gondomar"),
    ("fânzeres", "Gondomar"),
    ("fanzeres", "Gondomar"),
    ("baguim", "Gondomar"),
    ("valbom", "Gondomar"),
    ("jovim", "Gondomar"),
    ("gondomar", "Gondomar"),
    ("ermesinde", "Valongo"),
    ("alfena", "Valongo"),
    ("valongo", "Valongo"),
    ("vila nova de gaia", "Vila Nova de Gaia"),
    ("vila do conde", "Vila do Conde"),
    ("póvoa de varzim", "Póvoa de Varzim"),
    ("povoa de varzim", "Póvoa de Varzim"),
    ("póvoa", "Póvoa de Varzim"),
    ("espinho", "Espinho"),
]

_CONDITION_MAP = {"good": "good", "renew": "to_renovate", "newdevelopment": "new"}

# Apartment property types to keep; everything else (chalet/countryHouse/…) is a house.
_APARTMENT_TYPES = {"flat", "penthouse", "duplex", "studio"}

# Idealista encodes low floors as letter codes instead of numbers.
_FLOOR_CODES = {
    "bj": 0,    # baixo / rés-do-chão (ground floor)
    "rc": 0, "r/c": 0,
    "en": 0,    # entressolo (low mezzanine)
    "ss": -1,   # subsolo (semi-basement)
    "cv": -1,   # cave (basement)
    "sb": -1,
}


def _to_float(value) -> Optional[float]:
    try:
        if value is None or value == "":
            return None
        if isinstance(value, str):
            value = value.replace("€", "").replace(",", "").replace(" ", "")
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_int(value) -> Optional[int]:
    f = _to_float(value)
    return int(f) if f is not None else None


def _to_bool(value) -> Optional[bool]:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in {"true", "1", "yes", "sim", "y"}
    return None


class ApifyIdealistaProvider(DataProvider):
    name = "apify_idealista"
    BASE_URL = "https://api.apify.com/v2"

    def __init__(self, token: Optional[str] = None, actor_id: Optional[str] = None):
        self.token = token or settings.apify_token
        self.actor_id = actor_id or settings.apify_actor_id
        # Set after each fetch: did the result hit the requested cap (incomplete)?
        self.last_raw_count: Optional[int] = None
        self.last_capped: bool = False

    # ----------------------------------------------------------------- input
    def _build_input(self, search: Optional[SearchInput]) -> dict:
        # NOTE: split on whitespace, NOT commas — Idealista URLs contain commas
        # in their filter segment (e.g. .../com-preco-max_300000,t1,t2,t3/).
        urls = (
            search.urls
            if search and search.urls
            else settings.apify_search_urls.split()
        )
        max_items = search.max_items if search and search.max_items else settings.apify_max_items
        payload = {
            "Property_urls": [{"url": u} for u in urls],
            "desiredResults": max(10, int(max_items or 10)),  # actor minimum is 10
        }
        if search and search.extra:
            payload.update(search.extra)
        return payload

    # ----------------------------------------------------------------- fetch
    POLL_INTERVAL_S = 5
    _TERMINAL = {"SUCCEEDED", "FAILED", "ABORTED", "TIMED-OUT", "TIMING-OUT"}

    def fetch(self, search: Optional[SearchInput] = None) -> list[NormalizedListing]:
        if not self.token:
            raise RuntimeError("APIFY_TOKEN is not configured")
        payload = self._build_input(search)
        if not payload.get("Property_urls"):
            raise RuntimeError(
                "No Idealista search URLs configured (set APIFY_SEARCH_URLS or pass urls)"
            )

        items = self._run_and_collect(payload)
        if not isinstance(items, list):
            raise RuntimeError(f"Unexpected Apify response (expected a list): {str(items)[:200]}")

        # Did we hit the requested cap? If so the area is only partially covered
        # and we must NOT treat the unseen listings as delisted.
        desired = payload.get("desiredResults")
        self.last_raw_count = len(items)
        self.last_capped = bool(desired and len(items) >= desired)

        self._store_raw(items)

        hint = search.municipality_hint if search else None
        skipped_dev = skipped_house = 0
        normalized: list[NormalizedListing] = []
        for item in items:
            if not item:
                continue
            if settings.apify_exclude_new_developments and self._is_new_development(item):
                skipped_dev += 1
                continue
            if settings.apify_exclude_houses and self._is_house(item):
                skipped_house += 1
                continue
            try:
                normalized.append(self._normalize(item, municipality_hint=hint))
            except Exception:  # one bad record must not kill the whole run
                logger.warning("failed to normalize an apify item", exc_info=True)
        if skipped_dev or skipped_house:
            logger.info(
                "skipped non-apartment listings",
                extra={"extra_fields": {"new_developments": skipped_dev, "houses": skipped_house}},
            )
        return normalized

    @staticmethod
    def _is_new_development(item: dict) -> bool:
        """A new-development project (empreendimento), not a single resale unit."""
        if "/empreendimento/" in (item.get("url") or ""):
            return True
        return bool(item.get("newDevelopment"))

    @staticmethod
    def _is_house(item: dict) -> bool:
        """A house (chalet / countryHouse / moradia), not an apartment."""
        pt = (item.get("propertyType") or "").strip().lower()
        return bool(pt) and pt not in _APARTMENT_TYPES

    def _run_and_collect(self, payload: dict) -> list:
        """Start the actor run, poll until it finishes, then fetch dataset items.

        Avoids the 300s limit of the run-sync endpoint, so large scrapes and the
        daily scheduler work reliably.
        """
        params = {"token": self.token}
        logger.info(
            "starting apify run",
            extra={"extra_fields": {"actor": self.actor_id, "urls": len(payload["Property_urls"])}},
        )
        try:
            with httpx.Client(timeout=60) as client:
                r = client.post(
                    f"{self.BASE_URL}/acts/{self.actor_id}/runs", params=params, json=payload
                )
                r.raise_for_status()
                run = r.json()["data"]
                run_id, dataset_id, status = run["id"], run["defaultDatasetId"], run["status"]

                deadline = time.monotonic() + settings.apify_timeout_s
                while status not in self._TERMINAL:
                    if time.monotonic() > deadline:
                        raise RuntimeError(
                            f"Apify run {run_id} not finished within "
                            f"{settings.apify_timeout_s}s (status={status})"
                        )
                    time.sleep(self.POLL_INTERVAL_S)
                    s = client.get(f"{self.BASE_URL}/actor-runs/{run_id}", params=params)
                    s.raise_for_status()
                    status = s.json()["data"]["status"]

                logger.info(
                    "apify run finished",
                    extra={"extra_fields": {"run_id": run_id, "status": status}},
                )
                if status != "SUCCEEDED":
                    raise RuntimeError(f"Apify run {run_id} ended with status {status}")

                d = client.get(
                    f"{self.BASE_URL}/datasets/{dataset_id}/items",
                    params={**params, "clean": "true", "format": "json"},
                )
                d.raise_for_status()
                return d.json()
        except httpx.HTTPError as exc:
            logger.exception("apify request failed")
            raise RuntimeError(f"Apify request failed: {exc}") from exc

    def _store_raw(self, items: list) -> None:
        try:
            directory = Path(settings.raw_data_dir)
            directory.mkdir(parents=True, exist_ok=True)
            fp = directory / f"apify_{datetime.utcnow():%Y%m%d_%H%M%S}.json"
            fp.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
            logger.info(
                "stored raw apify response",
                extra={"extra_fields": {"file": str(fp), "items": len(items)}},
            )
        except Exception:
            logger.warning("could not store raw apify response", exc_info=True)

    # ------------------------------------------------------------ normalize
    @staticmethod
    def _first(item: dict, *keys):
        for k in keys:
            v = item.get(k)
            if v not in (None, ""):
                return v
        return None

    def _geo(self, item: dict) -> tuple[Optional[str], Optional[str], Optional[str]]:
        """Return (municipality/concelho, parish/freguesia, district)."""
        province = item.get("province")      # distrito, e.g. "Porto"
        muni = item.get("municipality")      # concelho OR freguesia (Porto city)
        district = item.get("district")      # zona / neighbourhood
        blob = " ".join(
            filter(None, [muni, district, item.get("address"), province])
        ).lower()
        concelho = None
        for kw, name in _CONCELHO_KEYWORDS:
            if kw in blob:
                concelho = name
                break
        if concelho is None:
            concelho = "Porto" if (province or "").strip().lower() == "porto" else (muni or province)
        return concelho, muni, district  # district = zona / bairro (e.g. Pasteleira)

    def _condition(self, item: dict) -> Optional[str]:
        if _to_bool(item.get("newDevelopment")) or _to_bool(item.get("newProperty")):
            return "new"
        status = (item.get("status") or "").strip().lower()
        return _CONDITION_MAP.get(status)

    def _energy(self, item: dict) -> Optional[str]:
        ec = item.get("energyCertification")
        if isinstance(ec, dict):
            cons = ec.get("energyConsumption")
            if isinstance(cons, dict):
                return cons.get("type")
        if isinstance(ec, str):
            return ec
        return None

    def _garage(self, item: dict) -> Optional[bool]:
        ps = item.get("parkingSpace")
        if isinstance(ps, dict):
            v = _to_bool(ps.get("hasParkingSpace"))
            if v is not None:
                return v
        blob = " ".join(
            [str(item.get("description") or ""), json.dumps(item.get("features") or {}, ensure_ascii=False)]
        ).lower()
        if any(k in blob for k in ("garagem", "garage", "lugar de garagem", "estacionamento", "parking")):
            return True
        return None

    def _floor(self, item: dict) -> Optional[int]:
        raw = self._first(item, "floor", "floorNumber")
        if raw is None:
            return None
        code = str(raw).strip().lower()
        if code in _FLOOR_CODES:
            return _FLOOR_CODES[code]
        return _to_int(raw)

    def _images(self, item: dict, limit: int = 12) -> tuple[Optional[str], list[str]]:
        """Return (thumbnail_url, [image_urls]). Idealista image URLs are signed
        and expire eventually; a fresh import refreshes them."""
        mm = item.get("multimedia") or {}
        images = mm.get("images") if isinstance(mm, dict) else None
        urls: list[str] = []
        if isinstance(images, list):
            urls = [im.get("url") for im in images if isinstance(im, dict) and im.get("url")][:limit]
        thumb = item.get("thumbnail") or (urls[0] if urls else None)
        return thumb, urls

    def _price(self, item: dict) -> Optional[float]:
        p = _to_float(item.get("price"))
        if p is not None:
            return p
        info = item.get("priceInfo") or {}
        if isinstance(info, dict):
            price = info.get("price") or {}
            if isinstance(price, dict):
                return _to_float(price.get("amount"))
        return None

    def _normalize(self, item: dict, municipality_hint: Optional[str] = None) -> NormalizedListing:
        rooms = _to_int(self._first(item, "rooms"))
        typology = f"T{rooms}" if rooms is not None else None
        if municipality_hint:
            # Known area: trust the hint as the concelho, keep the freguesia as
            # parish and Idealista's zona/bairro as district (e.g. Pasteleira).
            municipality = municipality_hint
            parish = item.get("municipality")
            district = item.get("district")
        else:
            municipality, parish, district = self._geo(item)

        suggested = item.get("suggestedTexts") or {}
        title = suggested.get("title") if isinstance(suggested, dict) else None
        title = title or self._first(item, "address")

        contact = item.get("contactInfo") or {}
        agency = contact.get("commercialName") if isinstance(contact, dict) else None

        features = item.get("features") or {}
        has_terrace = features.get("hasTerrace") if isinstance(features, dict) else None
        has_balcony = features.get("hasBalcony") if isinstance(features, dict) else None

        thumbnail_url, image_urls = self._images(item)

        return NormalizedListing(
            external_id=str(self._first(item, "propertyCode", "externalReference", "url")),
            source=self.name,
            url=self._first(item, "url"),
            title=title,
            description=self._first(item, "description"),
            price=self._price(item),
            property_type=self._first(item, "propertyType"),
            typology=typology,
            area_m2=_to_float(self._first(item, "size")),
            rooms=rooms,
            bathrooms=_to_int(self._first(item, "bathrooms")),
            floor=self._floor(item),
            has_elevator=_to_bool(self._first(item, "hasLift")),
            has_garage=self._garage(item),
            has_balcony=_to_bool(has_balcony),
            has_terrace=_to_bool(has_terrace),
            condition=self._condition(item),
            energy_certificate=self._energy(item),
            address_raw=self._first(item, "address"),
            parish=parish,
            municipality=municipality,
            district=district,
            latitude=_to_float(self._first(item, "latitude")),
            longitude=_to_float(self._first(item, "longitude")),
            exact_location=_to_bool(item.get("showAddress")),
            listing_agency=agency,
            images_count=_to_int(self._first(item, "numPhotos")),
            thumbnail_url=thumbnail_url,
            image_urls=image_urls,
        )
