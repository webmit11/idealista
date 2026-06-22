from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.db.models import Property
from app.services.query import VALID_SORTS, count_properties, query_properties


def _session() -> Session:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    SQLModel.metadata.create_all(engine)
    return Session(engine)


def _seed(s: Session, n: int):
    for i in range(n):
        s.add(Property(
            source="apify_idealista", external_id=f"P{i}", is_active=True,
            price=100000 + i * 1000, typology="T2", area_m2=50 + i,
        ))
    s.commit()


def test_count_respects_filters():
    with _session() as s:
        _seed(s, 7)
        s.add(Property(source="apify_idealista", external_id="X", is_active=False, price=1))
        s.commit()
        assert count_properties(s) == 7  # inactive excluded
        assert count_properties(s, max_price=103000) == 4  # 100k..103k


def test_pagination_offset_limit_no_overlap():
    with _session() as s:
        _seed(s, 7)
        page1 = query_properties(s, sort="price_asc", limit=3, offset=0)
        page2 = query_properties(s, sort="price_asc", limit=3, offset=3)
        ids1 = {p.id for p, _ in page1}
        ids2 = {p.id for p, _ in page2}
        assert len(page1) == 3 and len(page2) == 3
        assert ids1.isdisjoint(ids2)
        prices1 = [p.price for p, _ in page1]
        assert prices1 == sorted(prices1)  # ascending


def test_exclude_bad_neighborhoods():
    with _session() as s:
        s.add(Property(source="apify_idealista", external_id="OK", is_active=True,
                       parish="Bonfim", district="Baixa", price=200000))
        s.add(Property(source="apify_idealista", external_id="BAD", is_active=True,
                       parish="Lordelo do Ouro e Massarelos", district="Pasteleira", price=150000))
        s.commit()
        assert count_properties(s) == 2
        assert count_properties(s, exclude_bad_neighborhoods=True) == 1
        rows = query_properties(s, exclude_bad_neighborhoods=True, limit=50)
        assert [p.external_id for p, _ in rows] == ["OK"]


def test_only_exact_location():
    with _session() as s:
        s.add(Property(source="apify_idealista", external_id="E", is_active=True, exact_location=True, price=1))
        s.add(Property(source="apify_idealista", external_id="A", is_active=True, exact_location=False, price=1))
        s.add(Property(source="apify_idealista", external_id="U", is_active=True, exact_location=None, price=1))
        s.commit()
        assert count_properties(s, only_exact_location=True) == 1
        rows = query_properties(s, only_exact_location=True, limit=50)
        assert [p.external_id for p, _ in rows] == ["E"]


def test_only_delisted():
    with _session() as s:
        s.add(Property(source="apify_idealista", external_id="A", is_active=True, price=1))
        s.add(Property(source="apify_idealista", external_id="D", is_active=False, price=1))
        s.commit()
        assert count_properties(s, only_delisted=True, active_only=False) == 1
        rows = query_properties(s, only_delisted=True, active_only=False, limit=50)
        assert [p.external_id for p, _ in rows] == ["D"]


def test_new_within_days_filter():
    from datetime import datetime, timedelta
    with _session() as s:
        s.add(Property(source="apify_idealista", external_id="FRESH", is_active=True,
                       price=1, first_seen_at=datetime.utcnow()))
        s.add(Property(source="apify_idealista", external_id="OLD", is_active=True,
                       price=1, first_seen_at=datetime.utcnow() - timedelta(days=30)))
        s.commit()
        assert count_properties(s, new_within_days=7) == 1
        rows = query_properties(s, new_within_days=7, sort="newest", limit=50)
        assert [p.external_id for p, _ in rows] == ["FRESH"]


def test_new_sort_keys_available():
    for key in ("ppm2_desc", "area_asc", "distance_desc", "price_desc", "yield_asc", "oldest", "delisted_desc"):
        assert key in VALID_SORTS
