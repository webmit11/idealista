"""FastAPI application: JSON API + HTML dashboard."""
import base64
import logging
import secrets
from collections import Counter
from contextlib import asynccontextmanager
from datetime import datetime
from math import ceil
from typing import Optional
from urllib.parse import urlencode

from fastapi import Depends, FastAPI, Form, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, select

from app.api import (
    routes_exports,
    routes_imports,
    routes_properties,
    routes_searches,
)
from app.core.config import settings
from app.core.logging import setup_logging
from app.db.database import engine, get_session, init_db
from app.db.models import PriceHistory, Property, Score
from app.jobs.scheduler import shutdown_scheduler, start_scheduler
from app.services.metro_stations import METRO_STATIONS
from app.services.query import VALID_SORTS, count_properties, query_properties, serialize
from app.services.explain import explain_score
from app.services.investment import compute_investment
from app.services.refresh_service import refresh_status, trigger_refresh
from app.services.telegram_auth import require_telegram_user
from app.services.watchlist import WATCH_COLORS, WATCH_LABELS, WATCH_STATUSES, normalize_status

logger = logging.getLogger("app")
templates = Jinja2Templates(directory="app/templates")

TYPOLOGY_OPTIONS = ["T0", "T1", "T2", "T3", "T4"]


def _opt_float(value: Optional[str]) -> Optional[float]:
    """Parse a query param to float; blank/invalid -> None (HTML forms send '')."""
    try:
        return float(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _opt_int(value: Optional[str], default: int) -> int:
    try:
        return int(float(value)) if value not in (None, "") else default
    except (TypeError, ValueError):
        return default


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    if settings.auto_create_tables:
        init_db()
    if settings.scheduler_enabled:
        start_scheduler()
    logger.info("application started", extra={"extra_fields": {"app": settings.app_name}})
    yield
    shutdown_scheduler()


app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.include_router(routes_properties.router)
app.include_router(routes_searches.router)
app.include_router(routes_exports.router)
app.include_router(routes_imports.router)


@app.middleware("http")
async def basic_auth(request: Request, call_next):
    """HTTP Basic auth for everything except /health (when a password is set)."""
    password = settings.dashboard_password
    path = request.url.path
    # /app* uses Telegram initData auth instead of Basic; /health is open.
    if password and path != "/health" and not path.startswith("/app"):
        header = request.headers.get("authorization", "")
        ok = False
        if header.startswith("Basic "):
            try:
                user, _, pw = base64.b64decode(header[6:]).decode("utf-8").partition(":")
                ok = secrets.compare_digest(user, settings.dashboard_user) and \
                    secrets.compare_digest(pw, password)
            except Exception:
                ok = False
        if not ok:
            return Response(
                status_code=401,
                headers={"WWW-Authenticate": 'Basic realm="Porto Investment Finder"'},
            )
    response = await call_next(request)
    # Listings change daily; never let the browser serve a stale dashboard page
    # (a stale page is what makes applied filters/checkboxes appear to reset).
    if "text/html" in response.headers.get("content-type", ""):
        response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/app", response_class=HTMLResponse)
def mini_app(request: Request):
    """Telegram Mini App shell (data is fetched via /app/api with initData auth)."""
    return templates.TemplateResponse(request, "miniapp.html", {"app_name": settings.app_name})


@app.get("/app/api/properties")
def mini_app_properties(
    session: Session = Depends(get_session),
    user: dict = Depends(require_telegram_user),
    sort: str = Query("score_desc"),
    limit: int = Query(50, ge=1, le=200),
    min_score: Optional[float] = Query(None),
    only_price_drops: bool = Query(False),
    only_new: bool = Query(False),
):
    results = query_properties(
        session,
        sort=sort if sort in VALID_SORTS else "score_desc",
        limit=limit, min_score=min_score,
        only_price_drops=only_price_drops, only_new=only_new,
    )
    return [serialize(p, s) for p, s in results]


@app.post("/refresh")
def refresh_now(session: Session = Depends(get_session)):
    result = trigger_refresh(session)
    return RedirectResponse(url=f"/?refresh={result['reason']}", status_code=303)


_REFRESH_MESSAGES = {
    "started": "🔄 Обновление запущено — займёт пару минут. Обновите страницу позже.",
    "too_soon": "⏳ Обновлять можно не чаще раза в день. Попробуйте позже.",
    "running": "🔄 Обновление уже выполняется.",
}


@app.get("/", response_class=HTMLResponse)
def dashboard(
    request: Request,
    session: Session = Depends(get_session),
    min_score: Optional[str] = Query(None),
    max_price: Optional[str] = Query(None),
    typology: Optional[str] = Query(None),
    municipality: Optional[str] = Query(None),
    max_distance_to_metro: Optional[str] = Query(None),
    min_gross_yield: Optional[str] = Query(None),
    only_price_drops: bool = Query(False),
    only_new: bool = Query(False),
    has_garage: bool = Query(False),
    has_elevator: bool = Query(False),
    has_terrace: bool = Query(False),
    south_facing: bool = Query(False),
    exclude_ground_floor: bool = Query(False),
    exclude_no_coordinates: bool = Query(False),
    exclude_bad_neighborhoods: bool = Query(False),
    only_exact_location: bool = Query(False),
    sort: str = Query("score_desc"),
    limit: Optional[str] = Query(None),
    page: Optional[str] = Query(None),
    refresh: Optional[str] = Query(None),
):
    # HTML forms submit empty strings for blank number inputs; coerce them.
    per_page = min(200, max(10, _opt_int(limit, 50)))
    sort_key = sort if sort in VALID_SORTS else "score_desc"
    # Empty "Min score" field -> default threshold (hide weak listings).
    # Type 0 to see everything.
    min_score_f = _opt_float(min_score)
    if min_score_f is None:
        min_score_f = settings.dashboard_min_score
    filter_kwargs = dict(
        min_score=min_score_f,
        max_price=_opt_float(max_price),
        typology=typology or None,
        municipality=municipality or None,
        max_distance_to_metro=_opt_float(max_distance_to_metro),
        min_gross_yield=_opt_float(min_gross_yield),
        only_price_drops=only_price_drops,
        only_new=only_new,
        has_garage=True if has_garage else None,
        has_elevator=True if has_elevator else None,
        has_terrace=True if has_terrace else None,
        south_facing=south_facing,
        exclude_ground_floor=exclude_ground_floor,
        exclude_no_coordinates=exclude_no_coordinates,
        exclude_bad_neighborhoods=exclude_bad_neighborhoods,
        only_exact_location=only_exact_location,
    )

    total = count_properties(session, **filter_kwargs)
    total_pages = max(1, ceil(total / per_page))
    page_num = min(max(1, _opt_int(page, 1)), total_pages)
    offset = (page_num - 1) * per_page

    results = query_properties(
        session, sort=sort_key, limit=per_page, offset=offset, **filter_kwargs
    )
    rows = [serialize(p, s) for p, s in results]
    municipalities = sorted(
        {
            m
            for m in session.exec(
                select(Property.municipality).where(Property.municipality != None)  # noqa: E711
            ).all()
            if m
        }
    )

    # Querystring for header/pagination links (everything except sort & page).
    qs_params: dict = {}
    for key in ("min_score", "max_price", "max_distance_to_metro", "min_gross_yield"):
        if filter_kwargs[key] is not None:
            qs_params[key] = filter_kwargs[key]
    if typology:
        qs_params["typology"] = typology
    if municipality:
        qs_params["municipality"] = municipality
    for key, val in (
        ("only_price_drops", only_price_drops), ("only_new", only_new),
        ("has_garage", has_garage), ("has_elevator", has_elevator),
        ("has_terrace", has_terrace), ("south_facing", south_facing),
        ("exclude_ground_floor", exclude_ground_floor),
        ("exclude_no_coordinates", exclude_no_coordinates),
        ("exclude_bad_neighborhoods", exclude_bad_neighborhoods),
        ("only_exact_location", only_exact_location),
    ):
        if val:
            qs_params[key] = "true"
    qs_params["limit"] = per_page
    qs = urlencode(qs_params)

    filters = {
        "min_score": filter_kwargs["min_score"],
        "max_price": filter_kwargs["max_price"],
        "typology": typology,
        "municipality": municipality,
        "max_distance_to_metro": filter_kwargs["max_distance_to_metro"],
        "min_gross_yield": filter_kwargs["min_gross_yield"],
        "only_price_drops": only_price_drops,
        "only_new": only_new,
        "has_garage": has_garage,
        "has_elevator": has_elevator,
        "has_terrace": has_terrace,
        "south_facing": south_facing,
        "exclude_ground_floor": exclude_ground_floor,
        "exclude_no_coordinates": exclude_no_coordinates,
        "exclude_bad_neighborhoods": exclude_bad_neighborhoods,
        "only_exact_location": only_exact_location,
        "sort": sort_key,
        "limit": per_page,
    }
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "rows": rows,
            "filters": filters,
            "municipalities": municipalities,
            "typologies": TYPOLOGY_OPTIONS,
            "app_name": settings.app_name,
            "count": len(rows),
            "total": total,
            "page": page_num,
            "total_pages": total_pages,
            "per_page": per_page,
            "qs": qs,
            "rstatus": refresh_status(session),
            "refresh_msg": _REFRESH_MESSAGES.get(refresh),
            "watch_labels": WATCH_LABELS,
            "watch_colors": WATCH_COLORS,
        },
    )


