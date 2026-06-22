import httpx
import pytest

from app.core.config import settings
from app.db.models import Property
from app.services import walking_router
from app.services.ingest import enrich_geo


class _FakeResp:
    def __init__(self, data):
        self._data = data

    def raise_for_status(self):
        pass

    def json(self):
        return self._data


class _FakeClient:
    payload = None
    raise_exc = False

    def __init__(self, *a, **k):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def _respond(self):
        if _FakeClient.raise_exc:
            raise httpx.HTTPError("boom")
        return _FakeResp(_FakeClient.payload)

    def post(self, *a, **k):
        return self._respond()

    def get(self, *a, **k):
        return self._respond()


@pytest.fixture(autouse=True)
def _reset(monkeypatch):
    walking_router._CACHE.clear()
    _FakeClient.payload = None
    _FakeClient.raise_exc = False
    monkeypatch.setattr(walking_router.httpx, "Client", _FakeClient)
    yield
    walking_router._CACHE.clear()


def test_haversine_default_returns_none(monkeypatch):
    monkeypatch.setattr(settings, "routing_provider", "haversine")
    assert walking_router.route_walking((41.15, -8.61), (41.16, -8.62)) is None


def test_ors_parses_distance_and_minutes(monkeypatch):
    monkeypatch.setattr(settings, "routing_provider", "ors")
    monkeypatch.setattr(settings, "ors_api_key", "key")
    _FakeClient.payload = {"routes": [{"summary": {"distance": 2750.0, "duration": 2400.0}}]}
    assert walking_router.route_walking((41.19, -8.52), (41.18, -8.54)) == (2750.0, 40.0)


def test_google_parses_distance_and_minutes(monkeypatch):
    monkeypatch.setattr(settings, "routing_provider", "google")
    monkeypatch.setattr(settings, "google_maps_api_key", "key")
    _FakeClient.payload = {
        "status": "OK",
        "routes": [{"legs": [{"distance": {"value": 2750}, "duration": {"value": 2400}}]}],
    }
    assert walking_router.route_walking((41.19, -8.52), (41.18, -8.54)) == (2750.0, 40.0)


def test_missing_key_returns_none(monkeypatch):
    monkeypatch.setattr(settings, "routing_provider", "ors")
    monkeypatch.setattr(settings, "ors_api_key", None)
    assert walking_router.route_walking((41.19, -8.52), (41.18, -8.54)) is None


def test_network_error_returns_none(monkeypatch):
    monkeypatch.setattr(settings, "routing_provider", "google")
    monkeypatch.setattr(settings, "google_maps_api_key", "key")
    _FakeClient.raise_exc = True
    assert walking_router.route_walking((41.19, -8.52), (41.18, -8.54)) is None


def test_enrich_geo_picks_shorter_walk(monkeypatch):
    """The air-nearest station may be a longer walk; routing should pick the other."""
    from app.services.metro_stations import MetroStation

    monkeypatch.setattr(settings, "routing_provider", "ors")
    monkeypatch.setattr(settings, "ors_api_key", "key")
    monkeypatch.setattr(settings, "routing_candidates", 2)

    s_near = MetroStation("AirNear", 41.1900, -8.5200)  # closest by air, long walk
    s_far = MetroStation("AirFar", 41.1850, -8.5300)    # farther by air, short walk
    monkeypatch.setattr(
        "app.services.ingest.nearest_stations",
        lambda lat, lon, k=2, stations=None: [(s_near, 200.0), (s_far, 900.0)],
    )

    def fake_route(origin, dest):
        return (3000.0, 45.0) if dest == (41.1900, -8.5200) else (950.0, 12.0)

    monkeypatch.setattr("app.services.ingest.route_walking", fake_route)

    p = Property(source="x", external_id="1", latitude=41.19, longitude=-8.52)
    enrich_geo(p)
    assert p.nearest_metro_station == "AirFar"
    assert p.distance_to_metro_m == 950.0
    assert p.walking_minutes_to_metro_estimate == 12.0


def test_enrich_geo_falls_back_when_routing_unavailable(monkeypatch):
    """No provider -> straight-line nearest + estimated minutes."""
    monkeypatch.setattr(settings, "routing_provider", "haversine")
    p = Property(source="x", external_id="2", latitude=41.17127, longitude=-8.54275)  # at Fânzeres
    enrich_geo(p)
    assert p.nearest_metro_station == "Fânzeres"
    assert p.distance_to_metro_m < 50  # essentially on top of the station
