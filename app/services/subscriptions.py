"""Subscription state: who has paid access and until when.

The owner (settings.telegram_owner_id) is always active. Everyone else needs a
Subscriber row with subscription_until in the future (set by Stars payments).
"""
from datetime import datetime, timedelta
from typing import Optional

from sqlmodel import Session

from app.core.config import settings
from app.db.models import Subscriber


def is_owner(telegram_id: int) -> bool:
    return settings.telegram_owner_id is not None and int(telegram_id) == settings.telegram_owner_id


def is_active(session: Session, telegram_id: int) -> bool:
    if is_owner(telegram_id):
        return True
    sub = session.get(Subscriber, int(telegram_id))
    return bool(sub and sub.subscription_until and sub.subscription_until > datetime.utcnow())


def status(session: Session, telegram_id: int) -> dict:
    if is_owner(telegram_id):
        return {"active": True, "owner": True, "until": None}
    sub = session.get(Subscriber, int(telegram_id))
    active = bool(sub and sub.subscription_until and sub.subscription_until > datetime.utcnow())
    return {
        "active": active,
        "owner": False,
        "until": sub.subscription_until.isoformat() if (sub and sub.subscription_until) else None,
    }


def activate(
    session: Session,
    telegram_id: int,
    *,
    until: Optional[datetime] = None,
    charge_id: Optional[str] = None,
    is_recurring: bool = False,
    user: Optional[dict] = None,
) -> Subscriber:
    """Grant or extend access. If `until` is None, extend by one period from the
    later of now / current expiry (so manual grants stack)."""
    sub = session.get(Subscriber, int(telegram_id))
    if sub is None:
        sub = Subscriber(telegram_id=int(telegram_id))
    if until is None:
        base = sub.subscription_until if (sub.subscription_until and sub.subscription_until > datetime.utcnow()) else datetime.utcnow()
        until = base + timedelta(days=settings.subscription_period_days)
    sub.subscription_until = until
    if charge_id:
        sub.last_charge_id = charge_id
    sub.is_recurring = is_recurring or sub.is_recurring
    if user:
        sub.username = user.get("username") or sub.username
        sub.first_name = user.get("first_name") or sub.first_name
    sub.updated_at = datetime.utcnow()
    session.add(sub)
    session.commit()
    return sub
