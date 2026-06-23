"""Optional LLM-written expert commentary via the Claude API (cached per property).

Returns None when no API key is configured or on any error, so callers fall back
to the deterministic rule-based note. `anthropic` is imported lazily so the app
runs without the SDK installed when the feature is off.
"""
import logging
from typing import Optional

from app.core.config import settings

logger = logging.getLogger("expert_llm")

_SYSTEM = (
    "Ты — опытный инвестиционный консультант по недвижимости в Порту (Португалия). "
    "По данным объекта напиши живое, конкретное мнение в 2–4 предложениях: чем объект "
    "интересен и кому он подойдёт (инвестору под аренду, под ремонт и перепродажу, "
    "семье, для собственного проживания и т.п.). Опирайся ТОЛЬКО на приведённые данные, "
    "ничего не выдумывай. Пиши по-русски, по делу, без общих фраз и воды."
)


def generate_expert_text(facts: str) -> Optional[str]:
    if not settings.anthropic_api_key:
        return None
    try:
        import anthropic

        client = anthropic.Anthropic(api_key=settings.anthropic_api_key, timeout=20)
        resp = client.messages.create(
            model=settings.expert_llm_model,
            max_tokens=400,
            system=_SYSTEM,
            messages=[{"role": "user", "content": facts}],
        )
        text = next((b.text for b in resp.content if b.type == "text"), "").strip()
        return text or None
    except Exception as exc:  # network / auth / quota — fall back to rule-based
        logger.warning("expert LLM failed: %s", exc)
        return None
