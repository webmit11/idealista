"""Regression + mapping tests for the Apify Idealista provider."""
from app.services.providers.apify_idealista import ApifyIdealistaProvider
from app.services.providers.base import SearchInput

URL = "https://www.idealista.pt/comprar-casas/porto/com-preco-max_300000,t1,t2,t3/"


def _provider():
    return ApifyIdealistaProvider(token="x", actor_id="y")


def test_build_input_keeps_comma_url_intact_from_search():
    payload = _provider()._build_input(SearchInput(urls=[URL], max_items=200))
    assert payload["Property_urls"] == [{"url": URL}]  # not split on commas
    assert payload["desiredResults"] == 200


def test_build_input_env_url_with_commas(monkeypatch):
    # Regression: env URLs must NOT be split on commas (Idealista URLs have them).
    from app.core.config import settings

    monkeypatch.setattr(settings, "apify_search_urls", URL)
    payload = _provider()._build_input(None)
    assert len(payload["Property_urls"]) == 1
    assert payload["Property_urls"][0]["url"].endswith("t1,t2,t3/")


def test_build_input_enforces_min_desired_results():
    payload = _provider()._build_input(SearchInput(urls=["http://x"], max_items=3))
    assert payload["desiredResults"] == 10  # actor minimum


def test_normalize_maps_fields_and_geography():
    item = {
        "propertyCode": "123",
        "url": "https://www.idealista.pt/imovel/123/",
        "price": 250000,
        "size": 95,
        "rooms": 3,
        "bathrooms": 2,
        "floor": "1",
        "hasLift": True,
        "status": "good",
        "municipality": "Campanhã",   # freguesia for a Porto-city listing
        "province": "Porto",          # distrito
        "district": "Bonfim",
        "latitude": 41.15,
        "longitude": -8.58,
        "numPhotos": 22,
        "suggestedTexts": {"title": "T3 flat in Campanhã"},
        "contactInfo": {"commercialName": "Acme Imo"},
        "features": {"hasTerrace": True},
        "description": "Apartamento com lugar de garagem",
    }
    n = _provider()._normalize(item)
    assert n.external_id == "123"
    assert n.typology == "T3"
    assert n.municipality == "Porto"      # resolved concelho
    assert n.parish == "Campanhã"         # idealista municipality -> parish
    assert n.has_elevator is True
    assert n.has_garage is True           # inferred from description
    assert n.has_terrace is True
    assert n.condition == "good"
    assert n.listing_agency == "Acme Imo"
    assert n.title == "T3 flat in Campanhã"


def test_normalize_new_development_condition():
    n = _provider()._normalize({"propertyCode": "1", "newDevelopment": True, "rooms": 2})
    assert n.condition == "new"
    assert n.typology == "T2"


def test_normalize_with_municipality_hint():
    # Pedrouços is a Maia freguesia whose name lacks "maia"; the hint fixes it.
    item = {"propertyCode": "5", "rooms": 2, "municipality": "Pedrouços", "province": "Porto"}
    n = _provider()._normalize(item, municipality_hint="Maia")
    assert n.municipality == "Maia"
    assert n.parish == "Pedrouços"


def test_images_extraction():
    item = {
        "thumbnail": "https://img/thumb.jpg",
        "multimedia": {"images": [{"url": "https://img/1.jpg"}, {"url": "https://img/2.jpg"}, {"no": "x"}]},
    }
    thumb, urls = _provider()._images(item)
    assert thumb == "https://img/thumb.jpg"
    assert urls == ["https://img/1.jpg", "https://img/2.jpg"]


def test_images_thumbnail_falls_back_to_first_and_handles_empty():
    thumb, urls = _provider()._images({"multimedia": {"images": [{"url": "https://img/9.jpg"}]}})
    assert thumb == "https://img/9.jpg"
    assert _provider()._images({}) == (None, [])


def test_normalize_exact_location_from_show_address():
    p = _provider()
    assert p._normalize({"propertyCode": "1", "showAddress": False}).exact_location is False
    assert p._normalize({"propertyCode": "2", "showAddress": True}).exact_location is True
    assert p._normalize({"propertyCode": "3"}).exact_location is None


def test_is_house():
    p = _provider()
    assert p._is_house({"propertyType": "chalet"}) is True
    assert p._is_house({"propertyType": "countryHouse"}) is True
    assert p._is_house({"propertyType": "flat"}) is False
    assert p._is_house({"propertyType": "penthouse"}) is False
    assert p._is_house({"propertyType": "duplex"}) is False
    assert p._is_house({}) is False  # unknown type -> kept


def test_floor_codes():
    p = _provider()
    assert p._floor({"floor": "bj"}) == 0    # ground floor
    assert p._floor({"floor": "ss"}) == -1   # semi-basement
    assert p._floor({"floor": "en"}) == 0    # entressolo
    assert p._floor({"floor": "3"}) == 3
    assert p._floor({"floor": None}) is None


def test_is_new_development():
    p = _provider()
    assert p._is_new_development({"url": "https://www.idealista.pt/empreendimento/123/"}) is True
    assert p._is_new_development({"url": "https://www.idealista.pt/imovel/9/", "newDevelopment": True}) is True
    assert p._is_new_development({"url": "https://www.idealista.pt/imovel/9/"}) is False
