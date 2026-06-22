"""Rule-based rental estimation and gross yield for the Porto / Grande Porto area.

All figures are rough MVP heuristics, not market guarantees. Base monthly rent
ranges for T1/T2 come from the project brief; T0/T3/T4+ are derived with simple
multipliers. Replace with real comparables / an ML model later.
"""
from typing import Optional

# Base monthly rent ranges (EUR) by zone for the reference typologies T1 & T2.
ZONE_RENT_TABLE: dict[str, dict[str, tuple[int, int]]] = {
    "porto": {"T1": (850, 1050), "T2": (1100, 1400)},
    "senhora_matosinhos": {"T1": (900, 1150), "T2": (1200, 1500)},
    "maia": {"T1": (750, 950), "T2": (950, 1250)},
    "riotinto_gondomar": {"T1": (750, 950), "T2": (900, 1200)},
    "viladoconde_povoa": {"T1": (700, 900), "T2": (850, 1100)},
    "gaia": {"T1": (800, 1000), "T2": (1000, 1300)},
}
DEFAULT_ZONE = "riotinto_gondomar"  # conservative fallback for unknown areas

# Multipliers to derive typologies missing from the base table.
T0_FACTOR = 0.80  # studio, relative to T1
T3_FACTOR = 1.25  # relative to T2
T4_FACTOR = 1.45  # relative to T2

FURNISHING_COST = {"T0": 6000, "T1": 6000, "T2": 9000, "T3": 12000}
DEFAULT_FURNISHING = 12000
PURCHASE_COST_RATE = 0.06  # rough acquisition costs (IMT/IS/notary/registration)


def resolve_zone(municipality: Optional[str], parish: Optional[str] = None) -> str:
    m = (municipality or "").strip().lower()
    p = (parish or "").strip().lower()
    text = f"{p} {m}"
    if "maia" in m:
        return "maia"
    if "gaia" in m or "vila nova de gaia" in text:
        return "gaia"
    if "matosinhos" in m or "senhora da hora" in text or "sra da hora" in text:
        return "senhora_matosinhos"
    if "gondomar" in m or "rio tinto" in text:
        return "riotinto_gondomar"
    if "vila do conde" in m or "póvoa" in m or "povoa" in m:
        return "viladoconde_povoa"
    if "porto" in m:
        return "porto"
    return DEFAULT_ZONE


def estimate_rent(
    typology: Optional[str],
    municipality: Optional[str],
    parish: Optional[str] = None,
) -> tuple[int, int, int, str]:
    """Return (low, mid, high, zone) monthly rent estimate in EUR."""
    zone = resolve_zone(municipality, parish)
    table = ZONE_RENT_TABLE[zone]
    t = (typology or "").upper()

    if t in table:
        low, high = table[t]
    elif t == "T0":
        low, high = table["T1"][0] * T0_FACTOR, table["T1"][1] * T0_FACTOR
    elif t == "T3":
        low, high = table["T2"][0] * T3_FACTOR, table["T2"][1] * T3_FACTOR
    elif t.startswith("T") and t[1:].isdigit() and int(t[1:]) >= 4:
        low, high = table["T2"][0] * T4_FACTOR, table["T2"][1] * T4_FACTOR
    else:
        # Unknown typology -> assume a T2-like profile.
        low, high = table["T2"]

    low, high = round(low), round(high)
    mid = round((low + high) / 2)
    return low, mid, high, zone


def furnishing_cost(typology: Optional[str]) -> int:
    return FURNISHING_COST.get((typology or "").upper(), DEFAULT_FURNISHING)


def purchase_costs(price: Optional[float], rate: float = PURCHASE_COST_RATE) -> float:
    if not price:
        return 0.0
    return round(price * rate, 2)


def total_acquisition_cost(
    price: Optional[float],
    typology: Optional[str],
    rate: float = PURCHASE_COST_RATE,
) -> Optional[float]:
    if not price:
        return None
    return round(price + purchase_costs(price, rate) + furnishing_cost(typology), 2)


def gross_yield_percent(
    rental_mid: Optional[float],
    price: Optional[float],
    typology: Optional[str],
    rate: float = PURCHASE_COST_RATE,
) -> Optional[float]:
    tac = total_acquisition_cost(price, typology, rate)
    if not tac or not rental_mid:
        return None
    return round(rental_mid * 12 / tac * 100, 2)


def rental_yield_score(yield_percent: Optional[float]) -> float:
    """Map gross yield % to a 0-100 score."""
    if yield_percent is None:
        return 0.0
    y = yield_percent
    if y >= 7:
        return 100.0
    if y >= 6:
        return 85.0
    if y >= 5:
        return 70.0
    if y >= 4:
        return 50.0
    if y >= 3:
        return 30.0
    return 10.0
