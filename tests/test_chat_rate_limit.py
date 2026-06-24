"""Per-user chat rate limit (anti-abuse on LLM cost)."""
import pytest
from fastapi import HTTPException

import app.main as main
from app.core.config import settings


def test_blocks_after_cap(monkeypatch):
    monkeypatch.setattr(settings, "chat_rate_limit_per_min", 3)
    main._chat_hits.clear()
    for _ in range(3):
        main._check_chat_rate_limit(999)  # within the cap -> ok
    with pytest.raises(HTTPException) as exc:
        main._check_chat_rate_limit(999)  # 4th in the same minute -> blocked
    assert exc.value.status_code == 429


def test_zero_disables(monkeypatch):
    monkeypatch.setattr(settings, "chat_rate_limit_per_min", 0)
    main._chat_hits.clear()
    for _ in range(100):
        main._check_chat_rate_limit(123)  # 0 disables -> never raises


def test_limit_is_per_user(monkeypatch):
    monkeypatch.setattr(settings, "chat_rate_limit_per_min", 2)
    main._chat_hits.clear()
    main._check_chat_rate_limit(1)
    main._check_chat_rate_limit(1)
    main._check_chat_rate_limit(2)  # a different user is unaffected
    with pytest.raises(HTTPException):
        main._check_chat_rate_limit(1)
