# Porto Investment Finder

MVP system to find investment-worthy apartments (T1/T2/T3) near **Metro do Porto**
stations across **Porto / Grande Porto** (Porto, Maia, Matosinhos, Gondomar / Rio
Tinto, etc.). It imports listings daily, stores them, computes investment metrics
and a 0–100 score, filters for "hits" near the metro, and shows the best
candidates in a dashboard with CSV/XLSX export.

> ⚠️ This is an MVP with rule-based heuristics, not financial or legal advice.
> Rent tables, acquisition costs, and benchmarks are rough approximations.

---

## Table of contents
1. [Architecture](#architecture)
2. [Run with Docker Compose](#1-run-with-docker-compose)
3. [Configure `.env`](#2-configure-env)
4. [Import mock data](#3-import-mock-data)
5. [Connect Apify](#4-connect-apify)
6. [Add new metro stations](#5-add-new-metro-stations)
7. [How scoring works](#6-how-scoring-works)
8. [MVP limitations](#7-mvp-limitations)
9. [Legal limitations on data](#8-legal-limitations-on-data)
10. [Google Sheets / official API later](#9-google-sheets--official-api-later)
11. [API reference](#api-reference)
12. [CLI](#cli)
13. [Tests](#tests)

---

## Architecture

```
app/
  api/         routes_properties.py, routes_searches.py, routes_exports.py, routes_imports.py
  core/        config.py (env settings), logging.py (JSON logs)
  db/          database.py (engine/session), models.py (SQLModel)
  services/
    providers/ base.py (DataProvider interface), mock_provider.py, apify_idealista.py
    scoring.py            # weighted 0-100 score + risk penalties
    metro_distance.py     # haversine, nearest station, metro_score
    metro_stations.py     # station reference data (coordinates)
    rental_estimator.py   # rule-based rent + gross yield
    price_benchmark.py    # local median €/m²
    deduplication.py      # (source, external_id) upsert key
    price_history.py      # price change tracking
    ingest.py             # fetch -> enrich -> upsert -> benchmark -> score
    query.py              # shared filtering/sorting/serialization
    export.py             # CSV / XLSX
  jobs/        daily_import.py (job entrypoint), scheduler.py (APScheduler)
  templates/   base.html, dashboard.html, property_detail.html
  main.py      # FastAPI app + HTML dashboard
  cli.py       # import-mock / import-apify / recalculate-scores / export-xlsx
sample_data/properties_mock.json
tests/         test_scoring.py, test_metro_distance.py, test_rental_estimator.py
migrations/    Alembic migrations (applied on container start; create_all is a fallback)
deploy/nginx/  idealista.conf (reverse proxy: idealista.localhost -> app:8000)
docker-compose.yml, Dockerfile, .env.example
```

**Data sources are abstracted behind `DataProvider`** (`app/services/providers/base.py`).
Every provider returns `NormalizedListing` objects, so adding the official
Idealista API, CASAFARI, or any other source means writing one new provider
class — nothing downstream changes.

**Tech choices (vs the brief, with rationale):**
- ORM: **SQLModel** (SQLAlchemy + Pydantic) — less boilerplate for an MVP.
- Frontend: **FastAPI + Jinja2 templates** — fastest path, no separate Node build.
- Logging: stdlib **JSON logging** (no extra dependency).
- HTTP: **httpx** (used by both the Apify client and the test client).
- Migrations: **Alembic** is the source of truth — the container entrypoint runs
  `alembic upgrade head` on start (`deploy/entrypoint.sh`); `create_all` remains a
  dev fallback. Change schema with `alembic revision --autogenerate -m "..."`.
- Auth: optional **HTTP Basic** — set `DASHBOARD_PASSWORD` to require login for
  everything except `/health`. Empty = open.
- The `Property` model adds derived/cached fields
  (`rental_estimate_low/mid/high`, `gross_yield_percent`) so the dashboard can
  filter and sort on yield in SQL.

---

## 1. Run with Docker Compose

```bash
cp .env.example .env          # optional but recommended (Apify token, overrides)
docker compose up --build
```

> `.env` is optional — Compose runs with built-in defaults (mock provider, local
> Postgres). Create one to set `APIFY_TOKEN` or override any setting.

This starts:
- **db** — PostgreSQL 16
- **app** — FastAPI (internal, not published directly)
- **proxy** — nginx, serving the app on port 80 by host name

Then open (no port needed — the nginx proxy routes by host name):
- Dashboard: **http://idealista.localhost/**
- API docs (Swagger): http://idealista.localhost/docs
- Health: http://idealista.localhost/health

> Browsers (and macOS) resolve `*.localhost` to 127.0.0.1 automatically. If your
> setup doesn't, add `127.0.0.1 idealista.localhost` to `/etc/hosts`.

**Port conflicts:** if port 80 (or 5432) is busy, override the published ports:
```bash
PROXY_PORT=8080 HOST_DB_PORT=5440 docker compose up --build
# then open http://idealista.localhost:8080/
```
(or set `PROXY_PORT` / `HOST_DB_PORT` in `.env`). The app always listens on 8000
inside its container; only the host-facing ports change.

Tables are created automatically on startup. To load demo data, run the mock
import (next sections) — e.g.:

```bash
docker compose exec app python -m app.jobs.daily_import --provider mock
```

Refresh the dashboard and you'll see the scored listings.

### Run locally without Docker (SQLite)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
export DATABASE_URL="sqlite:///./dev.db"
python -m app.jobs.daily_import --provider mock
uvicorn app.main:app --reload
```

---

## 2. Configure `.env`

Copy `.env.example` to `.env` and adjust. Key variables:

| Variable | Meaning |
|---|---|
| `DATABASE_URL` | SQLAlchemy URL. Docker default points at the `db` service. Use `sqlite:///./dev.db` for local runs. |
| `APIFY_TOKEN` | Your Apify API token (required for the Apify provider). |
| `APIFY_ACTOR_ID` | Actor id in URL form, e.g. `username~idealista-scraper`. |
| `APIFY_SEARCH_URLS` | Comma-separated Idealista search URLs used when none are passed. |
| `WALKING_SPEED_M_PER_MIN` | Walking speed for the time estimate (default 80 m/min). |
| `BENCHMARK_MIN_SAMPLES` | Min listings in a bucket before its median €/m² is trusted. |
| `NEW_LISTING_DAYS` | A listing counts as "new" within this many days. |
| `SCHEDULER_ENABLED` | If `true`, run a daily import via APScheduler. |
| `SCHEDULER_PROVIDER` | `mock` or `apify` for the scheduled job. |
| `DAILY_IMPORT_HOUR` / `MINUTE` | When the daily job runs (UTC). |
| `AUTO_CREATE_TABLES` | `create_all` fallback on startup (Alembic is primary). |
| `DASHBOARD_USER` / `DASHBOARD_PASSWORD` | HTTP Basic auth. Set a password to require login; empty = open. |

---

## 3. Import mock data

A sample dataset lives at `sample_data/properties_mock.json` (~15 listings across
Porto, Rio Tinto, Maia, Senhora da Hora, Matosinhos).

```bash
# job entrypoint (as in the brief)
python -m app.jobs.daily_import --provider mock

# or the CLI
python -m app.cli import-mock
python -m app.cli import-mock --file path/to/other.json

# or the HTTP API
curl -X POST http://idealista.localhost/import/mock
```

The importer enriches each listing (nearest metro, €/m², rent, yield), upserts
by `(source, external_id)`, tracks price changes, then recomputes benchmarks and
scores.

---

## 4. Connect Apify

1. Create an Apify account and pick an Idealista scraper actor.
2. Set in `.env`:
   ```
   APIFY_TOKEN=apify_api_xxx
   APIFY_ACTOR_ID=oJTRDX4iyfR3erNnv          # dz_omar~idealista-scraper-api
   APIFY_SEARCH_URLS=https://www.idealista.pt/comprar-casas/porto/com-preco-max_300000,t1,t2,t3/
   ```
   > **URLs are separated by SPACES/newlines, not commas** — Idealista URLs
   > contain commas in their filter segment.
3. Run it:
   ```bash
   python -m app.jobs.daily_import --provider apify --url "https://www.idealista.pt/comprar-casas/porto/..."
   # or
   python -m app.cli import-apify --url "https://www.idealista.pt/..."
   # or HTTP
   curl -X POST http://idealista.localhost/import/apify \
        -H 'content-type: application/json' \
        -d '{"urls":["https://www.idealista.pt/..."]}'
   ```

The provider starts an actor run, **polls until it finishes**, then downloads the
dataset (so large scrapes and the daily scheduler aren't limited by the 300 s
sync cap). It stores the **raw JSON response** under `data/raw/` for debugging
and normalizes records, including Idealista's geography quirk (for Porto-city
listings the API's `municipality` is actually a *freguesia*, so the real concelho
is inferred — see `_geo()`).

> **Field mapping caveat:** the mapping in
> `app/services/providers/apify_idealista.py` (`_build_input` / `_normalize`) is
> tuned for actor **dz_omar~idealista-scraper-api**. A different actor has a
> different input/output schema — adjust those two methods accordingly.

---

## 5. Add new metro stations

Edit `app/services/metro_stations.py` and add a tuple to `_STATIONS`:

```python
("Station Name", latitude, longitude, ("Line",), "Municipality"),
```

Distances are recomputed on the next import (or run
`python -m app.cli recalculate-scores`).

> Coordinates in the MVP are **hand-curated approximations** (good enough for the
> 500/800/1000/1200/1500 m proximity buckets). For production, replace them with
> the official Metro do Porto GTFS feed or OpenStreetMap data.

---

## 6. How scoring works

Each property gets component scores (0–100) combined with weights; risk flags
then subtract penalty points. Final score is clamped to **0–100**.

| Component | Weight | Logic |
|---|---|---|
| Price vs local median €/m² | 25% | ≥20% cheaper → 100, 10–20% → 85, 0–10% → 65, 0–10% over → 45, 10–20% over → 25, >20% over → 10 |
| Metro proximity | 20% | ≤500 m → 100, ≤800 → 85, ≤1000 → 70, ≤1200 → 55, ≤1500 → 35, else 0 |
| Typology liquidity | 15% | T2 → 100, T1 → 85, T3 → 80, T0 → 55, T4+ → 50 |
| Rental yield | 15% | ≥7% → 100, ≥6 → 85, ≥5 → 70, ≥4 → 50, ≥3 → 30, else 10 |
| Condition | 10% | new → 100, renovated → 90, good → 70, to_renovate → 35, unknown → 50 |
| Elevator / garage | 7% | both → 100, elevator → 75, garage → 65, neither → 35 |
| Price drop / negotiation | 5% | drop ≥10% → 100, ≥7 → 85, ≥5 → 70, ≥3 → 55, >0 → 35, none → 20 |
| **Risk penalty** | −0…−20 | sum of risk-flag penalties, capped at 20 |

> The positive weights sum to **97** (per the brief), so the practical maximum is
> 97 before any penalty. The total is clamped to `[0, 100]`.

**Benchmark (€/m²):** local median computed per `parish + typology`, falling back
to `municipality + typology`, then `district + typology`, then the overall median.
A bucket must have at least `BENCHMARK_MIN_SAMPLES` listings to be used.

**Rental & yield:** rule-based rent table by zone (see `rental_estimator.py`).
`gross_yield = rent_mid × 12 / total_acquisition_cost`, where
`total_acquisition_cost = price + price×6% + furnishing` (furnishing: T0/T1 €6k,
T2 €9k, T3+ €12k).

**Risk flags:** missing coordinates / area, ground floor, no elevator on floor ≥3,
suspiciously low €/m², and red-flag keywords in the description
(`arrendado`, `ocupado`, `usufruto`, `sem licença`, `para remodelar`, …).

Every score stores an `explanation_json` with the full breakdown — visible on the
property detail page (`/property/{id}`).

---

## 7. MVP limitations

- **Distances are straight-line (haversine), not pedestrian routing.** Walking
  time = distance ÷ 80 m/min. Swap in Google Maps / OpenRouteService later by
  replacing the helpers in `metro_distance.py`.
- **Metro coordinates are approximate** (see §5).
- **Rent table & acquisition costs are rough heuristics**, not market data.
- **Two risk inputs from the brief are not implemented** — "very high condominium
  fee" and "old building (build year)" — because those fields are not in the MVP
  data model. Add columns + provider mapping to enable them.
- **De-duplication is by `(source, external_id)`** only; cross-source dedupe is
  scaffolded (`deduplication.find_possible_duplicate`) but off by default.
- **Benchmarks need enough data** to be meaningful — with a tiny dataset most
  buckets fall back to the overall median.

---

## 8. Legal limitations on data

- **Do not scrape Idealista directly in violation of their Terms of Service.**
  This project deliberately abstracts the data source behind `DataProvider` and
  does not ship a direct Idealista scraper. The Apify path delegates to a
  third-party actor — you are responsible for using it within Idealista's ToS and
  applicable law (e.g. GDPR for any personal data in listings).
- Prefer **official/licensed sources** (Idealista API, CASAFARI) for production.
- Stored raw responses (`data/raw/`) may contain third-party content — treat them
  accordingly and don't redistribute.

---

## 9. Google Sheets / official API later

- **Google Sheets export:** add `app/services/google_sheets.py` using `gspread` +
  a service account, reusing the row builder in `export.py` (`_rows`/`serialize`).
  Wire it into a new CLI command and/or endpoint. (Not enabled by default to keep
  the MVP dependency-free of Google credentials.)
- **Official Idealista API / CASAFARI:** implement a new `DataProvider` subclass
  returning `NormalizedListing`, register it in `ingest`/CLI/routes, and switch
  `SCHEDULER_PROVIDER`. No changes needed in scoring, storage, or the dashboard.

---

## API reference

| Method | Path | Description |
|---|---|---|
| GET | `/properties` | List with filters & sorting (see query params below) |
| GET | `/properties/{id}` | Single property + price history + score explanation |
| GET | `/properties/top` | Highest scored |
| GET | `/properties/new` | Listings first seen within `NEW_LISTING_DAYS` |
| GET | `/properties/price-drops` | Listings with a price drop, biggest first |
| GET | `/search-profiles` | List saved search profiles |
| POST | `/search-profiles` | Create a search profile |
| POST | `/import/mock` | Run a mock import (optional `{"path": ...}`) |
| POST | `/import/apify` | Run an Apify import (optional `{"urls": [...]}`) |
| GET | `/exports/properties.csv` | CSV export |
| GET | `/exports/properties.xlsx` | XLSX export |
| GET | `/` | HTML dashboard (with photo thumbnails) |
| GET | `/map` | HTML map of listings + metro stations (Leaflet + OpenStreetMap) |
| GET | `/property/{id}` | HTML detail page (with photo gallery) |

**`GET /properties` filters:** `min_score`, `max_price`, `typology`,
`municipality`, `max_distance_to_metro`, `min_gross_yield`, `only_price_drops`,
`only_new`, `has_garage`, `has_elevator`, `exclude_ground_floor`,
`exclude_no_coordinates`, plus `sort` and `limit`/`offset`.

**`sort` values:** `score_desc` (default), `price_asc`, `ppm2_asc`,
`yield_desc`, `newest`, `biggest_drop`.

---

## CLI

```bash
python -m app.cli import-mock [--file PATH]
python -m app.cli import-apify [--url URL ...] [--max-items N] [--deactivate-missing]
python -m app.cli refresh [--max-items N]   # full Grande Porto refresh (all areas) + deactivate missing
python -m app.cli recalculate-scores
python -m app.cli export-xlsx [--output PATH]
python -m app.cli test-alert                # send a test notification
```

## Alerts (new hits + price drops)

After each import the system can push a digest of **new listings scoring ≥
`ALERT_MIN_SCORE`** and **listings whose price dropped ≥ `ALERT_MIN_PRICE_DROP`%**
that run (no re-alerting across runs). Channels: **Telegram** or **email**.

Enable in `.env`:
```
ALERTS_ENABLED=true
ALERT_CHANNEL=auto            # auto | telegram | email
# Telegram:
TELEGRAM_BOT_TOKEN=123:ABC    # from @BotFather
TELEGRAM_CHAT_ID=123456789    # your chat id
# or email:
SMTP_HOST=smtp.gmail.com
SMTP_USER=you@gmail.com
SMTP_PASSWORD=app-password
ALERT_EMAIL_TO=you@gmail.com
```
Then `docker compose up -d app` and verify with
`docker compose exec app python -m app.cli test-alert`. Alerts fire on the daily
scheduled refresh and any import.

**Coverage / areas.** `refresh` scrapes every area in
`app/services/search_areas.py` (Porto, Maia, Matosinhos, Gondomar — Matosinhos
covers Senhora da Hora, Gondomar covers Rio Tinto), tagging each listing with the
correct concelho, then deactivates any active listing not seen in the run. Add
areas or raise the price cap by editing that file. The daily scheduler runs the
same multi-area refresh.

---

## Tests

```bash
pip install -r requirements-dev.txt
pytest
```

Covers the core logic: `scoring.py`, `metro_distance.py`, `rental_estimator.py`.
