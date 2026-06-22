"""Price history helpers."""
from datetime import datetime
from typing import Optional

from sqlmodel import Session

from app.db.models import PriceHistory


def compute_drop(previous: Optional[float], current: Optional[float]) -> tuple[Optional[float], Optional[float]]:
    """Return (drop_amount, drop_percent). Positive => price went down."""
    if not previous or not current or previous <= 0:
        return None, None
    amount = round(previous - current, 2)
    percent = round((previous - current) / previous * 100, 2)
    return amount, percent


def add_history(
    session: Session,
    property_id: int,
    price: float,
    observed_at: Optional[datetime] = None,
) -> None:
    session.add(
        PriceHistory(
            property_id=property_id,
            price=price,
            observed_at=observed_at or datetime.utcnow(),
        )
    )
