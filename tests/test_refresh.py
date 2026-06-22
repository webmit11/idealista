from datetime import datetime, timedelta

from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.db.models import RefreshRun
from app.services.refresh_service import refresh_status


def _session() -> Session:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    SQLModel.metadata.create_all(engine)
    return Session(engine)


def test_can_refresh_when_no_runs():
    with _session() as s:
        assert refresh_status(s)["can"] is True


def test_blocked_within_24h():
    with _session() as s:
        s.add(RefreshRun(started_at=datetime.utcnow(), finished_at=datetime.utcnow(), ok=True))
        s.commit()
        st = refresh_status(s)
        assert st["can"] is False
        assert st["reason"] == "too_soon"
        assert st["next_allowed"] is not None


def test_allowed_after_a_day():
    with _session() as s:
        old = datetime.utcnow() - timedelta(hours=25)
        s.add(RefreshRun(started_at=old, finished_at=old, ok=True))
        s.commit()
        assert refresh_status(s)["can"] is True


def test_blocked_while_running():
    with _session() as s:
        s.add(RefreshRun(started_at=datetime.utcnow(), finished_at=None))  # in progress
        s.commit()
        st = refresh_status(s)
        assert st["can"] is False
        assert st["reason"] == "running"
