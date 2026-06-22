"""Metro proximity: haversine distance, nearest station, walking time, score.

This is an approximation: straight-line (haversine) distance, not real
pedestrian routing. The architecture allows swapping in Google Maps /
OpenRouteService later by replacing `nearest_station` / `walking_minutes`.
"""
import math
from typing import Optional

from app.services.metro_stations import METRO_STATIONS, MetroStation

EARTH_RADIUS_M = 6_371_000.0


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance between two WGS84 points, in metres."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(a))


def nearest_station(
    lat: Optional[float],
    lon: Optional[float],
    stations: Optional[list[MetroStation]] = None,
) -> tuple[Optional[MetroStation], Optional[float]]:
    """Return (station, distance_m) for the closest station, or (None, None)."""
    if lat is None or lon is None:
        return None, None
    stations = stations or METRO_STATIONS
    best: Optional[MetroStation] = None
    best_d: Optional[float] = None
    for s in stations:
        d = haversine_m(lat, lon, s.latitude, s.longitude)
        if best_d is None or d < best_d:
            best_d, best = d, s
    return best, best_d


def walking_minutes(distance_m: Optional[float], speed_m_per_min: float = 80.0) -> Optional[float]:
    """Estimated walking minutes. Default 80 m/min (~4.8 km/h)."""
    if distance_m is None:
        return None
    if speed_m_per_min <= 0:
        speed_m_per_min = 80.0
    return round(distance_m / speed_m_per_min, 1)


def metro_score(distance_m: Optional[float]) -> float:
    """0-100 proximity score from straight-line distance to nearest station."""
    if distance_m is None:
        return 0.0
    if distance_m <= 500:
        return 100.0
    if distance_m <= 800:
        return 85.0
    if distance_m <= 1000:
        return 70.0
    if distance_m <= 1200:
        return 55.0
    if distance_m <= 1500:
        return 35.0
    return 0.0