@app.get("/sold", response_class=HTMLResponse)
def sold_view(
    request: Request,
    session: Session = Depends(get_session),
    limit: Optional[str] = Query(None),
    page: Optional[str] = Query(None),
):
    per_page = min(200, max(10, _opt_int(limit, 50)))
    total = count_properties(session, only_delisted=True, active_only=False)
    total_pages = max(1, ceil(total / per_page))
    page_num = min(max(1, _opt_int(page, 1)), total_pages)
    offset = (page_num - 1) * per_page
    results = query_properties(
        session, only_delisted=True, active_only=False,
        sort="delisted_desc", limit=per_page, offset=offset,
    )
    rows = [serialize(p, s) for p, s in results]
    return templates.TemplateResponse(
        request,
        "sold.html",
        {
            "rows": rows,
            "app_name": settings.app_name,
            "total": total,
            "page": page_num,
            "total_pages": total_pages,
            "per_page": per_page,
        },
    )


@app.post("/property/{property_id}/watch")
def set_watch(
    property_id: int,
    status: str = Form(""),
    note: str = Form(""),
    session: Session = Depends(get_session),
):
    prop = session.get(Property, property_id)
    if not prop:
        raise HTTPException(status_code=404, detail="Property not found")
    prop.watch_status = normalize_status(status)
    prop.watch_note = (note or "").strip() or None
    prop.watch_updated_at = datetime.utcnow()
    session.add(prop)
    session.commit()
    return RedirectResponse(url=f"/property/{property_id}", status_code=303)


