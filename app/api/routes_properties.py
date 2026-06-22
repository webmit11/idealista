"""Property listing endpoints."""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, select

from app.db.database import get_session
from app.db.models import PriceHistory, Property, Score
from app.services.query import query_properties, serialize

router = APIRouter(prefix="/properties", tags=["properties"])


@router.get("")
def list_properties(
    session: Session = Depends(get_session),
    min_score: Optional[float] = Query(None),
    max_price: Optional[float] = Query(None),
    typology: Optional[str] = Query(None),
    municipality: Optional[str] = Query(None),
    max_distance_to_metro: Optional[float] = Query(None),
    min_gross_yield: Optional[float] = Query(None),
    only_price_drops: bool = Query(False),
    only_new: bool = Query(False),
    has_garage: Optional[bool] = Query(None),
    has_elevator: Optional[bool] = Query(None),
    exclude_ground_floor: bool = Query(False),
    exclude_no_coordinates: bool = Query(False),
    sort: str = Query("score_desc"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    results = query_properties(
        session,
        min_score=min_score,
        max_price=max_price,
        typology=typology,
        municipality=municipality,
        max_distance_to_metro=max_distance_to_metro,
        min_gross_yield=min_gross_yield,
        only_price_drops=only_price_drops,
        only_new=only_new,
        has_garage=has_garage,
        has_elevator=has_elevator,
        exclude_ground_floor=exclude_ground_floor,
        exclude_no_coordinates=exclude_no_coordinates,
        sort=sort,
        limit=limit,
        offset=offset,
    )
    return [serialize(p, s) for p, s in results]


@router.get("/top")
def top_properties(
    session: Session = Depends(get_session),
    limit: int = Query(20, ge=1, le=200),
    min_score: Optional[float] = Query(None),
):
    results = query_properties(session, sort="score_desc", limit=limit, min_score=min_score)
    return [serialize(p, s) for p, s in results]


@router.get("/new")
def new_properties(
    session: Session = Depends(get_session),
    limit: int = Query(50, ge=1, le=500),
):
    results = query_properties(session, only_new=True, sort="newest", limit=limit)
    return [serialize(p, s) for p, s in results]


@router.get("/price-drops")
def price_drops(
    session: Session = Depends(get_session),
    limit: int = Query(50, ge=1, le=500),
):
    results = query_properties(session, only_price_drops=True, sort="biggest_drop", limit=limit)
    return [serialize(p, s) for p, s in results]


@router.get("/sold")
def sold_properties(
    session: Session = Depends(get_session),
    limit: int = Query(100, ge=1, le=500),
):
    """Delisted listings (sold / withdrawn / expired) with their last asking price."""
    results = query_properties(
        session, only_delisted=True, active_only=False, sort="delisted_desc", limit=limit
    )
    return [serialize(p, s) for p, s in results]


@router.get("/{property_id}")
def get_property(property_id: int, session: Session = Depends(get_session)):
    prop = session.get(Property, property_id)
    if not prop:
        raise HTTPException(status_code=404, detail="Property not found")
    score = session.get(Score, property_id)
    history = session.exec(
        select(PriceHistory)
        .where(PriceHistory.property_id == property_id)
        .order_by(PriceHistory.observed_at)
    ).all()
    data = serialize(prop, score)
    data["price_history"] = [
        {"price": h.price, "observed_at": h.observed_at} for h in history
    ]
    data["explanation"] = score.explanation_json if score else None
    return data
