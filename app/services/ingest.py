"""Import orchestration: fetch -> enrich -> upsert -> benchmark -> score."""
import logging
from datetime import datetime
from typing import Optional

from sqlmodel import Session, select

from app.core.config import settings
from app.db.models import Property, Score
from app.services.deduplication import find_existing
from app.services.metro_distance import nearest_stations, walking_minutes
from app.services.walking_router import route_walking
from app.services.price_benchmark import benchmark_for, compute_benchmarks
from app.services import price_history as ph
from app.services.providers.base import DataProvider, NormalizedListing, SearchInput
from app.services.rental_estimator import estimate_rent, gross_yield_percent
from app.services.scoring import compute_score

logger = logging.getLogger("ingest")

_UPDATABLE_FIELDS = [
    "url", "title", "description", "price", "property_type", "typology", "area_m2",
    "rooms", "bathrooms", "floor", "has_elevator", "has_garage", "has_balcony",
    "has_terrace", "condition", "energy_certificate", "address_raw", "parish",
    "municipality", "district", "latitude", "longitude", "exact_location",
    "listing_agency", "images_count", "thumbnail_url", "image_urls",
]


def _apply_fields(prop: Property, item: NormalizedListing) -> None:
    for field in _UPDATABLE_FIELDS:
        value = getattr(item, field, None)
        if value is not None:
            setattr(prop, field, value)
    prop.updated_at = datetime.utcnow()


def enrich_geo(prop: Property) -> None:
    if prop.latitude is None or prop.longitude is None:
        prop.nearest_metro_station = None
        prop.distance_to_metro_m = None
        prop.walking_minutes_to_metro_estimate = None
        return

    origin = (prop.latitude, prop.longitude)
    candidates = nearest_stations(prop.latitude, prop.longitude, k=settings.routing_candidates)
    best = None  # (station, distance_m, minutes)
    if settings.routing_provider.lower() in ("ors", "google"):
        # Pick the candidate that is actually closest to WALK to, not just by air.
        for station, _air in candidates:
            route = route_walking(origin, (station.latitude, station.longitude))
            if route and (best is None or route[1] < best[2]):
                best = (station, route[0], route[1])
    if best is None:  # routing disabled, or every call failed -> straight line
        station, air = candidates[0]
        best = (station, air, walking_minutes(air, settings.walking_speed_m_per_min))

    station, dist_m, minutes = best
    prop.nearest_metro_station = station.name
    prop.distance_to_metro_m = round(dist_m, 1) if dist_m is not None else None
    prop.walking_minutes_to_metro_estimate = minutes


def enrich_financials(prop: Property) -> None:
    if prop.price and prop.area_m2 and prop.area_m2 > 0:
        prop.price_per_m2 = round(prop.price / prop.area_m2, 2)
    else:
        prop.price_per_m2 = None
    low, mid, high, _zone = estimate_rent(prop.typology, prop.municipality, prop.parish)
    prop.rental_estimate_low = low
    prop.rental_estimate_mid = mid
    prop.rental_estimate_high = high
    prop.gross_yield_percent = gross_yield_percent(mid, prop.price, prop.typology)


def upsert_listing(session: Session, item: NormalizedListing) -> tuple[Property, bool, bool]:
    """Returns (property, is_new, price_dropped_this_run)."""
    now = datetime.utcnow()
    existing = find_existing(session, item.source, item.external_id)

    if existing:
        prop = existing
        old_price = prop.price
        _apply_fields(prop, item)
        prop.last_seen_at = now
        prop.is_active = True
        prop.delisted_at = None  # reappeared -> back on the market
        if prop.first_seen_at:
            prop.days_on_market = (now - prop.first_seen_at).days
        enrich_geo(prop)
        enrich_financials(prop)

        new_price = prop.price
        price_dropped = bool(new_price and old_price and new_price < old_price)
        if new_price and old_price and new_price != old_price:
            amount, percent = ph.compute_drop(old_price, new_price)
            prop.previous_price = old_price
            prop.price_drop_amount = amount
            prop.price_drop_percent = percent
            session.add(prop)
            session.flush()
            ph.add_history(session, prop.id, new_price, now)
        else:
            session.add(prop)
        return prop, False, price_dropped

    # New listing
    prop = Property(source=item.source, external_id=str(item.external_id))
    _apply_fields(prop, item)
    prop.first_seen_at = now
    prop.last_seen_at = now
    prop.is_active = True
    prop.days_on_market = 0

    # Provider may supply a previous price -> show a drop already on first import.
    if item.previous_price and prop.price and item.previous_price > prop.price:
        amount, percent = ph.compute_drop(item.previous_price, prop.price)
        prop.previous_price = item.previous_price
        prop.price_drop_amount = amount
        prop.price_drop_percent = percent

    enrich_geo(prop)
    enrich_financials(prop)
    session.add(prop)
    session.flush()

    if item.previous_price and prop.price and item.previous_price != prop.price:
        ph.add_history(session, prop.id, item.previous_price, now)
    if prop.price:
        ph.add_history(session, prop.id, prop.price, now)
    return prop, True, False


def deactivate_unseen(
    session: Session,
    source: str,
    seen_external_ids: set[str],
    municipality: Optional[str] = None,
) -> int:
    """Mark active listings of `source` that were NOT in the latest run inactive.

    Only call this for a scope that was FULLY fetched (not cap-truncated), or it
    will falsely "delist" live listings beyond the cap. `municipality` restricts
    the sweep to one area.
    """
    stmt = select(Property).where(
        Property.source == source, Property.is_active == True  # noqa: E712
    )
    if municipality is not None:
        stmt = stmt.where(Property.municipality == municipality)
    rows = session.exec(stmt).all()
    now = datetime.utcnow()
    count = 0
    for prop in rows:
        if prop.external_id not in seen_external_ids:
            prop.is_active = False
            prop.delisted_at = now  # left the market at its last asking price
            if prop.first_seen_at and prop.last_seen_at:
                prop.days_on_market = max(0, (prop.last_seen_at - prop.first_seen_at).days)
            prop.updated_at = now
            session.add(prop)
            count += 1
    session.commit()
    return count


