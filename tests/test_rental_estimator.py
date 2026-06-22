import pytest

from app.services.rental_estimator import (
    estimate_rent,
    furnishing_cost,
    gross_yield_percent,
    purchase_costs,
    rental_yield_score,
    resolve_zone,
    total_acquisition_cost,
)


@pytest.mark.parametrize(
    "municipality,parish,zone",
    [
        ("Porto", "Bonfim", "porto"),
        ("Maia", None, "maia"),
        ("Matosinhos", "Senhora da Hora", "senhora_matosinhos"),
        ("Gondomar", "Rio Tinto", "riotinto_gondomar"),
        ("Vila do Conde", None, "viladoconde_povoa"),
        ("Espinho", None, "riotinto_gondomar"),  # unknown -> default
    ],
)
def test_resolve_zone(municipality, parish, zone):
    assert resolve_zone(municipality, parish) == zone


def test_estimate_rent_porto_t2():
    low, mid, high, zone = estimate_rent("T2", "Porto", "Bonfim")
    assert (low, high, zone) == (1100, 1400, "porto")
    assert mid == 1250


def test_estimate_rent_maia_t1():
    low, mid, high, zone = estimate_rent("T1", "Maia")
    assert (low, mid, high) == (750, 850, 950)


def test_estimate_rent_t3_derived_from_t2():
    low, mid, high, _ = estimate_rent("T3", "Porto")
    # T3 factor 1.25 applied to Porto T2 (1100, 1400)
    assert low == round(1100 * 1.25)
    assert high == round(1400 * 1.25)


def test_furnishing_cost():
    assert furnishing_cost("T1") == 6000
    assert furnishing_cost("T2") == 9000
    assert furnishing_cost("T3") == 12000
    assert furnishing_cost("T5") == 12000  # default


def test_purchase_costs():
    assert purchase_costs(200000) == 12000.0
    assert purchase_costs(None) == 0.0


def test_total_acquisition_cost():
    # 200000 + 6% + furnishing(T2=9000)
    assert total_acquisition_cost(200000, "T2") == 221000.0
    assert total_acquisition_cost(None, "T2") is None


def test_gross_yield_percent():
    y = gross_yield_percent(1250, 200000, "T2")
    # 1250*12 / 221000 * 100
    assert y == pytest.approx(6.79, abs=0.01)
    assert gross_yield_percent(None, 200000, "T2") is None
    assert gross_yield_percent(1250, None, "T2") is None


@pytest.mark.parametrize(
    "yld,expected",
    [
        (7.5, 100.0),
        (7.0, 100.0),
        (6.5, 85.0),
        (5.5, 70.0),
        (4.2, 50.0),
        (3.1, 30.0),
        (2.0, 10.0),
        (None, 0.0),
    ],
)
def test_rental_yield_score(yld, expected):
    assert rental_yield_score(yld) == expected
