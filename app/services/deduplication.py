"""Listing de-duplication.

MVP strategy: a listing is identified by (source, external_id). A future
improvement is cross-source de-duplication by geo + area + price similarity;
`find_possible_duplicate` is a starting point for that.
"""
from typing import Optional

from sqlmodel import Session, select

from app.db.models import Property


def find_existing(session: Session, source: str, external_id: str) -> Optional[Property]:
    return session.exec(
        select(Property).where(
            Property.source == source,
            Property.external_id == str(external_id),
        )
    ).first()


def find_possible_duplicate(
    session: Session,
    latitude: Optional[float],
    longitude: Optional[float],
    area_m2: Optional[float],
    price: Optional[float],
    coord_tol: float = 0.0005,
    area_tol: float = 3.0,
) -> Optional[Property]:
    """Heuristic cross-source duplicate detection (not used by default)."""
    if latitude is None or longitude is None or area_m2 is None:
        return None
    candidates = session.exec(
        select(Property).where(
            Property.latitude.between(latitude - coord_tol, latitude + coord_tol),
            Property.longitude.between(longitude - coord_tol, longitude + coord_tol),
        )
    ).all()
    for c in candidates:
        if c.area_m2 and abs(c.area_m2 - area_m2) <= area_tol:
            if price is None or c.price is None or abs(c.price - price) <= 0.05 * price:
                return c
    return None
