"""Notification channels for alerts (Telegram / email).

Channel is chosen by `ALERT_CHANNEL` (auto|telegram|email|none). "auto" picks
Telegram if its token+chat are set, else email if SMTP is set.
"""
import logging
import smtplib
from email.message import EmailMessage

import httpx

from app.core.config import settings

logger = logging.getLogger("notifier")


class Notifier:
    def __init__(self):
        self.channel = self._resolve_channel()

    @staticmethod
    def _resolve_channel() -> str:
        c = (settings.alert_channel or "auto").lower()
        if c != "auto":
            return c
        if settings.telegram_bot_token and settings.telegram_chat_id:
            return "telegram"
        if settings.smtp_host and settings.alert_email_to:
            return "email"
        return "none"

    def is_configured(self) -> bool:
        if self.channel == "telegram":
            return bool(settings.telegram_bot_token and settings.telegram_chat_id)
        if self.channel == "email":
            return bool(settings.smtp_host and settings.alert_email_to)
        return False

    def send(self, text: str, subject: str = "Porto Investment Finder") -> None:
        if self.channel == "telegram":
            self._send_telegram(text)
        elif self.channel == "email":
            self._send_email(subject, text)
        else:
            raise RuntimeError("No alert channel configured")
        logger.info("alert sent", extra={"extra_fields": {"channel": self.channel}})

    def _send_telegram(self, text: str) -> None:
        url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage"
        with httpx.Client(timeout=20) as client:
            resp = client.post(
                url,
                json={
                    "chat_id": settings.telegram_chat_id,
                    "text": text[:4000],  # Telegram hard limit ~4096
                    "disable_web_page_preview": True,
                },
            )
            resp.raise_for_status()

    def _send_email(self, subject: str, text: str) -> None:
        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = settings.smtp_from or settings.smtp_user or "alerts@localhost"
        msg["To"] = settings.alert_email_to
        msg.set_content(text)
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20) as server:
            if settings.smtp_tls:
                server.starttls()
            if settings.smtp_user:
                server.login(settings.smtp_user, settings.smtp_password or "")
            server.send_message(msg)
