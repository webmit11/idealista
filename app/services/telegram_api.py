"""Thin Telegram Bot API client for the bits the subscription flow needs:
creating Stars invoice links, answering pre-checkout queries, sending messages,
and registering the webhook. Returns None / False on failure (callers handle it).
"""
import logging
from typing import Optional

import httpx

from app.core.config import settings

logger = logging.getLogger("telegram_api")
_TIMEOUT = 15.0


def _call(method: str, payload: dict) -> Optional[dict]:
    token = settings.telegram_bot_token
    if not token:
        return None
    try:
        with httpx.Client(timeout=_TIMEOUT) as client:
            r = client.post(f"https://api.telegram.org/bot{token}/{method}", json=payload)
        data = r.json()
        if not data.get("ok"):
            logger.warning("telegram %s failed: %s", method, data.get("description"))
            return None
        return data.get("result")
    except Exception as exc:
        logger.warning("telegram %s error: %s", method, exc)
        return None


def create_stars_subscription_link(payload: str) -> Optional[str]:
    """Create an invoice link for a recurring Stars subscription."""
    result = _call("createInvoiceLink", {
        "title": settings.subscription_title,
        "description": settings.subscription_description,
        "payload": payload,
        "currency": "XTR",
        "prices": [{"label": "Подписка", "amount": settings.subscription_price_stars}],
        "subscription_period": settings.subscription_period_days * 86400,
    })
    return result if isinstance(result, str) else None


def answer_pre_checkout(query_id: str, ok: bool = True, error: str = "") -> bool:
    payload = {"pre_checkout_query_id": query_id, "ok": ok}
    if not ok and error:
        payload["error_message"] = error
    return _call("answerPreCheckoutQuery", payload) is not None


def send_message(chat_id: int, text: str, reply_markup: Optional[dict] = None) -> None:
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
    if reply_markup:
        payload["reply_markup"] = reply_markup
    _call("sendMessage", payload)


def set_webhook(url: str, secret_token: str) -> bool:
    return _call("setWebhook", {
        "url": url,
        "secret_token": secret_token,
        "allowed_updates": ["message", "pre_checkout_query"],
    }) is not None
