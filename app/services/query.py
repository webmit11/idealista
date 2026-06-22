"""Shared property querying (filters + sorting) and serialization.

Used by the JSON API, the HTML dashboard, and exports so all three stay in sync.
"""
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import asc, desc, func, not_, or_
from sqlmodel import Session, select

from app.core.config import settings
from app.db.models import Property, Score
from app.services.bad_neighborhoods import get_text_phrases, get_zone_keywords

# Sort key -> ORDER BY expression. Each user-facing column exposes asc + desc.
SORT_COLUMNS = {
    "score_desc": desc(func.coalesce(Score.total_score, 0)),
    "score_asc": asc(func.coalesce(Score.total_score, 0)),
    "price_asc": asc(Property.price),
    "price_desc": desc(Property.price),
    "ppm2_asc": asc(Property.price_per_m2),
    "ppm2_desc": desc(Property.price_per_m2),
    "area_asc": asc(Property.area_m2),
    "area_desc": desc(Property.area_m2),
    "yield_desc": desc(func.coalesce(Property.gross_yield_percent, 0)),
    "yield_asc": asc(func.coalesce(Property.gross_yield_percent, 0)),
    "distance_asc": asc(Property.distance_to_metro_m),
    "distance_desc": desc(Property.distance_to_metro_m),
    "drop_desc": desc(func.coalesce(Property.price_drop_percent, 0)),
    "drop_asc": asc(func.coalesce(Property.price_drop_percent, 0)),
    "newest": desc(Property.first_seen_at),
    "oldest": asc(Property.first_seen_at),
    "delisted_desc": desc(func.coalesce(Property.delisted_at, Property.last_seen_at)),
    "watch_desc": desc(func.coalesce(Property.watch_updated_at, Property.updated_at)),
}
SORT_COLUMNS["biggest_drop"] = SORT_COLUMNS["drop_desc"]  # backward-compat alias
VALID_SORTS = set(SORT_COLUMNS)


def _apply_sort(stmt, sort: str):
    expr = SORT_COLUMNS.get(sort, SORT_COLUMNS["score_desc"])
    return stmt.order_by(expr, Property.id)  # Property.id = stable tiebreaker


def _apply_filters(
    stmt,
    *,
    min_score: Optional[float] = None,
    max_price: Optional[float] = None,
    typology: Optional[str] = None,
    municipality: Optional[str] = None,
    max_distance_to_metro: Optional[float] = None,
    min_gross_yield: Optional[float] = None,
    only_price_drops: bool = False,
    only_new: bool = False,
    has_garage: Optional[bool] = None,
    has_elevator: Optional[bool] = None,
    exclude_ground_floor: bool = False,
    exclude_no_coordinates: bool = False,
    exclude_bad_neighborhoods: bool = False,
    only_exact_location: bool = False,
    only_delisted: bool = False,
    new_within_days: Optional[int] = None,
    watched_only: bool = False,
    watch_status: Optional[str] = None,
    active_only: bool = True,
):
    if only_delisted:
        stmt = stmt.where(Property.is_active == False)  # noqa: E712
    elif active_only:
        stmt = stmt.where(Property.is_active == True)  # noqa: E712
    if max_price is not None:
        stmt = stmt.where(Property.price <= max_price)
    if typology:
        stmt = stmt.where(Property.typology == typology.upper())
    if municipality:
        stmt = stmt.where(Property.municipality.ilike(f"%{municipality}%"))
    if max_distance_to_metro is not None:
        stmt = stmt.where(Property.distance_to_metro_m <= max_distance_to_metro)
    if min_gross_yield is not None:
        stmt = stmt.where(Property.gross_yield_percent >= min_gross_yield)
    if only_price_drops:
        stmt = stmt.where(
            Property.price_drop_percent != None,  # noqa: E711
            Property.price_drop_percent > 0,
        )
    if only_new:
        cutoff = datetime.utcnow() - timedelta(days=settings.new_listing_days)
        stmt = stmt.where(Property.first_seen_at >= cutoff)
    if new_within_days is not None:
        stmt = stmt.where(
            Property.first_seen_at >= datetime.utcnow() - timedelta(days=new_within_days)
        )
    if watched_only:
        stmt = stmt.where(Property.watch_status != None)  # noqa: E711
    if watch_status:
        stmt = stmt.where(Property.watch_status == watch_status)
    if has_garage is not None:
        stmt = stmt.where(Property.has_garage == has_garage)
    if has_elevator is not None:
        stmt = stmt.where(Property.has_elevator == has_elevator)
    if exclude_ground_floor:
        stmt = stmt.where((Property.floor == None) | (Property.floor > 0))  # noqa: E711
    if exclude_no_coordinates:
        stmt = stmt.where(
            Property.latitude != None, Property.longitude != None  # noqa: E711
        )
    if min_score is not None:
        stmt = stmt.where(Score.total_score >= min_score)
    if only_exact_location:
        stmt = stmt.where(Property.exact_location == True)  # noqa: E712
    if exclude_bad_neighborhoods:
        conds = []
        for kw in get_zone_keywords():  # bairro names: zona + parish only
            pat = f"%{kw}%"
            conds.append(func.coalesce(Property.district, "").ilike(pat))
            conds.append(func.coalesce(Property.parish, "").ilike(pat))
        for phrase in get_text_phrases():  # explicit mentions: listing text
            pat = f"%{phrase}%"
            conds.append(func.coalesce(Property.description, "").ilike(pat))
            conds.append(func.coalesce(Property.title, "").ilike(pat))
        if conds:
            stmt = stmt.where(not_(or_(*conds)))
    return stmt


