"""Per-user deal pipeline (each Telegram user has their own watchlist)."""
from collections import Counter
from typing import Optional

from sqlmodel import Session, select

from app.db.models import Property, Score, UserWatch, utcnow
from app.services.watchlist import normalize_status


def set_watch(session: Session, telegram_id: int, property_id: int,
              status: str, note: str) -> Optional[UserWatch]:
    """Upsert the user's watch for a property; delete it if both fields are empty."""
    status = normalize_status(status)
    note = (note or "").strip() or None
    row = session.get(UserWatch, (int(telegram_id), int(property_id)))
    if not status and not note:
        if row:
            session.delete(row)
            session.commit()
        return None
    if row is None:
        row = UserWatch(telegram_id=int(telegram_id), property_id=int(property_id))
    row.status = status
    row.note = note
    row.updated_at = utcnow()
    session.add(row)
    session.commit()
    return row


def get_map(session: Session, telegram_id: int, property_ids: list[int]) -> dict:
    """{property_id: UserWatch} for the given user and properties (for overlay)."""
    if not property_ids:
        return {}
    rows = session.exec(
        select(UserWatch).where(
            UserWatch.telegram_id == int(telegram_id),
            UserWatch.property_id.in_(property_ids),
        )
    ).all()
    return {r.property_id: r for r in rows}


def list_watched(session: Session, telegram_id: int, status: Optional[str] = None):
    """The user's watched properties as (Property, Score, UserWatch), newest first."""
    stmt = (
        select(Property, Score, UserWatch)
        .join(UserWatch, UserWatch.property_id == Property.id)
        .outerjoin(Score, Score.property_id == Property.id)
        .where(UserWatch.telegram_id == int(telegram_id))
    )
    if status:
        stmt = stmt.where(UserWatch.status == status)
    stmt = stmt.order_by(UserWatch.updated_at.desc())
    return session.exec(stmt).all()


def counts(session: Session, telegram_id: int) -> dict:
    rows = session.exec(
        select(UserWatch.status).where(UserWatch.telegram_id == int(telegram_id))
    ).all()
    return dict(Counter(s for s in rows if s))
