import pytest

from app.services.scoring import (
    compute_score,
    condition_score,
    detect_risk_flags,
    discount_score,
    elevator_garage_score,
    liquidity_score,
    price_score,
)


@pytest.mark.parametrize(
    "ppm2,expected",
    [
        (1500, 100.0),  # ratio 0.75
        (1600, 100.0),  # ratio 0.80
        (1800, 85.0),   # ratio 0.90
        (1900, 65.0),   # ratio 0.95
        (2000, 65.0),   # ratio 1.00
        (2100, 45.0),   # ratio 1.05
        (2300, 25.0),   # ratio 1.15
        (2500, 10.0),   # ratio 1.25
    ],
)
def test_price_score_thresholds(ppm2, expected):
    assert price_score(ppm2, 2000) == expected


def test_price_score_no_benchmark():
    assert price_score(2000, None) == 50.0
    assert price_score(None, 2000) == 50.0


@pytest.mark.parametrize(
    "typ,expected",
    [("T2", 100.0), ("T1", 85.0), ("T3", 80.0), ("T0", 55.0), ("T4", 50.0), (None, 50.0)],
)
def test_liquidity_score(typ, expected):
    assert liquidity_score(typ) == expected


@pytest.mark.parametrize(
    "elev,gar,expected",
    [(True, True, 100.0), (True, False, 75.0), (False, True, 65.0), (False, False, 35.0), (None, None, 35.0)],
)
def test_elevator_garage_score(elev, gar, expected):
    assert elevator_garage_score(elev, gar) == expected


def test_condition_score():
    assert condition_score("new") == 100.0
    assert condition_score("to_renovate") == 35.0
    assert condition_score(None) == 50.0


@pytest.mark.parametrize(
    "drop,expected",
    [(12, 100.0), (8, 85.0), (6, 70.0), (4, 55.0), (1, 35.0), (0, 20.0), (None, 20.0)],
)
def test_discount_score(drop, expected):
    assert discount_score(drop) == expected


def test_risk_flags_missing_coordinates_and_area(make_prop):
    prop = make_prop(latitude=None, longitude=None, area_m2=None, condition="good")
    penalty, flags = detect_risk_flags(prop)
    assert "missing_coordinates" in flags
    assert "missing_area" in flags
    assert penalty == 10  # 5 + 5


def test_risk_flags_ground_floor_and_high_floor_no_elevator(make_prop):
    ground = make_prop(floor=0, latitude=1, longitude=1, area_m2=70, condition="good")
    _, flags = detect_risk_flags(ground)
    assert "ground_floor" in flags

    high = make_prop(floor=4, has_elevator=False, latitude=1, longitude=1, area_m2=70, condition="good")
    _, flags = detect_risk_flags(high)
    assert "no_elevator_high_floor" in flags


def test_risk_flag_basement_negative_floor(make_prop):
    p = make_prop(floor=-1, latitude=1, longitude=1, area_m2=59, condition="good")
    penalty, flags = detect_risk_flags(p)
    assert "basement" in flags
    assert "ground_floor" not in flags  # basement takes precedence
    assert penalty >= 6


def test_risk_flag_basement_from_keyword(make_prop):
    p = make_prop(floor=None, description="Apartamento T1 em cave", latitude=1, longitude=1,
                  area_m2=50, condition="good")
    _, flags = detect_risk_flags(p)
    assert "basement" in flags


def test_risk_flag_bad_neighborhood_from_district(make_prop):
    p = make_prop(district="Pasteleira", latitude=1, longitude=1, area_m2=60, condition="good")
    penalty, flags = detect_risk_flags(p)
    assert "bad_neighborhood" in flags
    assert penalty >= 10


def test_risk_flag_bad_neighborhood_from_description(make_prop):
    p = make_prop(description="Apartamento em bairro social", latitude=1, longitude=1,
                  area_m2=60, condition="good")
    _, flags = detect_risk_flags(p)
    assert "bad_neighborhood" in flags


