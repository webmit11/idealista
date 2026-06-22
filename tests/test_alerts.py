from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.core.config import settings
from app.db.models import Property, Score
from app.services.alerts import build_alert_events, format_alert_message
from app.services.notifier import Notifier


def _session() -> Session:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    SQLModel.metadata.create_all(engine)
    return Session(engine)


def test_build_alert_events_filters_by_score_and_drop():
    with _session() as s:
        p1 = Property(source="apify_idealista", external_id="H1", is_active=True, typology="T2", price=200000)
        p2 = Property(source="apify_idealista", external_id="L1", is_active=True, typology="T2", price=200000)
        p3 = Property(source="apify_idealista", external_id="D1", is_active=True, typology="T2",
                      price=180000, price_drop_percent=8.0)
        p4 = Property(source="apify_idealista", external_id="D2", is_active=True, typology="T2",
                      price=190000, price_drop_percent=2.0)
        s.add_all([p1, p2, p3, p4])
        s.commit()
        s.add_all([
            Score(property_id=p1.id, total_score=82),
            Score(property_id=p2.id, total_score=50),   # below min_score
            Score(property_id=p3.id, total_score=60),
            Score(property_id=p4.id, total_score=60),
        ])
        s.commit()

        hits, drops = build_alert_events(
            s, created_ids=[p1.id, p2.id], dropped_ids=[p3.id, p4.id],
            min_score=75, min_drop=5,
        )
        assert [h["external_id"] for h in hits] == ["H1"]
        assert [d["external_id"] for d in drops] == ["D1"]  # D2 below 5%


def test_format_alert_message_contains_links_and_counts():
    hits = [{
        "id": 1, "external_id": "H1", "total_score": 82, "typology": "T2",
        "municipality": "Maia", "nearest_metro_station": "Parque Maia",
        "price": 190000, "gross_yield_percent": 6.3, "distance_to_metro_m": 120,
    }]
    drops = [{
        "id": 2, "external_id": "D1", "price_drop_percent": 8.0, "typology": "T2",
        "municipality": "Matosinhos", "price": 215000, "previous_price": 235000,
    }]
    msg = format_alert_message(hits, drops)
    assert "1 new hits, 1 price drops" in msg
    assert "/property/1" in msg and "/property/2" in msg
    assert "-8.0%" in msg


def test_format_alert_message_empty():
    assert "0 new hits, 0 price drops" in format_alert_message([], [])


def test_notifier_channel_resolution(monkeypatch):
    monkeypatch.setattr(settings, "alert_channel", "auto")
    monkeypatch.setattr(settings, "telegram_bot_token", "t")
    monkeypatch.setattr(settings, "telegram_chat_id", "c")
    assert Notifier().channel == "telegram"

    monkeypatch.setattr(settings, "telegram_bot_token", None)
    monkeypatch.setattr(settings, "smtp_host", "smtp.example")
    monkeypatch.setattr(settings, "alert_email_to", "a@b.c")
    assert Notifier().channel == "email"

    monkeypatch.setattr(settings, "smtp_host", None)
    monkeypatch.setattr(settings, "alert_email_to", None)
    assert Notifier().channel == "none"
    assert Notifier().is_configured() is False