@app.get("/watchlist", response_class=HTMLResponse)
def watchlist_view(
    request: Request,
    session: Session = Depends(get_session),
    status: Optional[str] = Query(None),
):
    active = normalize_status(status)
    results = query_properties(
        session, watched_only=True, active_only=False, watch_status=active,
        sort="watch_desc", limit=1000,
    )
    rows = [serialize(p, s) for p, s in results]
    all_watched = query_properties(
        session, watched_only=True, active_only=False, sort="watch_desc", limit=1000
    )
    counts = Counter(p.watch_status for p, _ in all_watched)
    return templates.TemplateResponse(
        request,
        "watchlist.html",
        {
            "rows": rows,
            "app_name": settings.app_name,
            "statuses": WATCH_STATUSES,
            "labels": WATCH_LABELS,
            "colors": WATCH_COLORS,
            "counts": counts,
            "active_status": active,
            "total_watched": len(all_watched),
        },
    )


@app.get("/new", response_class=HTMLResponse)
def new_view(
    request: Request,
    session: Session = Depends(get_session),
    days: Optional[str] = Query(None),
    limit: Optional[str] = Query(None),
    page: Optional[str] = Query(None),
):
    days_i = min(90, max(1, _opt_int(days, settings.new_listing_days)))
    per_page = min(200, max(10, _opt_int(limit, 50)))
    total = count_properties(session, new_within_days=days_i)
    total_pages = max(1, ceil(total / per_page))
    page_num = min(max(1, _opt_int(page, 1)), total_pages)
    offset = (page_num - 1) * per_page
    results = query_properties(
        session, new_within_days=days_i, sort="newest", limit=per_page, offset=offset
    )
    rows = [serialize(p, s) for p, s in results]
    return templates.TemplateResponse(
        request,
        "new.html",
        {
            "rows": rows,
            "app_name": settings.app_name,
            "total": total,
            "page": page_num,
            "total_pages": total_pages,
            "per_page": per_page,
            "days": days_i,
        },
    )


