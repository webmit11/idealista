"""Telegram Mini App (WebApp) auth.

Validates `initData` per Telegram's spec (HMAC-SHA256 with the bot token) and
restricts access to the configured owner — exclusive, single-user use.
https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app
"""
import hashlib
import hmac
import json
import time
from typing import Optional
from urllib.parse import parse_qsl

from fastapi import Depends, Header, HTTPException
from sqlmodel import Session

from app.core.config import settings
from app.db.database import get_session
from app.services.subscriptions import is_active, is_owner


def validate_init_data(init_data: str, bot_token: str, max_age_seconds: int = 86400) -> Optional[dict]:
    """Return the parsed payload (incl. `user`) if the signature is valid & fresh, else None."""
    if not init_data or not bot_token:
        return None
    try:
        pairs = dict(parse_qsl(init_data, strict_parsing=True))
    except ValueError:
        return None
    received_hash = pairs.pop("hash", None)
    if not received_hash:
        return None

    data_check_string = "\n".join(f"{k}={pairs[k]}" for k in sorted(pairs))
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    computed = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(computed, received_hash):
        return None

    if max_age_seconds:
        try:
            if time.time() - int(pairs.get("auth_date", "0")) > max_age_seconds:
                return None
        except ValueError:
            return None

    user = None
    if "user" in pairs:
        try:
            user = json.loads(pairs["user"])
        except (ValueError, TypeError):
            user = None
    return {"user": user, "auth_date": pairs.get("auth_date")}


def require_telegram_user(x_telegram_init_data: Optional[str] = Header(default=None)) -> dict:
    """FastAPI dependency: validate initData and return the Telegram user (any valid user)."""
    data = validate_init_data(x_telegram_init_data or "", settings.telegram_bot_token or "")
    user = (data or {}).get("user") or {}
    if not user.get("id"):
        raise HTTPException(status_code=401, detail="Invalid Telegram auth")
    return user


def require_subscriber(
    user: dict = Depends(require_telegram_user),
    session: Session = Depends(get_session),
) -> dict:
    """Validated Telegram user with active access (owner or paid subscriber)."""
    if not is_active(session, int(user["id"])):
        raise HTTPException(status_code=402, detail="Subscription required")
    return user


def require_owner(user: dict = Depends(require_telegram_user)) -> dict:
    """Validated Telegram user that is the owner."""
    if not is_owner(int(user["id"])):
        raise HTTPException(status_code=403, detail="Owner only")
    return user
