"""Tests for ingest behaviours that need a database."""
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from app.db.models import Property
from app.services.ingest import deactivate_unseen


def _memory_session() -> Session:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,  # share one in-memory connection
    )
    SQLModel.metadata.create_all(engine)
    return Session(engine)


def test_deactivate_unseen_marks_only_missing_same_source():
    with _memory_session() as s:
        s.add(Property(source="apify_idealista", external_id="A", is_active=True))
        s.add(Property(source="apify_idealista", external_id="B", is_active=True))
        s.add(Property(source="mock", external_id="C", is_active=True))  # other source
        s.commit()

        n = deactivate_unseen(s, "apify_idealista", seen_external_ids={"A"})
        assert n == 1  # only B (apify, not seen)

        state = {p.external_id: p.is_active for p in s.exec(select(Property)).all()}
        assert state == {"A": True, "B": False, "C": True}


def test_deactivate_unseen_municipality_scope():
    with _memory_session() as s:
        s.add(Property(source="apify_idealista", external_id="G1", municipality="Gondomar", is_active=True))
        s.add(Property(source="apify_idealista", external_id="G2", municipality="Gondomar", is_active=True))
        s.add(Property(source="apify_idealista", external_id="P1", municipality="Porto", is_active=True))
        s.commit()
        # Gondomar fully fetched, only G1 seen -> G2 delisted; Porto untouched.
        n = deactivate_unseen(s, "apify_idealista", {"G1"}, municipality="Gondomar")
        assert n == 1
        state = {p.external_id: p.is_active for p in s.exec(select(Property)).all()}
        assert state == {"G1": True, "G2": False, "P1": True}


def test_deactivate_sets_delisted_at():
    with _memory_session() as s:
        p = Property(source="apify_idealista", external_id="B", is_active=True, price=200000)
        s.add(p)
        s.commit()
        deactivate_unseen(s, "apify_idealista", seen_external_ids=set())
        s.refresh(p)
        assert p.is_active is False
        assert p.delisted_at is not None  # recorded when it left the market
