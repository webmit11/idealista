"""FastAPI application: JSON API + HTML dashboard."""
import base64
import hashlib
import hmac
import json
import logging
import secrets
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from math import ceil
from typing import Optional
from urllib.parse import urlencode

from fastapi import Depends, FastAPI, Form, HTTPException, Query, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
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
from app.db.models import Lead, PriceHistory, Property, Score
from app.jobs.scheduler import shutdown_scheduler, start_scheduler
from app.services.metro_stations import METRO_STATIONS
from app.services.query import VALID_SORTS, count_properties, query_properties, serialize
from app.services.explain import explain_score
from app.services.expert_note import expert_note
from app.services.al_license import detect_al_license
from app.services.expert_llm import expert_facts, expert_worth_generating, generate_expert
from app.services.investment import compute_investment
from app.services.scoring import compute_score
from app.services.refresh_service import refresh_status, trigger_refresh
from app.services.telegram_auth import require_owner, require_subscriber, require_telegram_user
from app.services import area_scoring, geoip, property_chat, saved_filters, subscriptions, telegram_api, thumbs, user_watchlist
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


def _web_owner() -> int:
    """The owner's Telegram id — the single funnel shared by web + Mini App."""
    return settings.telegram_owner_id or 0


def _overlay_owner_watch(session, rows: list) -> None:
    """Overlay the owner's personal funnel (user_watches) onto web-serialized rows."""
    wmap = user_watchlist.get_map(session, _web_owner(), [r["id"] for r in rows])
    for r in rows:
        w = wmap.get(r["id"])
        r["watch_status"] = w.status if w else None
        r["watch_note"] = w.note if w else None


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    if settings.auto_create_tables:
        init_db()
    try:
        from app.services.refresh_service import cleanup_stale_runs

        cleanup_stale_runs()
    except Exception:
        logger.exception("stale-run cleanup failed")
    try:
        geoip.ensure_db()
    except Exception:
        logger.exception("geoip db init failed")
    if settings.scheduler_enabled:
        start_scheduler()
    if settings.telegram_webhook_secret and settings.public_base_url and settings.telegram_bot_token:
        url = f"{settings.public_base_url.rstrip('/')}/bot/webhook/{settings.telegram_webhook_secret}"
        ok = telegram_api.set_webhook(url, settings.telegram_webhook_secret)
        logger.info("telegram webhook", extra={"extra_fields": {"set": ok}})
    logger.info("application started", extra={"extra_fields": {"app": settings.app_name}})
    yield
    shutdown_scheduler()


app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.mount("/static", StaticFiles(directory="app/static"), name="static")
app.include_router(routes_properties.router)
app.include_router(routes_searches.router)
app.include_router(routes_exports.router)
app.include_router(routes_imports.router)


@app.middleware("http")
async def basic_auth(request: Request, call_next):
    """HTTP Basic auth for everything except /health (when a password is set)."""
    password = settings.dashboard_password
    path = request.url.path
    # /app* (initData), /bot* and /tribute* (payment webhooks), /health are open.
    if (password and path != "/health" and not path.startswith("/app")
            and not path.startswith("/bot") and not path.startswith("/tribute")
            and not path.startswith("/img")
            and not path.startswith("/static")):
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


@app.get("/img/{property_id}")
def listing_image(property_id: int, session: Session = Depends(get_session)):
    """Serve a listing thumbnail from our cache (Idealista URLs expire in ~24h).

    Cache-miss: download on the fly while the signed URL is still valid; if that
    fails too (e.g. already expired), fall back to a neutral placeholder.
    """
    if not thumbs.is_cached(property_id):
        prop = session.get(Property, property_id)
        if prop and prop.thumbnail_url:
            thumbs.download(property_id, prop.thumbnail_url)
    if thumbs.is_cached(property_id):
        return FileResponse(
            thumbs.path_for(property_id),
            media_type="image/jpeg",
            headers={"Cache-Control": "public, max-age=604800"},
        )
    return RedirectResponse(url="/static/logo.png", status_code=302)


