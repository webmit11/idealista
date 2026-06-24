"""Conversational Q&A about a single listing, as a friendly named consultant.

The caller supplies a compact context (facts + cached expert note) and the running
message history; the model answers only about this property, in two parts (a short
opener + a detailed reply). `anthropic` is imported lazily so the package stays optional.
"""
import logging
import re
from typing import Optional

from app.core.config import settings

logger = logging.getLogger("property_chat")

_SYSTEM = (
    "Тебя зовут {name}. Ты — консультант по недвижимости в Порту (сервис Domus), "
    "женщина; общаешься тепло, живо, от первого лица. Отвечай ТОЛЬКО про этот объект, "
    "опираясь на данные ниже; не выдумывай — если данных не хватает, скажи и предложи "
    "уточнить. Можно советовать по торгу, аренде, рискам, проживанию.\n"
    "Формат строго: сначала короткая живая фраза-реакция (до 12 слов), затем на новой "
    "строке разделитель '|||', затем подробный ответ по сути (3–5 предложений). По-русски."
)


def answer(context: str, history: list, consultant: str = "Мария") -> Optional[dict]:
    """Return {"short", "long"} for the listing context + chat history, or None."""
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
            max_tokens=600,
            system=_SYSTEM.format(name=consultant) + "\n\nДанные объекта:\n" + context,
            messages=msgs,
        )
        text = "".join(b.text for b in resp.content if getattr(b, "type", None) == "text").strip()
        if not text:
            return None
        if "|||" in text:
            short, long = text.split("|||", 1)
        else:  # fallback: first sentence is the opener, the rest is the detail
            parts = re.split(r"(?<=[.!?])\s+", text, maxsplit=1)
            short, long = parts[0], (parts[1] if len(parts) > 1 else "")
        return {"short": short.strip(), "long": long.strip()}
    except Exception as exc:  # network / auth / quota
        logger.warning("property chat failed: %s", exc)
        return None