@app.get("/map", response_class=HTMLResponse)
def map_view(request: Request, session: Session = Depends(get_session)):
    results = query_properties(
        session, sort="score_desc", limit=500, exclude_no_coordinates=True
    )
    listings = [
        {
            "id": p.id,
            "lat": p.latitude,
            "lng": p.longitude,
            "score": s.total_score if s else None,
            "title": p.title,
            "price": p.price,
            "typology": p.typology,
            "yield": p.gross_yield_percent,
            "metro": p.nearest_metro_station,
            "thumb": p.thumbnail_url,
            "url": p.url,
        }
        for p, s in results
    ]
    stations = [
        {"name": st.name, "lat": st.latitude, "lng": st.longitude} for st in METRO_STATIONS
    ]
    return templates.TemplateResponse(
        request,
        "map.html",
        {"listings": listings, "stations": stations, "app_name": settings.app_name},
    )


@app.get("/property/{property_id}", response_class=HTMLResponse)
def property_detail(
    property_id: int,
    request: Request,
    session: Session = Depends(get_session),
    ltv: Optional[str] = Query(None),
    rate: Optional[str] = Query(None),
    term: Optional[str] = Query(None),
):
    prop = session.get(Property, property_id)
    if not prop:
        raise HTTPException(status_code=404, detail="Property not found")
    score = session.get(Score, property_id)
    history = session.exec(
        select(PriceHistory)
        .where(PriceHistory.property_id == property_id)
        .order_by(PriceHistory.observed_at)
    ).all()
    data = serialize(prop, score)

    ltv_f, rate_f, term_i = _opt_float(ltv), _opt_float(rate), _opt_int(term, 0)
    invest = compute_investment(
        prop.price, prop.rental_estimate_mid, prop.typology,
        ltv=(ltv_f / 100) if ltv_f is not None else None,
        rate=(rate_f / 100) if rate_f is not None else None,
        term_years=term_i or None,
    )
    return templates.TemplateResponse(
        request,
        "property_detail.html",
        {
            "p": data,
            "explanation": score.explanation_json if score else None,
            "explain": explain_score(data, score.explanation_json if score else None),
            "invest": invest,
            "history": [{"price": h.price, "observed_at": h.observed_at} for h in history],
            "app_name": settings.app_name,
            "watch_statuses": WATCH_STATUSES,
            "watch_labels": WATCH_LABELS,
            "watch_colors": WATCH_COLORS,
        },
    )
