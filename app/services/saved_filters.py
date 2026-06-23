"""Saved searches: subscribers store filter criteria and get a Telegram alert
when the daily refresh discovers new listings matching them."""
import logging
from datetime import datetime
from typing import Optional

from sqlmodel import Session, select

from app.core.config import settings
from app.db.models import SavedFilter
from app.services import subscriptions
from app.services.query import query_properties, serialize
from app.services.telegram_api import send_message

logger = logging.getLogger("saved_filters")

MAX_PER_USER = 10

# Filter keys accepted from the client, grouped by how they are coerced.
_NUM_KEYS = ("min_score", "max_price", "max_distance_to_metro", "min_gross_yield")
_STR_KEYS = ("typology", "municipality")
# has_* map to Optional[bool] in query_properties; the rest are plain flags.
_TRI_BOOL_KEYS = ("has_garage", "has_elevator", "has_terrace")
_FLAG_KEYS = ("south_facing", "only_price_drops", "only_new", "exclude_ground_floor",
              "exclude_no_coordinates", "exclude_bad_neighborhoods", "only_exact_location",
              "expert_positive")


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _truthy(v) -> bool:
    return str(v).lower() in ("1", "true", "yes", "on")


def clean_criteria(raw: Optional[dict]) -> dict:
    """Whitelist + normalize a criteria dict coming from the client."""
    raw = raw or {}
    out: dict = {}
    for k in _NUM_KEYS:
        if k in raw and _num(raw[k]) is not None:
            out[k] = _num(raw[k])
    for k in _STR_KEYS:
        if raw.get(k):
            out[k] = str(raw[k])
    for k in _TRI_BOOL_KEYS + _FLAG_KEYS:
        if _truthy(raw.get(k)):
            out[k] = True
    return out


def _to_kwargs(criteria: dict) -> dict:
    """Criteria -> query_properties kwargs. Saved searches are resale apartments."""
    c = clean_criteria(criteria)
    kw: dict = {"only_developments": False}
    for k in _NUM_KEYS + _STR_KEYS + _TRI_BOOL_KEYS + _FLAG_KEYS:
        if k in c:
            kw[k] = c[k]
    return kw


def describe(criteria: dict) -> str:
    """Short human label for a criteria set (default subscription name)."""
    c = clean_criteria(criteria)
    parts = []
    if c.get("typology"):
        parts.append(str(c["typology"]))
    if c.get("municipality"):
        parts.append(str(c["municipality"]))
    if c.get("max_price"):
        parts.append(f"≤{int(c['max_price'] / 1000)}k€")
    if c.get("min_gross_yield"):
        parts.append(f"{c['min_gross_yield']:g}%+")
    if c.get("min_score"):
        parts.append(f"балл {int(c['min_score'])}+")
    if c.get("max_distance_to_metro"):
        parts.append(f"метро ≤{int(c['max_distance_to_metro'])}м")
    return " · ".join(parts) or "Все новые объекты"


def list_for(session: Session, telegram_id: int) -> list:
    return session.exec(
        select(SavedFilter)
        .where(SavedFilter.telegram_id == telegram_id)
        .order_by(SavedFilter.created_at.desc())
    ).all()


def create(session: Session, telegram_id: int, name: Optional[str], criteria: dict) -> Optional[SavedFilter]:
    c = clean_criteria(criteria)
    if len(list_for(session, telegram_id)) >= MAX_PER_USER:
        return None
    sf = SavedFilter(telegram_id=telegram_id, name=(name or describe(c))[:80], criteria_json=c)
    session.add(sf)
    session.commit()
    session.refresh(sf)
    return sf


def delete(session: Session, telegram_id: int, filter_id: int) -> bool:
    sf = session.get(SavedFilter, filter_id)
    if not sf or sf.telegram_id != telegram_id:
        return False
    session.delete(sf)
    session.commit()
    return True


def set_active(session: Session, telegram_id: int, filter_id: int, active: bool) -> bool:
    sf = session.get(SavedFilter, filter_id)
    if not sf or sf.telegram_id != telegram_id:
        return False
    sf.active = bool(active)
    session.add(sf)
    session.commit()
    return True


def _fmt_price(v) -> str:
    return (f"{round(v):,}".replace(",", " ") + " €") if v else "—"


def notify_new(session: Session, created_ids, dropped_ids=None) -> int:
    """For each active saved filter owned by an active subscriber, alert about new
    listings discovered this run that match it. Returns number of messages sent."""
    ids = list(dict.fromkeys(created_ids or []))
    if not ids or not settings.telegram_bot_token:
        return 0
    base = (settings.public_base_url or settings.app_base_url or "").rstrip("/")
    filters = session.exec(select(SavedFilter).where(SavedFilter.active == True)).all()  # noqa: E712
    sent = 0
    for sf in filters:
        if not subscriptions.is_active(session, sf.telegram_id):
            continue
        rows = query_properties(session, ids=ids, sort="score_desc", limit=8, **_to_kwargs(sf.criteria_json))
        hits = [serialize(p, s) for p, s in rows]
        if not hits:
            continue
        lines = [f"🔔 <b>{len(hits)}</b> новых по подписке «{sf.name}»:"]
        buttons = []
        for d in hits:
            score = d.get("total_score")
            yld = d.get("gross_yield_percent")
            lines.append(
                f"• {round(score) if score is not None else '—'} · {d.get('typology') or '?'} · "
                f"{d.get('municipality') or ''} · {_fmt_price(d.get('price'))}"
                f"{(' · %.1f%%' % yld) if yld is not None else ''}"
            )
            buttons.append([{
                "text": f"{d.get('typology') or '?'} · {_fmt_price(d.get('price'))}",
                "web_app": {"url": f"{base}/app?p={d['id']}"},
            }])
        try:
            send_message(sf.telegram_id, "\n".join(lines), reply_markup={"inline_keyboard": buttons})
            sf.last_notified_at = datetime.utcnow()
            session.add(sf)
            sent += 1
        except Exception as exc:
            logger.warning("saved-filter notify failed for %s: %s", sf.telegram_id, exc)
    if sent:
        session.commit()
    return sent
