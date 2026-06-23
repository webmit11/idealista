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
    "Ты — опытный инвестиционный консультант по недвижимости в Порту (Португалия). "
    "По данным объекта И по приложенным фотографиям дай два результата.\n"
    "1) commentary: живое мнение в 3–5 предложениях — чем объект интересен и кому "
    "подойдёт, и что видно на фото (состояние, уровень ремонта, свет, планировка, "
    "тревожные звоночки). Простой текст по-русски, без заголовков и списков, без воды.\n"
    "2) score_delta: целое число от -10 до 10 — на сколько баллов скорректировать "
    "инвестиционную оценку с учётом того, что видно на ФОТО, относительно сухих цифр. "
    "0 — фото подтверждают данные; плюс — лучше, чем по цифрам (свежий ремонт, свет, "
    "вид); минус — хуже (убитое состояние, видимые дефекты, плесень, тёмные комнаты, "
    "красные флаги). Опирайся только на данные и фото, ничего не выдумывай."
)


class _Rating(BaseModel):
    commentary: str
    score_delta: int


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

        client = anthropic.Anthropic(api_key=settings.anthropic_api_key, timeout=40)
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