def test_risk_flags_legal_keyword(make_prop):
    prop = make_prop(
        description="Apartamento arrendado com inquilino",
        latitude=1, longitude=1, area_m2=70, condition="good",
    )
    penalty, flags = detect_risk_flags(prop)
    assert "legal_or_occupancy_risk" in flags
    assert penalty >= 8


def test_risk_penalty_capped_at_20(make_prop):
    prop = make_prop(
        latitude=None, longitude=None, area_m2=None, floor=0, has_elevator=False,
        description="para remodelar, arrendado, ocupado, sem licença",
        price_per_m2=100,
    )
    penalty, _ = detect_risk_flags(prop, median_ppm2=2000)
    assert penalty == 20


def _perfect_prop(make_prop):
    return make_prop(
        price_per_m2=1400,           # ratio 0.7 vs median 2000 -> price 100
        distance_to_metro_m=300,     # metro 100
        typology="T2",               # liquidity 100
        gross_yield_percent=8.0,     # rental_yield 100
        condition="new",             # condition 100
        has_elevator=True, has_garage=True,  # elevator_garage 100
        price_drop_percent=12,       # discount 100
        latitude=41.15, longitude=-8.61, area_m2=85, floor=1,
        energy_certificate="A",
    )


def test_metro_score_discounted_for_approx_location(make_prop):
    base = dict(distance_to_metro_m=300, typology="T2", latitude=1, longitude=1,
                area_m2=80, floor=2, condition="good", energy_certificate="B")
    exact = compute_score(make_prop(exact_location=True, **base), median_ppm2=2000)
    approx = compute_score(make_prop(exact_location=False, **base), median_ppm2=2000)
    assert exact.metro_score == 100.0
    assert approx.metro_score == 70.0  # 100 * 0.7
    # metro weight is 20% -> total differs by (100-70)*0.20 = 6 points
    assert round(exact.total_score - approx.total_score, 2) == 6.0
    assert approx.explanation["metro_reduced_for_approx_location"] is True


def test_south_facing_bonus(make_prop):
    base = dict(distance_to_metro_m=300, typology="T2", latitude=1, longitude=1,
                area_m2=80, floor=2, condition="good", energy_certificate="B",
                exact_location=True)
    plain = compute_score(make_prop(**base), median_ppm2=2000)
    south = compute_score(
        make_prop(description="Living room and kitchen face south, great light", **base),
        median_ppm2=2000,
    )
    assert south.explanation["bonus_flags"] == ["south_facing"]
    assert south.explanation["bonus_points"] == 4.0
    assert round(south.total_score - plain.total_score, 2) == 4.0


def test_compute_score_perfect(make_prop):
    result = compute_score(_perfect_prop(make_prop), median_ppm2=2000)
    # Positive weights sum to 97; no penalty.
    assert result.total_score == 97.0
    assert result.risk_score == 0
    assert result.price_score == 100.0
    assert result.metro_score == 100.0
    # elevator/garage contributes via explanation, not a stored column
    assert result.explanation["component_scores"]["elevator_garage"] == 100.0


def test_compute_score_with_risk_penalty(make_prop):
    prop = _perfect_prop(make_prop)
    prop.description = "Imóvel arrendado com inquilino"  # legal risk -> -8
    result = compute_score(prop, median_ppm2=2000)
    assert result.risk_score == 8
    assert result.total_score == 89.0  # 97 - 8


def test_compute_score_clamped_and_bounded(make_prop):
    bad = make_prop(
        price_per_m2=3000, distance_to_metro_m=2000, typology="T4",
        gross_yield_percent=1.0, condition="to_renovate",
        has_elevator=False, has_garage=False, price_drop_percent=0,
        latitude=None, longitude=None, area_m2=None, floor=5,
        description="para remodelar ocupado",
    )
    result = compute_score(bad, median_ppm2=2000)
    assert 0.0 <= result.total_score <= 100.0
