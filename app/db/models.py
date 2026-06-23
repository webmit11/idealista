"""SQLModel ORM models."""
from datetime import datetime
from typing import Optional

from sqlalchemy import JSON, UniqueConstraint
from sqlmodel import Field, Relationship, SQLModel


def utcnow() -> datetime:
    return datetime.utcnow()


class Property(SQLModel, table=True):
    __tablename__ = "properties"
    __table_args__ = (
        UniqueConstraint("source", "external_id", name="uq_source_external_id"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    external_id: str = Field(index=True)
    source: str = Field(index=True)
    url: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = None
    expert_text: Optional[str] = None  # cached LLM-written expert commentary
    expert_delta: Optional[int] = None  # vision-based score adjustment (-10..+10)

    price: Optional[float] = Field(default=None, index=True)
    previous_price: Optional[float] = None
    price_drop_amount: Optional[float] = None
    price_drop_percent: Optional[float] = Field(default=None, index=True)

    property_type: Optional[str] = None
    typology: Optional[str] = Field(default=None, index=True)  # T0/T1/T2/T3/T4...
    area_m2: Optional[float] = None
    price_per_m2: Optional[float] = Field(default=None, index=True)
    rooms: Optional[int] = None
    bathrooms: Optional[int] = None
    floor: Optional[int] = None

    has_elevator: Optional[bool] = None
    has_garage: Optional[bool] = None
    has_balcony: Optional[bool] = None
    has_terrace: Optional[bool] = None
    # Ad states an Alojamento Local (short-term rental) licence — heuristic over text.
    has_al_license: Optional[bool] = Field(default=None, index=True)
    # Owner manual override of the AL flag: None = auto (detector), True/False = forced.
    al_override: Optional[bool] = None
    condition: Optional[str] = None  # new/renovated/good/to_renovate/unknown
    energy_certificate: Optional[str] = None

    address_raw: Optional[str] = None
    parish: Optional[str] = Field(default=None, index=True)
    municipality: Optional[str] = Field(default=None, index=True)
    district: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    # False = advertiser hid the exact address -> coordinates are approximate
    # (street/zona centre), so distance_to_metro_m is only indicative.
    exact_location: Optional[bool] = None

    nearest_metro_station: Optional[str] = None
    distance_to_metro_m: Optional[float] = Field(default=None, index=True)
    walking_minutes_to_metro_estimate: Optional[float] = None

    # Derived financial metrics (cached for filtering/sorting; MVP extension).
    rental_estimate_low: Optional[float] = None
    rental_estimate_mid: Optional[float] = None
    rental_estimate_high: Optional[float] = None
    gross_yield_percent: Optional[float] = Field(default=None, index=True)

    listing_agency: Optional[str] = None
    thumbnail_url: Optional[str] = None
    image_urls: Optional[list] = Field(default=None, sa_type=JSON)
    first_seen_at: datetime = Field(default_factory=utcnow)
    last_seen_at: datetime = Field(default_factory=utcnow)
    is_active: bool = Field(default=True, index=True)
    # When the listing disappeared from a full refresh (sold / withdrawn / expired).
    # `price` at that point is the last asking price ("за сколько ушло").
    delisted_at: Optional[datetime] = Field(default=None, index=True)
    days_on_market: Optional[int] = None
    images_count: Optional[int] = None

    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)

    # Deal pipeline (user state; never overwritten by imports).
    watch_status: Optional[str] = Field(default=None, index=True)
    watch_note: Optional[str] = None
    watch_updated_at: Optional[datetime] = None

    score: Optional["Score"] = Relationship(
        back_populates="property",
        sa_relationship_kwargs={"uselist": False, "cascade": "all, delete-orphan"},
    )
    price_history: list["PriceHistory"] = Relationship(
        back_populates="property",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )


class PriceHistory(SQLModel, table=True):
    __tablename__ = "price_history"

    id: Optional[int] = Field(default=None, primary_key=True)
    property_id: int = Field(foreign_key="properties.id", index=True)
    price: float
    observed_at: datetime = Field(default_factory=utcnow)

    property: Optional[Property] = Relationship(back_populates="price_history")


class SearchProfile(SQLModel, table=True):
    __tablename__ = "search_profiles"

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    municipalities: list[str] = Field(default_factory=list, sa_type=JSON)
    metro_stations: list[str] = Field(default_factory=list, sa_type=JSON)
    min_price: Optional[float] = None
    max_price: Optional[float] = None
    typologies: list[str] = Field(default_factory=list, sa_type=JSON)
    min_area_m2: Optional[float] = None
    max_distance_to_metro_m: Optional[float] = None
    require_elevator: bool = False
    require_garage: bool = False
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class RefreshRun(SQLModel, table=True):
    """One manual/scheduled full-refresh run (for the dashboard button + rate limit)."""
    __tablename__ = "refresh_runs"

    id: Optional[int] = Field(default=None, primary_key=True)
    started_at: datetime = Field(default_factory=utcnow, index=True)
    finished_at: Optional[datetime] = None
    ok: Optional[bool] = None
    stats_json: dict = Field(default_factory=dict, sa_type=JSON)
    error: Optional[str] = None


class Score(SQLModel, table=True):
    __tablename__ = "scores"

    property_id: int = Field(foreign_key="properties.id", primary_key=True)
    total_score: float = 0.0
    price_score: float = 0.0
    metro_score: float = 0.0
    liquidity_score: float = 0.0
    rental_yield_score: float = 0.0
    condition_score: float = 0.0
    discount_score: float = 0.0
    risk_score: float = 0.0  # penalty points (0-20), already subtracted from total
    explanation_json: dict = Field(default_factory=dict, sa_type=JSON)
    calculated_at: datetime = Field(default_factory=utcnow)

    property: Optional[Property] = Relationship(back_populates="score")


class UserWatch(SQLModel, table=True):
    """Per-user deal pipeline: one row per (telegram user, property)."""
    __tablename__ = "user_watches"

    telegram_id: int = Field(primary_key=True)
    property_id: int = Field(foreign_key="properties.id", primary_key=True)
    status: Optional[str] = None
    note: Optional[str] = None
    updated_at: datetime = Field(default_factory=utcnow)


class Subscriber(SQLModel, table=True):
    """A Telegram user with paid access (Stars subscription)."""
    __tablename__ = "subscribers"

    telegram_id: int = Field(primary_key=True)
    username: Optional[str] = None
    first_name: Optional[str] = None
    subscription_until: Optional[datetime] = Field(default=None, index=True)
    is_recurring: bool = False
    last_charge_id: Optional[str] = None
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class SavedFilter(SQLModel, table=True):
    """A subscriber's saved search; new listings matching it trigger a Telegram alert."""
    __tablename__ = "saved_filters"

    id: Optional[int] = Field(default=None, primary_key=True)
    telegram_id: int = Field(index=True)
    name: Optional[str] = None
    criteria_json: dict = Field(default_factory=dict, sa_type=JSON)
    active: bool = True
    created_at: datetime = Field(default_factory=utcnow)
    last_notified_at: Optional[datetime] = None
