"""Internal alerts. External channels stay silent without explicit configuration."""

from __future__ import annotations

import logging

import httpx
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models import Alert, BetOpportunity

LOGGER = logging.getLogger(__name__)


def record_signal(session: Session, opportunity: BetOpportunity, settings: Settings) -> Alert:
    payload = {
        "match_id": opportunity.match_id,
        "market": opportunity.market,
        "selection": opportunity.selection,
        "odds": opportunity.odds,
        "model_probability": opportunity.model_probability,
        "edge": opportunity.edge,
        "expected_value": opportunity.expected_value,
        "signal_quality": opportunity.signal_quality,
    }
    alert = Alert(
        opportunity_id=opportunity.id,
        message="Statistical signal detected",
        payload=payload,
        channel="internal",
        delivered=False,
    )
    session.add(alert)
    session.flush()
    _dispatch(alert, settings)
    return alert


def _post(url: str, payload: dict[str, object]) -> None:
    try:
        httpx.post(url, json=payload, timeout=10.0)
    except httpx.HTTPError:
        LOGGER.warning("alert delivery failed", extra={"context": {"channel": "external"}})


def _dispatch(alert: Alert, settings: Settings) -> None:
    if settings.discord_webhook_url:
        _post(settings.discord_webhook_url, {"content": alert.message})
        alert.channel = "discord"
        alert.delivered = True
    if settings.telegram_bot_token and settings.telegram_chat_id:
        _post(
            f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage",
            {"chat_id": settings.telegram_chat_id, "text": alert.message},
        )
        alert.channel = "telegram"
        alert.delivered = True
    if settings.smtp_url:
        LOGGER.info("email channel configured but SMTP delivery is left to the operator", extra={"context": {}})
