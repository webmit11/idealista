from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.db.models import Property
from app.services.query import count_properties, query_properties
from app.services.watchlist import normalize_status


def _session() -> Session:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    SQLModel.metadata.create_all(engine)
    return Session(engine)


def test_normalize_status():
    assert normalize_status("offer") == "offer"
    assert normalize_status(" offer ") == "offer"
    assert normalize_status("garbage") is None
    assert normalize_status("") is None
    assert normalize_status(None) is None


def test_watched_only_and_status_filter():
    with _session() as s:
        s.add(Property(source="x", external_id="A", is_active=True, watch_status="offer", price=1))
        s.add(Property(source="x", external_id="B", is_active=True, watch_status="rejected", price=1))
        s.add(Property(source="x", external_id="C", is_active=True, price=1))  # not watched
        s.commit()
        assert count_properties(s, watched_only=True) == 2
        rows = query_properties(s, watched_only=True, watch_status="offer", limit=50)
        assert [p.external_id for p, _ in rows] == ["A"]
