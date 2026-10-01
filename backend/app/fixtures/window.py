"""Sliding fixture window in Europe/Paris, stored later as UTC."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

PARIS = ZoneInfo("Europe/Paris")


def get_upcoming_window(now: datetime | None = None, days: int = 14) -> tuple[datetime, datetime]:
    if days < 1:
        raise ValueError("days must be at least 1")
    moment = now or datetime.now(timezone.utc)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    start = moment.astimezone(PARIS)
    end = start + timedelta(days=days)
    return start, end


def window_dates(start: datetime, end: datetime) -> list[str]:
    """Calendar dates covering the window, plus one day on each side for midnight and DST."""
    start_paris = start.astimezone(PARIS)
    end_paris = end.astimezone(PARIS)
    day = start_paris.date() - timedelta(days=1)
    last = end_paris.date() + timedelta(days=1)
    dates: list[str] = []
    while day <= last:
        dates.append(day.strftime("%Y%m%d"))
        day += timedelta(days=1)
    return dates


def in_window(kickoff_utc: datetime, start: datetime, end: datetime) -> bool:
    kickoff = kickoff_utc.astimezone(timezone.utc)
    return start.astimezone(timezone.utc) <= kickoff <= end.astimezone(timezone.utc)
