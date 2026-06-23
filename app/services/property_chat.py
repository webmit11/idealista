"""Conversational Q&A about a single listing, grounded in its own data.

The caller supplies a compact context (facts + cached expert note) and the running
message history; the model answers only about this property. `anthropic` is imported
lazily so the package stays optional.
"""
import logging
from typing import Optional

from app.core.config import settings

logger = logging.getLogger("property_chat")

_SYSTEM = (
    "Ты — инвестиционный консультант по недвижимости в Порту (Португалия). "
    "Отвечай кратко (2–5 предложений), по делу и по-русски, ТОЛЬКО про этот объект и "
    "опираясь на данные ниже. Не выдумывай факты: если данных не хватает — скажи об "
    "этом и предложи уточнить у агента. Можно советовать по торгу, аренде и рискам."
)


def answer(context: str, history: list) -> Optional[str]:
    """Return the assistant reply for the given listing context + chat history."""
    if not settings.anthropic_api_key:
        return None
    msgs = []
    for m in (history or []):
        role = m.get("role")
        content = (m.get("content") or "").strip()
        if role in ("user", "assistant") and content:
            msgs.append({"role": role, "content": content[:1500]})
    msgs = msgs[-12:]
    if not msgs or msgs[-1]["role"] != "user":
        return None
    try:
        import anthropic

        client = anthropic.Anthropic(api_key=settings.anthropic_api_key, timeout=40, max_retries=3)
        resp = client.messages.create(
            model=settings.chat_llm_model,
            max_tokens=500,
            system=_SYSTEM + "\n\nДанные объекта:\n" + context,
            messages=msgs,
        )
        parts = [b.text for b in resp.content if getattr(b, "type", None) == "text"]
        return ("".join(parts)).strip() or None
    except Exception as exc:  # network / auth / quota
        logger.warning("property chat failed: %s", exc)
        return None