@app.get("/app", response_class=HTMLResponse)
def mini_app(request: Request):
    """Telegram Mini App shell (data is fetched via /app/api with initData auth)."""
    return templates.TemplateResponse(request, "miniapp.html", {"app_name": settings.app_name})


@app.get("/app/api/meta")
def mini_app_meta(
    session: Session = Depends(get_session),
    user: dict = Depends(require_subscriber),
):
    municipalities = sorted(
        {m for m in session.exec(select(Property.municipality).where(Property.municipality != None)).all() if m}  # noqa: E711
    )
    typologies = sorted(
        {t for t in session.exec(select(Property.typology).where(Property.typology != None)).all() if t}  # noqa: E711
    )
    return {
        "municipalities": municipalities,
        "typologies": typologies,
        "watch_statuses": [{"value": v, "label": l, "color": c} for v, l, c in WATCH_STATUSES],
        "new_count": count_properties(
            session, only_new=True, only_developments=False,
            min_score=settings.new_listing_min_score,
        ),
    }


@app.get("/app/api/properties")
def mini_app_properties(
    session: Session = Depends(get_session),
    user: dict = Depends(require_subscriber),
    sort: str = Query("score_desc"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    min_score: Optional[float] = Query(None),
    max_price: Optional[float] = Query(None),
    typology: Optional[str] = Query(None),
    municipality: Optional[str] = Query(None),
    parish: Optional[str] = Query(None),
    max_distance_to_metro: Optional[float] = Query(None),
    min_gross_yield: Optional[float] = Query(None),
    only_price_drops: bool = Query(False),
    only_new: bool = Query(False),
    has_garage: bool = Query(False),
    has_elevator: bool = Query(False),
    has_terrace: bool = Query(False),
    has_al_license: bool = Query(False),
    south_facing: bool = Query(False),
    exclude_ground_floor: bool = Query(False),
    exclude_no_coordinates: bool = Query(False),
    exclude_bad_neighborhoods: bool = Query(False),
    only_exact_location: bool = Query(False),
    only_developments: bool = Query(False),
    expert_positive: bool = Query(False),
    watched_only: bool = Query(False),
    watch_status: Optional[str] = Query(None),
    with_stats: bool = Query(False),
):
    if only_developments:
        dev = True
    elif watched_only:
        dev = None  # watchlist may contain developments too
    else:
        dev = False  # main tabs hide new developments (their own tab shows them)
    filters = dict(
        min_score=min_score, max_price=max_price, typology=typology or None,
        municipality=municipality or None, parish=parish or None, max_distance_to_metro=max_distance_to_metro,
        min_gross_yield=min_gross_yield, only_price_drops=only_price_drops, only_new=only_new,
        has_garage=True if has_garage else None, has_elevator=True if has_elevator else None,
        has_terrace=True if has_terrace else None, south_facing=south_facing,
        has_al_license=True if has_al_license else None,
        exclude_ground_floor=exclude_ground_floor, exclude_no_coordinates=exclude_no_coordinates,
        exclude_bad_neighborhoods=exclude_bad_neighborhoods, only_exact_location=only_exact_location,
        expert_positive=expert_positive,
        only_developments=dev, watched_only=watched_only,
        watch_status=normalize_status(watch_status) if watch_status else None,
        active_only=not watched_only,
    )
    sort_key = sort if sort in VALID_SORTS else "score_desc"
    total = count_properties(session, **filters)
    rows = [
        serialize(p, s)
        for p, s in query_properties(session, sort=sort_key, limit=limit, offset=offset, **filters)
    ]
    wmap = user_watchlist.get_map(session, int(user["id"]), [r["id"] for r in rows])
    for r in rows:
        w = wmap.get(r["id"])
        r["watch_status"] = w.status if w else None
        r["watch_note"] = w.note if w else None
    out: dict = {"rows": rows, "total": total}
    if with_stats:
        all_rows = [serialize(p, s) for p, s in query_properties(session, limit=3000, **filters)]
        out["stats"] = _developments_stats(all_rows)
    return out


_CONSULTANTS = ["Мария", "Анна", "София", "Елена", "Ольга", "Наталья", "Ирина", "Екатерина"]


def _consultant_for(tid) -> str:
    """Stable female consultant name per user."""
    return _CONSULTANTS[int(tid) % len(_CONSULTANTS)]


def _enrich_with_expert(session: Session, prop: Property, score: Optional[Score], data: dict) -> None:
    """Median €/m² deviation + cached LLM expert commentary (generated once).

    Shared by the Mini App JSON detail and the web HTML detail so the two stay in
    sync. Mutates `data` (median_ppm2 / ppm2_diff_pct / refreshed total_score) and,
    on first view, sets prop.expert_text / prop.expert_delta and re-scores.
    """
    expl = (score.explanation_json or {}) if score else {}
    med = expl.get("median_price_per_m2_benchmark")
    ppm2 = data.get("price_per_m2")
    data["median_ppm2"] = med
    data["ppm2_diff_pct"] = round((ppm2 / med - 1) * 100, 1) if (ppm2 and med) else None
    if (prop.expert_text is None and settings.anthropic_api_key
            and expert_worth_generating(prop, data.get("total_score"))):
        txt, delta = generate_expert(expert_facts(prop, expl), data.get("image_urls"))
        if txt:
            prop.expert_text = txt
            prop.expert_delta = delta
            session.add(prop)
            if score:  # re-score so the badge reflects the photo adjustment
                result = compute_score(prop, med)
                score.total_score = result.total_score
                score.explanation_json = result.explanation
                score.calculated_at = datetime.utcnow()
                session.add(score)
                data["total_score"] = result.total_score
            session.commit()


@app.get("/app/api/property/{property_id}")
def mini_app_property(
    property_id: int,
    session: Session = Depends(get_session),
    user: dict = Depends(require_subscriber),
):
    prop = session.get(Property, property_id)
    if not prop:
        raise HTTPException(status_code=404, detail="Property not found")
    score = session.get(Score, property_id)
    data = serialize(prop, score)
    w = user_watchlist.get_map(session, int(user["id"]), [prop.id]).get(prop.id)
    data["watch_status"] = w.status if w else None
    data["watch_note"] = w.note if w else None
    if prop.previous_price:
        last_change = session.exec(
            select(PriceHistory.observed_at)
            .where(PriceHistory.property_id == prop.id)
            .order_by(PriceHistory.observed_at.desc())
        ).first()
        iso = last_change.isoformat() if last_change else None
        data["price_changed_at"] = iso
        if prop.price_drop_percent and prop.price_drop_percent > 0:
            data["price_dropped_at"] = iso
    _enrich_with_expert(session, prop, score, data)
    return {
        "property": data,
        "explain": explain_score(data, score.explanation_json if score else None),
        "expert": expert_note(data, score.explanation_json if score else None),
        "expert_text": prop.expert_text,
        "expert_delta": prop.expert_delta,
        "invest": compute_investment(prop.price, prop.rental_estimate_mid, prop.typology),
        "watch_statuses": [{"value": v, "label": l, "color": c} for v, l, c in WATCH_STATUSES],
    }


@app.post("/app/api/property/{property_id}/watch")
def mini_app_set_watch(
    property_id: int,
    status: str = Query(""),
    note: str = Query(""),
    session: Session = Depends(get_session),
    user: dict = Depends(require_subscriber),
):
    if not session.get(Property, property_id):
        raise HTTPException(status_code=404, detail="Property not found")
    w = user_watchlist.set_watch(session, int(user["id"]), property_id, status, note)
    return {"ok": True, "watch_status": w.status if w else None, "watch_note": w.note if w else None}


def _set_al_override(session: Session, prop: Property, value: str) -> None:
    """Apply an owner AL override (not_al / al / auto), recompute the flag, drop the
    cached AL-framed expert commentary so it regenerates, and re-score."""
    if value == "auto":
        prop.al_override = None
        prop.has_al_license = detect_al_license(prop.description, prop.title)
    elif value == "al":
        prop.al_override = True
        prop.has_al_license = True
    else:  # not_al
        prop.al_override = False
        prop.has_al_license = False
    prop.expert_text = None
    prop.expert_delta = None
    session.add(prop)
    score = session.get(Score, prop.id)
    if score:
        med = (score.explanation_json or {}).get("median_price_per_m2_benchmark")
        result = compute_score(prop, med)
        score.total_score = result.total_score
        score.explanation_json = result.explanation
        score.calculated_at = datetime.utcnow()
        session.add(score)
    session.commit()


@app.post("/app/api/property/{property_id}/chat")
async def mini_app_property_chat(
    property_id: int,
    request: Request,
    session: Session = Depends(get_session),
    user: dict = Depends(require_subscriber),
):
    prop = session.get(Property, property_id)
    if not prop:
        raise HTTPException(status_code=404, detail="Property not found")
    try:
        body = await request.json()
    except Exception:
        body = {}
    score = session.get(Score, property_id)
    expl = (score.explanation_json or {}) if score else {}
    context = expert_facts(prop, expl)
    if prop.expert_text:
        context += "\n\nЭкспертная оценка: " + prop.expert_text
    ans = property_chat.answer(context, body.get("messages") or [], consultant=_consultant_for(user["id"]))
    if not ans:
        raise HTTPException(status_code=503, detail="Чат временно недоступен")
    return ans


@app.post("/app/api/property/{property_id}/al_override")
def mini_app_al_override(
    property_id: int,
    value: str = Query("not_al"),
    session: Session = Depends(get_session),
    user: dict = Depends(require_owner),
):
    prop = session.get(Property, property_id)
    if not prop:
        raise HTTPException(status_code=404, detail="Property not found")
    _set_al_override(session, prop, value)
    return {"ok": True, "has_al_license": prop.has_al_license, "al_override": prop.al_override}


@app.get("/app/api/watchlist")
def mini_app_watchlist(
    session: Session = Depends(get_session),
    user: dict = Depends(require_subscriber),
    status: Optional[str] = Query(None),
):
    """The current user's own deal pipeline."""
    uid = int(user["id"])
    active = normalize_status(status) if status else None
    rows = []
    for prop, score, w in user_watchlist.list_watched(session, uid, active):
        d = serialize(prop, score)
        d["watch_status"], d["watch_note"] = w.status, w.note
        rows.append(d)
    return {
        "rows": rows,
        "total": len(rows),
        "counts": user_watchlist.counts(session, uid),
        "watch_statuses": [{"value": v, "label": l, "color": c} for v, l, c in WATCH_STATUSES],
    }


@app.get("/app/api/areas")
def mini_app_areas(
    session: Session = Depends(get_session),
    user: dict = Depends(require_subscriber),
):
    return {"rows": area_scoring.compute_area_scores(session)}


@app.get("/app/api/filters")
def mini_app_filters_list(
    session: Session = Depends(get_session),
    user: dict = Depends(require_subscriber),
):
    rows = saved_filters.list_for(session, int(user["id"]))
    return {
        "rows": [
            {"id": s.id, "name": s.name, "criteria": s.criteria_json, "active": s.active}
            for s in rows
        ],
        "max": saved_filters.MAX_PER_USER,
    }


@app.post("/app/api/filters")
async def mini_app_filters_create(
    request: Request,
    session: Session = Depends(get_session),
    user: dict = Depends(require_subscriber),
):
    try:
        body = await request.json()
    except Exception:
        body = {}
    sf = saved_filters.create(session, int(user["id"]), body.get("name"), body.get("criteria") or {})
    if not sf:
        raise HTTPException(status_code=400, detail="Достигнут лимит сохранённых поисков")
    return {"id": sf.id, "name": sf.name, "criteria": sf.criteria_json, "active": sf.active}


@app.delete("/app/api/filters/{filter_id}")
def mini_app_filters_delete(
    filter_id: int,
    session: Session = Depends(get_session),
    user: dict = Depends(require_subscriber),
):
    return {"ok": saved_filters.delete(session, int(user["id"]), filter_id)}


@app.post("/app/api/filters/{filter_id}/toggle")
def mini_app_filters_toggle(
    filter_id: int,
    active: bool = Query(True),
    session: Session = Depends(get_session),
    user: dict = Depends(require_subscriber),
):
    return {"ok": saved_filters.set_active(session, int(user["id"]), filter_id, active)}


@app.get("/app/api/me")
def mini_app_me(
    request: Request,
    session: Session = Depends(get_session),
    user: dict = Depends(require_telegram_user),
):
    uid = int(user["id"])
    subscriptions.start_trial_if_new(session, uid, user)
    st = subscriptions.status(session, uid)
    st["price_stars"] = settings.subscription_price_stars
    st["period_days"] = settings.subscription_period_days
    st["subscribe_url"] = settings.tribute_subscription_url  # Tribute link; null -> use Stars
    st["consultant"] = _consultant_for(uid)
    st["contact_given"] = session.exec(select(Lead.id).where(Lead.telegram_id == uid)).first() is not None
    st["dial_code"] = geoip.dial_code_for_ip(geoip.client_ip(request))  # phone prefix from IP
    return st


@app.post("/app/api/lead")
async def mini_app_lead(
    request: Request,
    session: Session = Depends(get_session),
    user: dict = Depends(require_telegram_user),
):
    try:
        body = await request.json()
    except Exception:
        body = {}
    uid = int(user["id"])
    phone = str(body.get("phone") or "").strip()[:40]
    name = str(body.get("name") or "").strip()[:80] or user.get("first_name")
    pid = body.get("property_id")
    pid = int(pid) if isinstance(pid, int) or (isinstance(pid, str) and pid.isdigit()) else None
    country = geoip.country_for_ip(geoip.client_ip(request))
    lead = session.exec(select(Lead).where(Lead.telegram_id == uid)).first()
    if lead:
        if phone:
            lead.phone = phone
        if name:
            lead.name = name
        if pid:
            lead.property_id = pid
        if country:
            lead.country = country
    else:
        lead = Lead(telegram_id=uid, name=name, phone=phone or None, country=country, property_id=pid)
    session.add(lead)
    session.commit()
    return {"ok": True}


@app.post("/app/api/subscribe")
def mini_app_subscribe(
    user: dict = Depends(require_telegram_user),
):
    """Create a Telegram Stars subscription invoice link for the current user."""
    link = telegram_api.create_stars_subscription_link(payload=f"sub:{user['id']}")
    if not link:
        raise HTTPException(status_code=503, detail="Payments not available")
    return {"link": link}


@app.post("/bot/webhook/{secret}")
async def telegram_webhook(secret: str, request: Request):
    """Telegram webhook: handle Stars pre-checkout and successful payments."""
    if not settings.telegram_webhook_secret or secret != settings.telegram_webhook_secret:
        raise HTTPException(status_code=404, detail="Not found")
    if request.headers.get("X-Telegram-Bot-Api-Secret-Token") != settings.telegram_webhook_secret:
        raise HTTPException(status_code=403, detail="Bad secret token")
    update = await request.json()

    # Must approve the pre-checkout within 10s, else the payment fails.
    if "pre_checkout_query" in update:
        telegram_api.answer_pre_checkout(update["pre_checkout_query"]["id"], ok=True)
        return {"ok": True}

    msg = update.get("message") or {}
    sp = msg.get("successful_payment")
    if sp and sp.get("currency") == "XTR":
        frm = msg.get("from") or {}
        tid = int(frm.get("id"))
        until = None
        exp = sp.get("subscription_expiration_date")
        if exp:
            until = datetime.utcfromtimestamp(int(exp))
        with Session(engine) as s:
            subscriptions.activate(
                s, tid, until=until,
                charge_id=sp.get("telegram_payment_charge_id"),
                is_recurring=bool(sp.get("is_recurring") or sp.get("subscription_expiration_date")),
                user=frm,
            )
        telegram_api.send_message(tid, "✅ Подписка активна. Открой приложение из меню бота.")
        return {"ok": True}

    # /start — greet and open the Mini App via a web_app button.
    if msg.get("text", "").startswith("/start"):
        frm = msg.get("from") or {}
        chat_id = int(frm.get("id", 0))
        name = frm.get("first_name") or ""
        url = f"{(settings.public_base_url or '').rstrip('/')}/app"
        telegram_api.send_message(
            chat_id,
            (f"👋 Привет, {name}! " if name else "👋 ")
            + "Это <b>Domus</b> — недвижимость в Порту для жизни и дохода.\n\n"
            "Подбираю квартиры у метро Порту — и под себя, и под доход: балл, разбор по фото, "
            "расчёт аренды (в т.ч. краткосрочной AL), ROI-симулятор и алерты по сделкам.\n\nЖми кнопку 👇",
            reply_markup={"inline_keyboard": [[{"text": "🏠 Открыть Domus", "web_app": {"url": url}}]]}
            if settings.public_base_url else None,
        )
    return {"ok": True}


def _parse_iso(value: Optional[str]) -> Optional[datetime]:
    """Parse an ISO-8601 timestamp to naive UTC (DB stores naive UTC)."""
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None
    return dt.astimezone(timezone.utc).replace(tzinfo=None) if dt.tzinfo else dt


@app.post("/tribute/webhook")
async def tribute_webhook(request: Request):
    """Tribute payment webhook: activate access on subscription events."""
    key = settings.tribute_api_key
    if not key:
        raise HTTPException(status_code=404, detail="Not found")
    body = await request.body()
    mac = hmac.new(key.encode(), body, hashlib.sha256)
    sig = request.headers.get("trbt-signature", "")
    if not (hmac.compare_digest(sig, mac.hexdigest())
            or hmac.compare_digest(sig, base64.b64encode(mac.digest()).decode())):
        raise HTTPException(status_code=403, detail="Bad signature")
    try:
        event = json.loads(body)
    except ValueError:
        raise HTTPException(status_code=400, detail="Bad payload")

    name = event.get("name")
    p = event.get("payload") or {}
    tid = p.get("telegram_user_id")
    if name in ("new_subscription", "renewed_subscription", "cancelled_subscription") and tid:
        with Session(engine) as s:
            subscriptions.activate(
                s, int(tid),
                until=_parse_iso(p.get("expires_at")),
                charge_id=str(p.get("subscription_id") or "tribute"),
                is_recurring=(name != "cancelled_subscription"),
                user={"username": p.get("telegram_username")},
            )
        if name == "new_subscription":
            telegram_api.send_message(int(tid), "✅ Подписка активна — открой приложение из меню бота.")
    return {"ok": True}


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
    parish: Optional[str] = Query(None),
    max_distance_to_metro: Optional[str] = Query(None),
    min_gross_yield: Optional[str] = Query(None),
    only_price_drops: bool = Query(False),
    only_new: bool = Query(False),
    has_garage: bool = Query(False),
    has_elevator: bool = Query(False),
    has_terrace: bool = Query(False),
    has_al_license: bool = Query(False),
    expert_positive: bool = Query(False),
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
        parish=parish or None,
        max_distance_to_metro=_opt_float(max_distance_to_metro),
        min_gross_yield=_opt_float(min_gross_yield),
        only_price_drops=only_price_drops,
        only_new=only_new,
        has_garage=True if has_garage else None,
        has_elevator=True if has_elevator else None,
        has_terrace=True if has_terrace else None,
        has_al_license=True if has_al_license else None,
        expert_positive=expert_positive,
        south_facing=south_facing,
        exclude_ground_floor=exclude_ground_floor,
        exclude_no_coordinates=exclude_no_coordinates,
        exclude_bad_neighborhoods=exclude_bad_neighborhoods,
        only_exact_location=only_exact_location,
        only_developments=False,  # new developments live on their own /developments tab
    )

    total = count_properties(session, **filter_kwargs)
    total_pages = max(1, ceil(total / per_page))
    page_num = min(max(1, _opt_int(page, 1)), total_pages)
    offset = (page_num - 1) * per_page

    results = query_properties(
        session, sort=sort_key, limit=per_page, offset=offset, **filter_kwargs
    )
    rows = [serialize(p, s) for p, s in results]
    _overlay_owner_watch(session, rows)
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
    if parish:
        qs_params["parish"] = parish
    for key, val in (
        ("only_price_drops", only_price_drops), ("only_new", only_new),
        ("has_garage", has_garage), ("has_elevator", has_elevator),
        ("has_terrace", has_terrace), ("south_facing", south_facing),
        ("exclude_ground_floor", exclude_ground_floor),
        ("exclude_no_coordinates", exclude_no_coordinates),
        ("exclude_bad_neighborhoods", exclude_bad_neighborhoods),
        ("only_exact_location", only_exact_location),
        ("has_al_license", has_al_license),
        ("expert_positive", expert_positive),
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
        "has_al_license": has_al_license,
        "expert_positive": expert_positive,
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
    if not session.get(Property, property_id):
        raise HTTPException(status_code=404, detail="Property not found")
    user_watchlist.set_watch(session, _web_owner(), property_id, status, note)
    return RedirectResponse(url=f"/property/{property_id}", status_code=303)


@app.post("/property/{property_id}/al-override")
def web_al_override(
    property_id: int,
    value: str = Form("not_al"),
    session: Session = Depends(get_session),
):
    prop = session.get(Property, property_id)
    if prop:
        _set_al_override(session, prop, value)
    return RedirectResponse(url=f"/property/{property_id}", status_code=303)


@app.get("/watchlist", response_class=HTMLResponse)
def watchlist_view(
    request: Request,
    session: Session = Depends(get_session),
    status: Optional[str] = Query(None),
):
    owner = _web_owner()
    active = normalize_status(status)
    rows = []
    for prop, score, w in user_watchlist.list_watched(session, owner, active):
        d = serialize(prop, score)
        d["watch_status"], d["watch_note"] = w.status, w.note
        rows.append(d)
    counts = user_watchlist.counts(session, owner)
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
            "total_watched": sum(counts.values()),
        },
    )


