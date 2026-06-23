"""Application configuration loaded from environment / .env file."""
from datetime import datetime
from functools import lru_cache
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- App ---
    app_name: str = "Porto Investment Finder"
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    debug: bool = False
    log_level: str = "INFO"
    log_json: bool = True

    # --- Auth (HTTP Basic) ---
    # Set dashboard_password to require login for everything except /health.
    # Empty password = auth disabled (open).
    dashboard_user: str = "admin"
    dashboard_password: str = ""

    # --- Database ---
    # For Docker Compose this points at the `db` service. For local runs you can
    # use e.g. sqlite:///./dev.db
    database_url: str = "postgresql+psycopg2://idealista:idealista@db:5432/idealista"

    # --- Apify (Idealista scraper) ---
    apify_token: Optional[str] = None
    # Apify actor id in URL form, e.g. "username~actor-name".
    apify_actor_id: str = "igolaizola~idealista-scraper"
    # Comma-separated Idealista search URLs used when none are passed explicitly.
    apify_search_urls: str = ""
    apify_max_items: int = 200
    apify_country: str = "pt"
    apify_timeout_s: int = 300
    # Drop new-development project listings (/empreendimento/) — not single resale units.
    apify_exclude_new_developments: bool = True
    # Drop houses (chalet / countryHouse / moradia) — keep only apartments.
    apify_exclude_houses: bool = True

    # --- Geo / metro ---
    # Walking speed used to turn metres into an estimated walking time.
    walking_speed_m_per_min: float = 80.0
    # Optional real pedestrian routing for distance/time to the nearest station.
    # Default "haversine" = straight-line ÷ walking_speed (no API calls, no cost).
    # Set to "ors" (OpenRouteService, free key) or "google" (Google Directions)
    # and provide the matching API key to get real walking routes instead.
    routing_provider: str = "haversine"  # haversine | ors | google
    ors_api_key: Optional[str] = None
    google_maps_api_key: Optional[str] = None
    # When routing, send the N nearest-by-air stations to the router and keep the
    # one that is actually closest to WALK to (handles rivers/highways in between).
    routing_candidates: int = 2

    # --- Scoring / benchmark ---
    benchmark_min_samples: int = 3
    new_listing_days: int = 7
    # Listings first seen before this datetime are never shown as "new" (keeps the
    # bulk-imported seed set out of the New tab; only genuinely new listings found
    # after this date count). Unset = pure rolling window. ISO date, e.g. 2026-06-24.
    new_listing_baseline: Optional[datetime] = None
    # Default minimum score on the dashboard (empty "Min score" field -> this).
    # Set 0 in the field to see everything.
    dashboard_min_score: float = 50.0
    # Metro proximity score is multiplied by this when the listing's location is
    # only approximate (advertiser hid the exact address) — the distance is less
    # reliable. 1.0 disables the adjustment.
    approx_location_metro_factor: float = 0.7
    # Bonus points added to the total score when the listing mentions south-facing
    # windows / orientation (more sun — valued in Portugal). 0 disables.
    south_facing_bonus: float = 4.0
    # Extra bad-neighborhood keywords (comma/newline separated), added to the
    # built-in list in app/services/bad_neighborhoods.py.
    bad_neighborhoods: str = ""

    # --- Alerts ---
    alerts_enabled: bool = False
    alert_channel: str = "auto"  # auto | telegram | email | none
    alert_min_score: float = 75.0
    alert_min_price_drop: float = 5.0  # percent
    app_base_url: str = "http://idealista.localhost"  # for links in alerts
    # Telegram
    telegram_bot_token: Optional[str] = None
    telegram_chat_id: Optional[str] = None
    # Telegram Mini App owner — always has full access (admin, free).
    telegram_owner_id: Optional[int] = None
    # --- Telegram Stars subscriptions ---
    trial_days: int = 1                          # free trial on first open (0 disables)
    subscription_price_stars: int = 500          # Stars/period (~$10 in-app to the buyer)
    subscription_period_days: int = 30           # Telegram supports 30-day periods
    subscription_title: str = "Porto Investment Finder — доступ"
    subscription_description: str = "Доступ к аналитике объектов у метро Порту на 30 дней."
    # Secret embedded in the bot webhook URL path (and Telegram secret_token header).
    telegram_webhook_secret: Optional[str] = None
    # Tribute (card/Wallet payments). When set, the Mini App sends users to this
    # subscription link and access is granted via the Tribute webhook (signed
    # with tribute_api_key). Takes precedence over Stars.
    tribute_api_key: Optional[str] = None
    tribute_subscription_url: Optional[str] = None
    # Optional LLM-written expert commentary on the property detail (Claude API).
    # When anthropic_api_key is set, a unique paragraph is generated per property
    # and cached; otherwise the deterministic rule-based note is used.
    anthropic_api_key: Optional[str] = None
    expert_llm_model: str = "claude-haiku-4-5"  # cheap/fast; switch to opus/sonnet for richer prose
    expert_vision_images: int = 5  # how many listing photos to send to the model (0 = text only)
    expert_per_refresh: int = 40   # max expert generations per daily refresh (covers new listings)
    expert_min_score: int = 60     # only generate expert for listings scoring at least this
    # Public HTTPS base used to register the webhook, e.g. https://aicraftpin.com
    public_base_url: Optional[str] = None
    # Email / SMTP
    smtp_host: Optional[str] = None
    smtp_port: int = 587
    smtp_user: Optional[str] = None
    smtp_password: Optional[str] = None
    smtp_from: Optional[str] = None
    smtp_tls: bool = True
    alert_email_to: Optional[str] = None

    # --- Investment calculator (Portugal) ---
    stamp_duty_rate: float = 0.008          # Imposto do Selo on purchase
    notary_registration_eur: float = 1500.0  # notary + land registry estimate
    imi_rate: float = 0.003                  # annual IMI proxy (% of price)
    operating_cost_pct: float = 0.20         # of rent: vacancy/maintenance/mgmt/condo/insurance
    # Short-term rental (Alojamento Local) scenario, shown for AL-licensed listings.
    al_gross_multiplier: float = 1.9         # AL gross revenue vs long-term rent (typology-tilted)
    al_operating_cost_pct: float = 0.40      # higher opex: cleaning/management/utilities/fees/vacancy
    mortgage_ltv: float = 0.70               # loan-to-value
    mortgage_rate: float = 0.035             # annual interest rate
    mortgage_term_years: int = 30

    # --- Manual refresh button ---
    manual_refresh_min_interval_hours: float = 24.0  # no more than once per day
    manual_refresh_max_items: int = 200  # results per area for the manual refresh

    # --- Scheduler ---
    scheduler_enabled: bool = False
    scheduler_provider: str = "mock"  # "mock" | "apify"
    daily_import_hour: int = 6
    daily_import_minute: int = 0

    # --- Paths ---
    mock_data_path: str = "sample_data/properties_mock.json"
    raw_data_dir: str = "data/raw"

    # Auto-create tables on startup (MVP convenience). Use Alembic in production.
    auto_create_tables: bool = True


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
