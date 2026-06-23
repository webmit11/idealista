"""Investment scoring: combine component scores into a single 0-100 score.

The positive component weights sum to 97 (by design, per the brief), leaving a
small headroom; risk flags then subtract up to 20 penalty points. The final
total is clamped to [0, 100].
"""
from dataclasses import dataclass, field
from typing import Optional

from app.core.config import settings
from app.services.bad_neighborhoods import get_text_phrases, get_zone_keywords
from app.services.metro_distance import metro_score
from app.services.rental_estimator import rental_yield_score

WEIGHTS = {
    "price": 25,
    "metro": 20,
    "liquidity": 15,
    "rental_yield": 15,
    "condition": 10,
    "elevator_garage": 7,
    "discount": 5,
}

CONDITION_SCORES = {
    "new": 100.0,
    "renovated": 90.0,
    "good": 70.0,
    "to_renovate": 35.0,
    "unknown": 50.0,
}

LEGAL_RISK_KEYWORDS = [
    "ocupado",
    "usufruto",
    "arrendado",
    "rendimento vitalício",
    "rendimento vitalicio",
    "ilegal",
    "sem licença",
    "sem licenca",
    "não disponível para visitas",
    "nao disponivel para visitas",
    "penhora",
]
RENOVATION_KEYWORDS = [
    "para remodelar",
    "para recuperar",
    "para restaurar",
    "necessita de obras",
    "a recuperar",
]
GROUND_FLOOR_KEYWORDS = [
    "rés-do-chão",
    "res-do-chao",
    "rés do chão",
    "res do chao",
    "r/c",
]
BASEMENT_KEYWORDS = [
    "cave",
    "subsolo",
    "sub-solo",
    "meia cave",
    "meia-cave",
]

SOUTH_FACING_KEYWORDS = [
    # English (the actor often returns translated descriptions)
    "face south", "faces south", "facing south", "south-facing", "south facing",
    "southern exposure", "south exposure", "oriented to the south", "south orientation",
    # Portuguese
    "orientação sul", "orientação a sul", "orientado a sul", "exposição sul",
    "exposição a sul", "exposição solar a sul", "voltado a sul", "virado a sul",
    "frente sul", "face sul",
]

RISK_PENALTIES = {
    "missing_coordinates": 5,
    "missing_area": 5,
    "basement": 6,
    "ground_floor": 3,
    "no_elevator_high_floor": 4,
    "suspicious_low_price": 6,
    "legal_or_occupancy_risk": 8,
    "needs_renovation": 3,
    "insufficient_condition_data": 2,
    "bad_neighborhood": 10,
}
RISK_CAP = 20


# --------------------------------------------------------------------------- #
# Component scores
# --------------------------------------------------------------------------- #
def price_score(price_per_m2: Optional[float], median_ppm2: Optional[float]) -> float:
    """Score how cheap the listing is vs the local median price per m²."""
    if not price_per_m2 or not median_ppm2:
        return 50.0  # neutral when no benchmark / no area
    ratio = price_per_m2 / median_ppm2
    if ratio <= 0.80:
        return 100.0
    if ratio <= 0.90:
        return 85.0
    if ratio <= 1.00:
        return 65.0
    if ratio <= 1.10:
        return 45.0
    if ratio <= 1.20:
        return 25.0
    return 10.0


def liquidity_score(typology: Optional[str]) -> float:
    t = (typology or "").upper()
    return {"T1": 85.0, "T2": 100.0, "T3": 80.0, "T0": 55.0}.get(t, 50.0)


def elevator_garage_score(has_elevator: Optional[bool], has_garage: Optional[bool]) -> float:
    e, g = bool(has_elevator), bool(has_garage)
    if e and g:
        return 100.0
    if e:
        return 75.0
    if g:
        return 65.0
    return 35.0


def condition_score(condition: Optional[str]) -> float:
    return CONDITION_SCORES.get((condition or "unknown").lower(), 50.0)


def discount_score(price_drop_percent: Optional[float]) -> float:
    d = price_drop_percent or 0
    if d >= 10:
        return 100.0
    if d >= 7:
        return 85.0
    if d >= 5:
        return 70.0
    if d >= 3:
        return 55.0
    if d > 0:
        return 35.0
    return 20.0  # baseline negotiation potential


def _text_blob(prop) -> str:
    parts = [getattr(prop, "title", None), getattr(prop, "description", None), getattr(prop, "address_raw", None)]
    return " ".join(p for p in parts if p).lower()


