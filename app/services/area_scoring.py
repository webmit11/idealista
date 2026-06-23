"""Area (freguesia) scoring — aggregate listing metrics per zone for a
"where to buy" ranking. Computed on demand from active listings; the zone score
is the median of our per-property investment scores, with supporting metrics and
strength tags (relative to the city medians)."""
from statistics import median
from typing import Optional

from sqlmodel import Session, select

from app.db.models import Property, Score

MIN_LISTINGS = 6  # zones with fewer active listings are too thin to rank


def _med(xs) -> Optional[float]:
    xs = [x for x in xs if x is not None]
    return median(xs) if xs else None


def compute_area_scores(session: Session) -> list:
    rows = session.exec(
        select(Property, Score)
        .join(Score, Score.property_id == Property.id, isouter=True)
        .where(Property.is_active == True)  # noqa: E712
    ).all()

    zones: dict = {}
    for p, s in rows:
        zone = (p.parish or p.municipality or "—").strip()
        muni = (p.municipality or "").strip()
        z = zones.setdefault((zone, muni), {
            "ppm2": [], "yield": [], "score": [], "metro": [], "dom": [], "drops": 0, "al": 0, "n": 0,
        })
        z["n"] += 1
        z["ppm2"].append(p.price_per_m2)
        z["yield"].append(p.gross_yield_percent)
        z["metro"].append(p.walking_minutes_to_metro_estimate)
        z["dom"].append(p.days_on_market)
        if s and s.total_score is not None:
            z["score"].append(s.total_score)
        if (p.price_drop_percent or 0) > 0:
            z["drops"] += 1
        if p.has_al_license:
            z["al"] += 1

    city_yield = _med([v for z in zones.values() for v in z["yield"]])
    city_ppm2 = _med([v for z in zones.values() for v in z["ppm2"]])
    city_metro = _med([v for z in zones.values() for v in z["metro"]])

    out = []
    for (zone, muni), z in zones.items():
        if z["n"] < MIN_LISTINGS:
            continue
        my, mp, mm = _med(z["yield"]), _med(z["ppm2"]), _med(z["metro"])
        md, ms = _med(z["dom"]), _med(z["score"])
        drop_share = round(z["drops"] / z["n"] * 100) if z["n"] else 0
        tags = []
        if my and city_yield and my >= city_yield * 1.1:
            tags.append("высокая доходность")
        if mm and city_metro and mm <= city_metro * 0.8:
            tags.append("ближе к метро")
        if mp and city_ppm2 and mp <= city_ppm2 * 0.9:
            tags.append("доступный вход")
        if z["al"] >= 3:
            tags.append("AL-спрос")
        if drop_share >= 15:
            tags.append("часто торгуются")
        out.append({
            "zone": zone,
            "municipality": muni,
            "count": z["n"],
            "score": round(ms) if ms is not None else None,
            "median_ppm2": round(mp) if mp else None,
            "median_yield": round(my, 1) if my else None,
            "median_metro_min": round(mm) if mm else None,
            "median_dom": round(md) if md is not None else None,
            "al_count": z["al"],
            "drop_share": drop_share,
            "tags": tags or ["сбалансированный"],
        })
    out.sort(key=lambda d: (d["score"] or 0, d["count"]), reverse=True)
    return out
