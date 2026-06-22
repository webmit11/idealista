from app.services.explain import explain_score

_P = {
    "total_score": 78.0, "price_per_m2": 2700, "nearest_metro_station": "Ramalde",
    "distance_to_metro_m": 330, "typology": "T2", "gross_yield_percent": 6.3,
    "rental_estimate_mid": 1300, "condition": "good", "has_elevator": True,
    "has_garage": False, "price_drop_percent": None,
}
_E = {
    "component_scores": {"price": 85, "metro": 70, "liquidity": 100, "rental_yield": 85,
                         "condition": 70, "elevator_garage": 75, "discount": 20},
    "weights": {"price": 25, "metro": 20, "liquidity": 15, "rental_yield": 15,
                "condition": 10, "elevator_garage": 7, "discount": 5},
    "weighted_contributions": {"price": 21.25, "metro": 14.0, "liquidity": 15.0,
                               "rental_yield": 12.75, "condition": 7.0,
                               "elevator_garage": 5.25, "discount": 1.0},
    "positive_subtotal": 76.25, "risk_penalty": 0, "risk_flags": [],
    "bonus_points": 4, "bonus_flags": ["south_facing"],
    "median_price_per_m2_benchmark": 3000, "price_per_m2": 2700,
    "metro_reduced_for_approx_location": True,
}


def test_explain_score_structure_and_text():
    out = explain_score(_P, _E)
    assert len(out["components"]) == 7
    by_label = {c["label"]: c for c in out["components"]}
    price = by_label["Цена vs локальная медиана €/м²"]
    assert price["raw"] == 85 and "медиане" in price["detail"] and "10%" in price["detail"]
    metro = by_label["Близость к метро"]
    assert "Ramalde" in metro["detail"] and "0.7" in metro["detail"]
    assert out["bonuses"][0]["label"] == "Окна на юг"
    assert out["bonus_points"] == 4
    assert out["risk_penalty"] == 0


def test_explain_score_risk_labels_and_penalties():
    e = dict(_E, risk_flags=["basement", "bad_neighborhood"], risk_penalty=16)
    out = explain_score(_P, e)
    labels = {r["label"]: r["penalty"] for r in out["risks"]}
    assert labels["Подвал / цоколь"] == 6
    assert labels["Плохой / социальный район"] == 10


def test_explain_score_none():
    assert explain_score(_P, None) is None