def detect_risk_flags(prop, median_ppm2: Optional[float] = None) -> tuple[float, list[str]]:
    """Return (penalty_points, flags). Penalty capped at RISK_CAP.

    NOTE: 'very high condominium fee' and 'old building (build year)' from the
    brief are not implemented because those inputs are not part of the MVP data
    model. See README limitations.
    """
    flags: list[str] = []
    text = _text_blob(prop)

    if getattr(prop, "latitude", None) is None or getattr(prop, "longitude", None) is None:
        flags.append("missing_coordinates")
    area = getattr(prop, "area_m2", None)
    if not area or area <= 0:
        flags.append("missing_area")

    floor = getattr(prop, "floor", None)
    is_basement = (floor is not None and floor < 0) or any(k in text for k in BASEMENT_KEYWORDS)
    is_ground = (floor == 0) or any(k in text for k in GROUND_FLOOR_KEYWORDS)
    if is_basement:
        flags.append("basement")
    elif is_ground:
        flags.append("ground_floor")
    if not getattr(prop, "has_elevator", None) and floor is not None and floor >= 3:
        flags.append("no_elevator_high_floor")

    ppm2 = getattr(prop, "price_per_m2", None)
    if median_ppm2 and ppm2 and ppm2 < 0.4 * median_ppm2:
        flags.append("suspicious_low_price")

    if any(k in text for k in LEGAL_RISK_KEYWORDS):
        flags.append("legal_or_occupancy_risk")
    if any(k in text for k in RENOVATION_KEYWORDS):
        flags.append("needs_renovation")

    condition = getattr(prop, "condition", None)
    energy = getattr(prop, "energy_certificate", None)
    if condition in (None, "unknown") and energy in (None, "", "unknown"):
        flags.append("insufficient_condition_data")

    # Bad / social-housing neighbourhood. Bairro names are matched only against
    # the zona + parish (avoids street-name false positives); explicit
    # social-housing phrases are matched against the listing text.
    zone_text = " ".join(
        filter(None, [
            (getattr(prop, "parish", None) or "").lower(),
            (getattr(prop, "district", None) or "").lower(),
        ])
    )
    if any(k in zone_text for k in get_zone_keywords()) or any(
        p in text for p in get_text_phrases()
    ):
        flags.append("bad_neighborhood")

    flags = list(dict.fromkeys(flags))  # de-dupe, preserve order
    penalty = min(RISK_CAP, sum(RISK_PENALTIES.get(f, 0) for f in flags))
    return float(penalty), flags


def detect_bonuses(prop) -> tuple[float, list[str]]:
    """Positive adjustments (e.g. south-facing windows). Returns (points, flags)."""
    flags: list[str] = []
    text = _text_blob(prop)
    if any(k in text for k in SOUTH_FACING_KEYWORDS):
        flags.append("south_facing")
    points = settings.south_facing_bonus if "south_facing" in flags else 0.0
    return float(points), flags


@dataclass
class ScoreResult:
    total_score: float
    price_score: float
    metro_score: float
    liquidity_score: float
    rental_yield_score: float
    condition_score: float
    discount_score: float
    risk_score: float  # penalty (0-20)
    risk_flags: list[str] = field(default_factory=list)
    explanation: dict = field(default_factory=dict)


def compute_score(prop, median_ppm2: Optional[float] = None) -> ScoreResult:
    """Compute the full weighted score for a property-like object.

    `prop` only needs the relevant attributes (price_per_m2, distance_to_metro_m,
    typology, gross_yield_percent, condition, has_elevator, has_garage,
    price_drop_percent, latitude/longitude, area_m2, floor, text fields).
    """
    # Approximate location (hidden exact address) -> the metro distance is less
    # reliable, so discount the metro component.
    metro_raw = metro_score(getattr(prop, "distance_to_metro_m", None))
    approx_location = getattr(prop, "exact_location", None) is False
    if approx_location:
        metro_raw = round(metro_raw * settings.approx_location_metro_factor, 2)

    comp = {
        "price": price_score(getattr(prop, "price_per_m2", None), median_ppm2),
        "metro": metro_raw,
        "liquidity": liquidity_score(getattr(prop, "typology", None)),
        "rental_yield": rental_yield_score(getattr(prop, "gross_yield_percent", None)),
        "condition": condition_score(getattr(prop, "condition", None)),
        "elevator_garage": elevator_garage_score(
            getattr(prop, "has_elevator", None), getattr(prop, "has_garage", None)
        ),
        "discount": discount_score(getattr(prop, "price_drop_percent", None)),
    }
    penalty, flags = detect_risk_flags(prop, median_ppm2)
    bonus, bonus_flags = detect_bonuses(prop)

    positive = sum(WEIGHTS[k] * comp[k] / 100 for k in WEIGHTS)
    # Expert photo adjustment (-10..+10): the vision model nudges the score by what
    # it sees in the listing photos (condition, renovation, red flags). 0 if absent.
    expert_delta = max(-10, min(10, int(getattr(prop, "expert_delta", None) or 0)))
    total = max(0.0, min(100.0, positive - penalty + bonus + expert_delta))
    contributions = {k: round(WEIGHTS[k] * comp[k] / 100, 2) for k in WEIGHTS}

    explanation = {
        "expert_photo_delta": expert_delta,
        "weights": WEIGHTS,
        "component_scores": {k: round(v, 2) for k, v in comp.items()},
        "weighted_contributions": contributions,
        "positive_subtotal": round(positive, 2),
        "risk_penalty": penalty,
        "risk_flags": flags,
        "bonus_points": bonus,
        "bonus_flags": bonus_flags,
        "median_price_per_m2_benchmark": median_ppm2,
        "price_per_m2": getattr(prop, "price_per_m2", None),
        "gross_yield_percent": getattr(prop, "gross_yield_percent", None),
        "rental_estimate": {
            "low": getattr(prop, "rental_estimate_low", None),
            "mid": getattr(prop, "rental_estimate_mid", None),
            "high": getattr(prop, "rental_estimate_high", None),
        },
        "distance_to_metro_m": getattr(prop, "distance_to_metro_m", None),
        "nearest_metro_station": getattr(prop, "nearest_metro_station", None),
        "metro_reduced_for_approx_location": approx_location,
    }

    return ScoreResult(
        total_score=round(total, 2),
        price_score=round(comp["price"], 2),
        metro_score=round(comp["metro"], 2),
        liquidity_score=round(comp["liquidity"], 2),
        rental_yield_score=round(comp["rental_yield"], 2),
        condition_score=round(comp["condition"], 2),
        discount_score=round(comp["discount"], 2),
        risk_score=penalty,
        risk_flags=flags,
        explanation=explanation,
    )
