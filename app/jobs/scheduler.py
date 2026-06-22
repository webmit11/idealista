"""APScheduler-based daily import scheduler."""
import logging
from typing import Optional

from apscheduler.schedulers.background import BackgroundScheduler
from sqlmodel import Session

from app.core.config import settings
from app.db.database import engine
from app.services.ingest import run_import
from app.services.providers.mock_provider import MockProvider

logger = logging.getLogger("scheduler")
_scheduler: Optional[BackgroundScheduler] = None


def _job() -> None:
    logger.info(
        "scheduled import starting",
        extra={"extra_fields": {"provider": settings.scheduler_provider}},
    )
    try:
        if settings.scheduler_provider == "mock":
            # Daily run is a full refresh -> deactivate listings that disappeared.
            with Session(engine) as session:
                run_import(session, MockProvider(), deactivate_missing=True)
        else:
            # Full multi-area refresh, recorded in refresh_runs (shares the
            # once-per-day limit with the manual button).
            from app.services.refresh_service import run_now_recorded

            run_now_recorded()
    except Exception:
        logger.exception("scheduled import failed")


def start_scheduler() -> BackgroundScheduler:
    global _scheduler
    if _scheduler:
        return _scheduler
    _scheduler = BackgroundScheduler(timezone="UTC")
    _scheduler.add_job(
        _job,
        "cron",
        hour=settings.daily_import_hour,
        minute=settings.daily_import_minute,
        id="daily_import",
        replace_existing=True,
    )
    _scheduler.start()
    logger.info(
        "scheduler started",
        extra={
            "extra_fields": {
                "hour": settings.daily_import_hour,
                "minute": settings.daily_import_minute,
                "provider": settings.scheduler_provider,
            }
        },
    )
    return _scheduler


def shutdown_scheduler() -> None:
    global _scheduler
    if _scheduler:
        _scheduler.shutdown(wait=False)
        _scheduler = None
