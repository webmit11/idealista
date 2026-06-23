"""LLM expert commentary + photo-based score adjustment via the Claude API.

One call returns both the prose verdict and a numeric score_delta (-10..+10) the
vision model assigns from the listing photos (condition, renovation, red flags).
Returns (None, None) when no key / on error so callers fall back to the rule-based
note and a zero adjustment. `anthropic` is imported lazily.
"""
import logging
from typing import Optional, Tuple

from pydantic import BaseModel

from app.core.config import settings

logger = logging.getLogger("expert_llm")

_SYSTEM = (
    "Ты — опытный консультант по недвижимости в Порту (Португалия) — и для жизни, и под доход. "
    "По данным объекта И по приложенным фотографиям дай два результата.\n"
    "1) commentary: живое мнение в 3–5 предложениях — чем объект интересен и кому "
    "подойдёт — для собственной жизни и/или под доход (аренду), и что видно на фото (состояние, уровень ремонта, свет, планировка, "
    "тревожные звоночки). Простой текст по-русски, без заголовков и списков, без воды.\n"
    "2) score_delta: целое число от -10 до 10 — на сколько баллов скорректировать "
    "инвестиционную оценку с учётом того, что видно на ФОТО, относительно сухих цифр. "
    "0 — фото подтверждают данные; плюс — лучше, чем по цифрам (свежий ремонт, свет, "
    "вид); минус — хуже (убитое состояние, видимые дефекты, плесень, тёмные комнаты, "
    "красные флаги). Опирайся только на данные и фото, ничего не выдумывай.\n"
    "Если в данных указана действующая AL-лицензия — анализируй объект как готовый "
    "бизнес под краткосрочную аренду (Alojamento Local / Airbnb): говори про "
    "краткосрочный доход и ценность самой лицензии, а не про долгосрочную аренду, и "
    "укажи, что подойдёт инвесторам под Airbnb."
)


class _Rating(BaseModel):
    commentary: str
    score_delta: int


def expert_worth_generating(prop, score_total) -> bool:
    """Skip LLM generation for listings that are BOTH far from metro and low-score
    (the free rule-based note covers them). AL listings are always worth it."""
    if getattr(prop, "has_al_license", False):
        return True
    dist = getattr(prop, "distance_to_metro_m", None)
    far = dist is not None and dist > settings.expert_skip_distance_m
    low = (score_total or 0) < settings.expert_skip_below_score
    return not (far and low)


def expert_facts(prop, explanation) -> str:
    """Build the compact facts string fed to the model alongside the photos."""
    expl = explanation or {}
    risks = ", ".join(expl.get("risk_flags") or []) or "нет"
    bonuses = ", ".join(expl.get("bonus_flags") or []) or "нет"
    med = expl.get("median_price_per_m2_benchmark")
    g = lambda k: getattr(prop, k, None)  # noqa: E731
    facts = (
        f"Тип: {g('typology')}; цена: {g('price')} €; €/m2: {g('price_per_m2')}; "
        f"медиана района €/m2: {med}; площадь: {g('area_m2')} m2; доходность(долгосрочная): {g('gross_yield_percent')}%; "
        f"метро: {g('nearest_metro_station')} ~{g('walking_minutes_to_metro_estimate')} мин пешком; "
        f"состояние: {g('condition')}; лифт: {g('has_elevator')}; гараж: {g('has_garage')}; "
        f"терраса: {g('has_terrace')}; район: {g('municipality')}/{g('parish')}; "
        f"флаги риска: {risks}; бонусы: {bonuses}."
    )
    if g("has_al_license"):
        from app.services.investment import al_multiplier

        gy = g("gross_yield_percent")
        mult = al_multiplier(g("typology"))
        al_y = round(gy * mult, 1) if gy else None
        facts += (
            f" ВАЖНО: у объекта ДЕЙСТВУЮЩАЯ AL-лицензия (Alojamento Local, краткосрочная аренда). "
            f"Анализируй его как готовый бизнес под краткосрочную аренду/Airbnb, а НЕ под долгосрочную: "
            f"оценочная краткосрочная доходность ~{al_y}% валовая (≈{mult}× к долгосрочной, расходы выше). "
            f"Подчеркни ценность самой лицензии — новые AL в Порту во многих зонах заморожены."
        )
    return facts


def _fetch_images(urls: list) -> list:
    import base64
    import httpx

    limit = settings.expert_vision_images
    out: list = []
    if limit <= 0 or not urls:
        return out
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        with httpx.Client(timeout=15, headers=headers, follow_redirects=True) as cli:
            for u in urls[:limit]:
                try:
                    r = cli.get(u)
                except Exception:
                    continue
                ct = (r.headers.get("content-type") or "").split(";")[0]
                if r.status_code == 200 and ct.startswith("image") and len(r.content) < 4_000_000:
                    out.append((ct, base64.standard_b64encode(r.content).decode()))
    except Exception:
        pass
    return out


def generate_expert(facts: str, image_urls: Optional[list] = None) -> Tuple[Optional[str], Optional[int]]:
    if not settings.anthropic_api_key:
        return None, None
    try:
        import anthropic

        content: list = [{"type": "text", "text": facts}]
        for media_type, data in _fetch_images(image_urls or []):
            content.append({"type": "image", "source": {"type": "base64", "media_type": media_type, "data": data}})

        client = anthropic.Anthropic(api_key=settings.anthropic_api_key, timeout=40, max_retries=5)
        resp = client.messages.parse(
            model=settings.expert_llm_model,
            max_tokens=600,
            system=_SYSTEM,
            messages=[{"role": "user", "content": content}],
            output_format=_Rating,
        )
        r = resp.parsed_output
        if r is None:
            return None, None
        delta = max(-10, min(10, int(r.score_delta)))
        return (r.commentary.strip() or None), delta
    except Exception as exc:  # network / auth / quota / parse — fall back
        logger.warning("expert LLM failed: %s", exc)
        return None, None
