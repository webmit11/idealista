"""Optional real pedestrian routing to a metro station.

By default (no provider/key configured) `route_walking` returns None and callers
fall back to the straight-line estimate. Set settings.routing_provider to "ors"
(OpenRouteService) or "google" (Google Directions) plus the matching API key to
get real walking distance/time. Results are cached per coordinate pair so each
property costs at most one API call (and repeats for the same building are free).
"""
import logging
from typing import Optional, Tuple

import httpx

from app.core.config import settings

logger = logging.getLogger("walking_router")

_CACHE: dict = {}
_TIMEOUT = 8.0

Route = Tuple[float, float]  # (walking_distance_m, walking_minutes)


def route_walking(origin: Tuple[float, float], dest: Tuple[float, float]) -> Optional[Route]:
    """Return (walking_distance_m, walking_minutes), or None if unavailable."""
    provider = (settings.routing_provider or "haversine").lower()
    if provider not in ("ors", "google"):
        return None
    cache_key = (
        provider,
        round(origin[0], 5), round(origin[1], 5),
        round(dest[0], 5), round(dest[1], 5),
    )
    if cache_key in _CACHE:
        return _CACHE[cache_key]
    try:
        result = _ors(origin, dest) if provider == "ors" else _google(origin, dest)
    except Exception as exc:  # network / parsing / quota — fall back to haversine
        logger.warning("walking route (%s) failed: %s", provider, exc)
        result = None
    _CACHE[cache_key] = result
    return result


def _ors(origin: Tuple[float, float], dest: Tuple[float, float]) -> Optional[Route]:
    if not settings.ors_api_key:
        return None
    with httpx.Client(timeout=_TIMEOUT) as client:
        resp = client.post(
            "https://api.openrouteservice.org/v2/directions/foot-walking",
            headers={"Authorization": settings.ors_api_key},
            json={"coordinates": [[origin[1], origin[0]], [dest[1], dest[0]]]},
        )
    resp.raise_for_status()
    summary = resp.json()["routes"][0]["summary"]
    return float(summary["distance"]), round(float(summary["duration"]) / 60.0, 1)


def _google(origin: Tuple[float, float], dest: Tuple[float, float]) -> Optional[Route]:
    if not settings.google_maps_api_key:
        return None
    with httpx.Client(timeout=_TIMEOUT) as client:
        resp = client.get(
            "https://maps.googleapis.com/maps/api/directions/json",
            params={
                "origin": f"{origin[0]},{origin[1]}",
                "destination": f"{dest[0]},{dest[1]}",
                "mode": "walking",
                "key": settings.google_maps_api_key,
            },
        )
    resp.raise_for_status()
    data = resp.json()
    if data.get("status") != "OK" or not data.get("routes"):
        return None
    leg = data["routes"][0]["legs"][0]
    return float(leg["distance"]["value"]), round(float(leg["duration"]["value"]) / 60.0, 1)
