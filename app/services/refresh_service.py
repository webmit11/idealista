"""Manual full-refresh trigger with a once-per-day rate limit.

The refresh runs in a background thread so the HTTP request returns immediately;
progress/result is recorded in the RefreshRun table.
"""
import logging
import threading
from datetime import datetime, timedelta
from typing import Optional

from sqlmodel import Session, select

from app.core.config import settings
from app.db.database import engine
from app.db.models import RefreshRun
from app.services.ingest import run_areas_refresh
from app.services.providers.apify_idealista import ApifyIdealistaProvider
from app.services.search_areas import DEFAULT_SEARCH_AREAS

logger = logging.getLogger("refresh")

# A run still marked unfinished after this is considered stale (e.g. app crashed).
_STALE_AFTER = timedelta(hours=1)


def latest_run(session: Session) -> Optional[RefreshRun]:
    return session.exec(
        select(RefreshRun).order_by(RefreshRun.started_at.desc())
    ).first()


def _in_progress(run: Optional[RefreshRun]) -> bool:
    return (
        run is not None
        and run.finished_at is None
        and (datetime.utcnow() - run.started_at) < _STALE_AFTER
    )


def refresh_status(session: Session) -> dict:
    run = latest_run(session)
    interval = timedelta(hours=settings.manual_refresh_min_interval_hours)
    running = _in_progress(run)
    can, reason, next_allowed = True, None, None
    if running:
        can, reason = False, "running"
    elif run and (datetime.utcnow() - run.started_at) < interval:
        can, reason, next_allowed = False, "too_soon", run.started_at + interval
    return {"can": can, "reason": reason, "running": running, "last": run, "next_allowed": next_allowed}


def _run_in_background(run_id: int) -> None:
    with Session(engine) as session:
        ok, err, stats = True, None, {}
        try:
            stats = run_areas_refresh(
                session,
                ApifyIdealistaProvider(),
                DEFAULT_SEARCH_AREAS,
                max_items=settings.manual_refresh_max_items,
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("manual refresh failed")
            ok, err = False, str(exc)[:500]
        run = session.get(RefreshRun, run_id)
        if run:
            run.finished_at = datetime.utcnow()
            run.ok = ok
            run.stats_json = stats
            run.error = err
            session.add(run)
            session.commit()


def run_now_recorded() -> None:
    """Create a RefreshRun and execute it synchronously (used by the scheduler).

    Recording it means a scheduled run also counts toward the manual button's
    once-per-day limit, so they don't double-scrape on the same day.
    """
    with Session(engine) as session:
        run = RefreshRun()
        session.add(run)
        session.commit()
        session.refresh(run)
        run_id = run.id
    _run_in_background(run_id)


def trigger_refresh(session: Session) -> dict:
    status = refresh_status(session)
    if not status["can"]:
        return status
    run = RefreshRun()
    session.add(run)
    session.commit()
    session.refresh(run)
    threading.Thread(target=_run_in_background, args=(run.id,), daemon=True).start()
    logger.info("manual refresh started", extra={"extra_fields": {"run_id": run.id}})
    return {"can": True, "reason": "started", "running": True, "last": run, "next_allowed": None}
