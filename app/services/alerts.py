"""Build and send alerts for new high-score listings and price drops.

Only listings that became new / dropped in price *during the current run* are
passed in, so there is no re-alerting across runs.
"""
import logging
from typing import Optional

from sqlmodel import Session

from app.core.config import settings
from app.db.models import Property, Score
from app.services.notifier import Notifier
from app.services.query import serialize

logger = logging.getLogger("alerts")

_MAX_PER_SECTION = 15


def _fmt_price(value) -> str:
    if not value:
        return "—"
    return f"{round(value):,}".replace(",", ".") + " €"


def build_alert_events(
    session: Session,
    created_ids: list[int],
    dropped_ids: list[int],
    min_score: Optional[float] = None,
    min_drop: Optional[float] = None,
) -> tuple[list[dict], list[dict]]:
    min_score = settings.alert_min_score if min_score is None else min_score
    min_drop = settings.alert_min_price_drop if min_drop is None else min_drop

    new_hits: list[dict] = []
    for pid in dict.fromkeys(created_ids):  # de-dupe, keep order
        prop = session.get(Property, pid)
        score = session.get(Score, pid)
        if prop and prop.is_active and score and (score.total_score or 0) >= min_score:
            new_hits.append(serialize(prop, score))

    price_drops: list[dict] = []
    for pid in dict.fromkeys(dropped_ids):
        prop = session.get(Property, pid)
        score = session.get(Score, pid)
        if prop and prop.is_active and (prop.price_drop_percent or 0) >= min_drop:
            price_drops.append(serialize(prop, score))

    new_hits.sort(key=lambda d: -(d.get("total_score") or 0))
    price_drops.sort(key=lambda d: -(d.get("price_drop_percent") or 0))
    return new_hits, price_drops


def format_alert_message(new_hits: list[dict], price_drops: list[dict]) -> str:
    base = settings.app_base_url.rstrip("/")
    lines = [
        f"🏠 Porto Investment Finder — {len(new_hits)} new hits, {len(price_drops)} price drops",
    ]

    if new_hits:
        lines.append(f"\n🟢 NEW HITS (score ≥ {settings.alert_min_score:.0f}):")
        for d in new_hits[:_MAX_PER_SECTION]:
            score = d.get("total_score")
            yld = d.get("gross_yield_percent")
            lines.append(
                f"• {round(score) if score is not None else '—'} · {d.get('typology') or '?'} · "
                f"{d.get('municipality') or ''}/{d.get('nearest_metro_station') or '?'} · "
                f"{_fmt_price(d.get('price'))} · "
                f"{('%.1f%%' % yld) if yld is not None else '—'} · "
                f"{round(d['distance_to_metro_m']) if d.get('distance_to_metro_m') is not None else '?'}m\n"
                f"  {base}/property/{d['id']}"
            )

    if price_drops:
        lines.append(f"\n🔻 PRICE DROPS (≥ {settings.alert_min_price_drop:.0f}%):")
        for d in price_drops[:_MAX_PER_SECTION]:
            lines.append(
                f"• -{d['price_drop_percent']:.1f}% · {d.get('typology') or '?'} · "
                f"{d.get('municipality') or ''} · {_fmt_price(d.get('price'))} "
                f"(was {_fmt_price(d.get('previous_price'))})\n"
                f"  {base}/property/{d['id']}"
            )

    return "\n".join(lines)


def send_run_alerts(session: Session, created_ids: list[int], dropped_ids: list[int]) -> int:
    """Build and send alerts for this run. Returns number of events sent."""
    notifier = Notifier()
    if not notifier.is_configured():
        logger.info(
            "alerts enabled but no channel configured",
            extra={"extra_fields": {"channel": notifier.channel}},
        )
        return 0

    new_hits, price_drops = build_alert_events(session, created_ids, dropped_ids)
    total = len(new_hits) + len(price_drops)
    if total == 0:
        return 0

    notifier.send(format_alert_message(new_hits, price_drops))
    logger.info(
        "alerts dispatched",
        extra={"extra_fields": {"new_hits": len(new_hits), "price_drops": len(price_drops)}},
    )
    return total
