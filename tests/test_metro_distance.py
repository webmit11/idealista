import math

import pytest

from app.services.metro_distance import (
    haversine_m,
    metro_score,
    nearest_station,
    walking_minutes,
)
from app.services.metro_stations import MetroStation


def test_haversine_zero():
    assert haversine_m(41.15, -8.61, 41.15, -8.61) == pytest.approx(0.0, abs=1e-6)


def test_haversine_one_degree_latitude():
    # ~111.2 km per degree of latitude
    d = haversine_m(0.0, 0.0, 1.0, 0.0)
    assert d == pytest.approx(111_195, rel=0.01)


def test_nearest_station_picks_closest():
    stations = [
        MetroStation("Near", 41.1520, -8.6094),
        MetroStation("Far", 41.3000, -8.7000),
    ]
    station, dist = nearest_station(41.1519, -8.6093, stations)
    assert station.name == "Near"
    assert dist < 50  # within a few metres


def test_nearest_station_missing_coords():
    assert nearest_station(None, None) == (None, None)


def test_walking_minutes():
    assert walking_minutes(800, 80) == 10.0
    assert walking_minutes(0, 80) == 0.0
    assert walking_minutes(None) is None


@pytest.mark.parametrize(
    "distance,expected",
    [
        (0, 100.0),
        (500, 100.0),
        (501, 85.0),
        (800, 85.0),
        (900, 70.0),
        (1000, 70.0),
        (1100, 55.0),
        (1200, 55.0),
        (1300, 35.0),
        (1500, 35.0),
        (1600, 0.0),
        (None, 0.0),
    ],
)
def test_metro_score_thresholds(distance, expected):
    assert metro_score(distance) == expected
