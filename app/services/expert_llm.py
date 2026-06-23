"""Optional LLM-written expert commentary via the Claude API (cached per property).

Sends the listing facts plus a few photos (vision) so the model can also judge
condition / renovation / light from the images. Returns None when no API key is
configured or on any error, so callers fall back to the rule-based note.
`anthropic` is imported lazily so the app runs without the SDK when off.
"""
import logging
from typing import Optional

from app.core.config import settings

logger = logging.getLogger("expert_llm")

_SYSTEM = (
    "Ты — опытный инвестиционный консультант по недвижимости в Порту (Португалия). "
    "По данным объекта И по приложенным фотографиям напиши живое, конкретное мнение "
    "в 3–5 предложениях: чем объект интересен и кому подойдёт (инвестору под аренду, "
    "под ремонт и перепродажу, семье, для собственного проживания), и что видно на фото "
    "— состояние и уровень ремонта, свет и планировка, тревожные звоночки, если есть. "
    "Опирайся ТОЛЬКО на приведённые данные и фотографии, ничего не выдумывай. "
    "Простой текст по-русски, без заголовков и списков, по делу, без воды."
)


def _fetch_images(urls: list) -> list:
    """Download up to N listing photos and return (media_type, base64) tuples."""
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


def generate_expert_text(facts: str, image_urls: Optional[list] = None) -> Optional[str]:
    if not settings.anthropic_api_key:
        return None
    try:
        import anthropic

        content: list = [{"type": "text", "text": facts}]
        for media_type, data in _fetch_images(image_urls or []):
            content.append({"type": "image", "source": {"type": "base64", "media_type": media_type, "data": data}})

        client = anthropic.Anthropic(api_key=settings.anthropic_api_key, timeout=40)
        resp = client.messages.create(
            model=settings.expert_llm_model,
            max_tokens=500,
            system=_SYSTEM,
            messages=[{"role": "user", "content": content}],
        )
        text = next((b.text for b in resp.content if b.type == "text"), "").strip()
        return text or None
    except Exception as exc:  # network / auth / quota / vision — fall back to rule-based
        logger.warning("expert LLM failed: %s", exc)
        return None