def query_properties(
    session: Session,
    *,
    sort: str = "score_desc",
    limit: int = 50,
    offset: int = 0,
    **filters,
) -> list[tuple[Property, Optional[Score]]]:
    stmt = select(Property, Score).join(
        Score, Score.property_id == Property.id, isouter=True
    )
    stmt = _apply_filters(stmt, **filters)
    stmt = _apply_sort(stmt, sort if sort in VALID_SORTS else "score_desc")
    stmt = stmt.offset(offset).limit(limit)
    return list(session.exec(stmt).all())


def count_properties(session: Session, **filters) -> int:
    stmt = select(func.count()).select_from(Property).join(
        Score, Score.property_id == Property.id, isouter=True
    )
    stmt = _apply_filters(stmt, **filters)
    res = session.exec(stmt).one()
    try:
        return int(res)
    except (TypeError, ValueError):
        return int(res[0])


def _breakdown(score: Score) -> dict:
    return {
        "total": score.total_score,
        "price": score.price_score,
        "metro": score.metro_score,
        "liquidity": score.liquidity_score,
        "rental_yield": score.rental_yield_score,
        "condition": score.condition_score,
        "discount": score.discount_score,
        "risk_penalty": score.risk_score,
    }


def serialize(prop: Property, score: Optional[Score]) -> dict:
    return {
        "id": prop.id,
        "external_id": prop.external_id,
        "source": prop.source,
        "url": prop.url,
        "title": prop.title,
        "price": prop.price,
        "previous_price": prop.previous_price,
        "price_drop_amount": prop.price_drop_amount,
        "price_drop_percent": prop.price_drop_percent,
        "property_type": prop.property_type,
        "typology": prop.typology,
        "area_m2": prop.area_m2,
        "price_per_m2": prop.price_per_m2,
        "rooms": prop.rooms,
        "bathrooms": prop.bathrooms,
        "floor": prop.floor,
        "has_elevator": prop.has_elevator,
        "has_garage": prop.has_garage,
        "has_balcony": prop.has_balcony,
        "has_terrace": prop.has_terrace,
        "condition": prop.condition,
        "energy_certificate": prop.energy_certificate,
        "address_raw": prop.address_raw,
        "parish": prop.parish,
        "municipality": prop.municipality,
        "district": prop.district,
        "latitude": prop.latitude,
        "longitude": prop.longitude,
        "exact_location": prop.exact_location,
        "nearest_metro_station": prop.nearest_metro_station,
        "distance_to_metro_m": prop.distance_to_metro_m,
        "walking_minutes_to_metro_estimate": prop.walking_minutes_to_metro_estimate,
        "rental_estimate_low": prop.rental_estimate_low,
        "rental_estimate_mid": prop.rental_estimate_mid,
        "rental_estimate_high": prop.rental_estimate_high,
        "gross_yield_percent": prop.gross_yield_percent,
        "listing_agency": prop.listing_agency,
        "images_count": prop.images_count,
        "thumbnail_url": prop.thumbnail_url,
        "image_urls": prop.image_urls,
        "first_seen_at": prop.first_seen_at,
        "last_seen_at": prop.last_seen_at,
        "is_active": prop.is_active,
        "is_new": bool(
            prop.first_seen_at
            and prop.first_seen_at >= datetime.utcnow() - timedelta(days=settings.new_listing_days)
        ),
        "delisted_at": prop.delisted_at,
        "days_on_market": prop.days_on_market,
        "watch_status": prop.watch_status,
        "watch_note": prop.watch_note,
        "total_score": score.total_score if score else None,
        "risk_flags": (score.explanation_json or {}).get("risk_flags") if score else None,
        "bonus_flags": (score.explanation_json or {}).get("bonus_flags") if score else None,
        "score_breakdown": _breakdown(score) if score else None,
    }