def _maybe_send_alerts(session: Session, created_ids: list[int], dropped_ids: list[int]) -> int:
    if not settings.alerts_enabled:
        return 0
    try:
        from app.services.alerts import send_run_alerts  # lazy import

        return send_run_alerts(session, created_ids, dropped_ids)
    except Exception:
        logger.exception("alert dispatch failed")
        return 0


def recalculate_scores(session: Session) -> int:
    benchmarks = compute_benchmarks(session)
    props = session.exec(select(Property).where(Property.is_active == True)).all()  # noqa: E712
    count = 0
    for prop in props:
        median = benchmark_for(benchmarks, prop)
        result = compute_score(prop, median)
        score = session.get(Score, prop.id)
        if not score:
            score = Score(property_id=prop.id)
        score.total_score = result.total_score
        score.price_score = result.price_score
        score.metro_score = result.metro_score
        score.liquidity_score = result.liquidity_score
        score.rental_yield_score = result.rental_yield_score
        score.condition_score = result.condition_score
        score.discount_score = result.discount_score
        score.risk_score = result.risk_score
        score.explanation_json = result.explanation
        score.calculated_at = datetime.utcnow()
        session.add(score)
        count += 1
    session.commit()
    return count


def run_areas_refresh(
    session: Session,
    provider: DataProvider,
    areas: list[tuple[str, str]],
    max_items: Optional[int] = None,
    deactivate_missing: bool = True,
) -> dict:
    """Full multi-area refresh: scrape each (municipality, url) area, upserting
    with the area as a municipality hint, then deactivate everything not seen in
    ANY area (single sweep) and rescore once.
    """
    created = updated = fetched = 0
    created_ids: list[int] = []
    dropped_ids: list[int] = []
    area_seen: dict[str, set[str]] = {}
    area_capped: dict[str, bool] = {}
    for municipality, url in areas:
        search = SearchInput(urls=[url], max_items=max_items, municipality_hint=municipality)
        try:
            listings = provider.fetch(search)
        except Exception:
            logger.exception("area fetch failed", extra={"extra_fields": {"area": municipality}})
            area_capped[municipality] = True  # treat failure as incomplete -> no delisting
            continue
        # If the area hit the cap it's only partially covered -> never delist it.
        area_capped[municipality] = area_capped.get(municipality, False) or getattr(
            provider, "last_capped", False
        )
        seen = area_seen.setdefault(municipality, set())
        fetched += len(listings)
        for item in listings:
            try:
                prop, is_new, dropped = upsert_listing(session, item)
                seen.add(str(item.external_id))
                created += 1 if is_new else 0
                updated += 0 if is_new else 1
                if is_new:
                    created_ids.append(prop.id)
                if dropped:
                    dropped_ids.append(prop.id)
            except Exception:
                logger.exception(
                    "failed to upsert listing",
                    extra={"extra_fields": {"external_id": getattr(item, "external_id", None)}},
                )
        session.commit()
        logger.info(
            "area imported",
            extra={"extra_fields": {"area": municipality, "fetched": len(listings),
                                    "capped": area_capped[municipality]}},
        )

    deactivated = 0
    if deactivate_missing:
        for municipality, ids in area_seen.items():
            if area_capped.get(municipality):
                logger.warning(
                    "area cap-truncated — skipping delisting (raise max_items)",
                    extra={"extra_fields": {"area": municipality}},
                )
                continue
            deactivated += deactivate_unseen(session, provider.name, ids, municipality=municipality)
    scored = recalculate_scores(session)
    alerted = _maybe_send_alerts(session, created_ids, dropped_ids)
    stats = {
        "provider": provider.name,
        "areas": len(areas),
        "fetched": fetched,
        "created": created,
        "updated": updated,
        "deactivated": deactivated,
        "scored": scored,
        "alerted": alerted,
    }
    logger.info("areas refresh complete", extra={"extra_fields": stats})
    return stats


def run_import(
    session: Session,
    provider: DataProvider,
    search: Optional[SearchInput] = None,
    deactivate_missing: bool = False,
) -> dict:
    listings = provider.fetch(search)
    created = updated = 0
    seen: set[str] = set()
    created_ids: list[int] = []
    dropped_ids: list[int] = []
    for item in listings:
        try:
            prop, is_new, dropped = upsert_listing(session, item)
            seen.add(str(item.external_id))
            created += 1 if is_new else 0
            updated += 0 if is_new else 1
            if is_new:
                created_ids.append(prop.id)
            if dropped:
                dropped_ids.append(prop.id)
        except Exception:
            logger.exception(
                "failed to upsert listing",
                extra={"extra_fields": {"external_id": getattr(item, "external_id", None)}},
            )
    session.commit()

    deactivated = 0
    # Only sweep when asked AND the run actually returned data (avoid wiping
    # everything on an empty/failed fetch).
    if deactivate_missing and listings:
        deactivated = deactivate_unseen(session, provider.name, seen)

    scored = recalculate_scores(session)
    alerted = _maybe_send_alerts(session, created_ids, dropped_ids)
    stats = {
        "provider": provider.name,
        "fetched": len(listings),
        "created": created,
        "updated": updated,
        "deactivated": deactivated,
        "scored": scored,
        "alerted": alerted,
    }
    logger.info("import complete", extra={"extra_fields": stats})
    return stats