@app.get("/areas", response_class=HTMLResponse)
def areas_view(request: Request, session: Session = Depends(get_session)):
    return templates.TemplateResponse(
        request,
        "areas.html",
        {"rows": area_scoring.compute_area_scores(session), "app_name": settings.app_name},
    )


@app.get("/leads", response_class=HTMLResponse)
def leads_view(request: Request, session: Session = Depends(get_session)):
    leads = session.exec(select(Lead).order_by(Lead.created_at.desc())).all()
    pids = [l.property_id for l in leads if l.property_id]
    props = (
        {p.id: p for p in session.exec(select(Property).where(Property.id.in_(pids))).all()}
        if pids
        else {}
    )
    rows = [
        {
            "name": l.name,
            "phone": l.phone,
            "country": l.country,
            "telegram_id": l.telegram_id,
            "created_at": l.created_at,
            "property": props.get(l.property_id),
        }
        for l in leads
    ]
    origins: dict = {}
    for l in leads:
        key = l.country or "—"
        origins[key] = origins.get(key, 0) + 1
    origins = sorted(origins.items(), key=lambda kv: kv[1], reverse=True)
    return templates.TemplateResponse(
        request,
        "leads.html",
        {"leads": rows, "origins": origins, "app_name": settings.app_name},
    )


@app.get("/exports/leads.csv")
def leads_csv(session: Session = Depends(get_session)):
    import csv
    import io

    leads = session.exec(select(Lead).order_by(Lead.created_at.desc())).all()
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["created_at", "name", "phone", "country", "telegram_id", "property_id"])
    for l in leads:
        writer.writerow(
            [
                l.created_at.isoformat(sep=" ", timespec="minutes"),
                l.name or "",
                l.phone or "",
                l.country or "",
                l.telegram_id,
                l.property_id or "",
            ]
        )
    return Response(
        content=buf.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=leads.csv"},
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
    total = count_properties(session, new_within_days=days_i, min_score=settings.new_listing_min_score)
    total_pages = max(1, ceil(total / per_page))
    page_num = min(max(1, _opt_int(page, 1)), total_pages)
    offset = (page_num - 1) * per_page
    results = query_properties(
        session, new_within_days=days_i, min_score=settings.new_listing_min_score,
        sort="newest", limit=per_page, offset=offset,
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


def _developments_stats(rows):
    """Aggregate analysis for the new-developments tab."""
    def avg(vals):
        vals = [v for v in vals if v is not None]
        return sum(vals) / len(vals) if vals else None

    by_muni: dict = {}
    for r in rows:
        d = by_muni.setdefault(r.get("municipality") or "—", {"count": 0, "ppm2": []})
        d["count"] += 1
        if r.get("price_per_m2"):
            d["ppm2"].append(r["price_per_m2"])
    municipalities = sorted(
        (
            {
                "name": m,
                "count": d["count"],
                "avg_ppm2": (sum(d["ppm2"]) / len(d["ppm2"]) if d["ppm2"] else None),
            }
            for m, d in by_muni.items()
        ),
        key=lambda x: x["count"],
        reverse=True,
    )
    return {
        "count": len(rows),
        "avg_price": avg([r.get("price") for r in rows]),
        "avg_ppm2": avg([r.get("price_per_m2") for r in rows]),
        "avg_score": avg([r.get("total_score") for r in rows]),
        "avg_metro": avg([r.get("distance_to_metro_m") for r in rows]),
        "municipalities": municipalities,
    }


@app.get("/developments", response_class=HTMLResponse)
def developments_view(
    request: Request,
    session: Session = Depends(get_session),
    sort: str = Query("score_desc"),
    limit: Optional[str] = Query(None),
    page: Optional[str] = Query(None),
):
    sort_key = sort if sort in VALID_SORTS else "score_desc"
    per_page = min(200, max(10, _opt_int(limit, 50)))
    total = count_properties(session, only_developments=True)
    total_pages = max(1, ceil(total / per_page))
    page_num = min(max(1, _opt_int(page, 1)), total_pages)
    offset = (page_num - 1) * per_page
    results = query_properties(
        session, only_developments=True, sort=sort_key, limit=per_page, offset=offset
    )
    rows = [serialize(p, s) for p, s in results]
    # Analysis is computed over the whole set, not just the current page.
    all_rows = [
        serialize(p, s)
        for p, s in query_properties(session, only_developments=True, limit=2000)
    ]
    return templates.TemplateResponse(
        request,
        "developments.html",
        {
            "rows": rows,
            "stats": _developments_stats(all_rows),
            "app_name": settings.app_name,
            "total": total,
            "page": page_num,
            "total_pages": total_pages,
            "per_page": per_page,
            "sort": sort_key,
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
    _overlay_owner_watch(session, [data])
    _enrich_with_expert(session, prop, score, data)

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
            "expert_text": prop.expert_text,
            "expert_delta": prop.expert_delta,
            "expert": expert_note(data, score.explanation_json if score else None),
            "app_name": settings.app_name,
            "watch_statuses": WATCH_STATUSES,
            "watch_labels": WATCH_LABELS,
            "watch_colors": WATCH_COLORS,
        },
    )
