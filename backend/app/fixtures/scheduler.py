"""Hourly fixture sync. A missing provider is logged and does not create matches."""

from __future__ import annotations

import logging

from apscheduler.schedulers.background import BackgroundScheduler

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.fixtures.providers.api_football_fixtures import ApiFootballFixtureProvider
from app.fixtures.providers.base import ProviderNotConfigured
from app.fixtures.providers.espn import EspnFixtureProvider
from app.fixtures.service import UpcomingMatchesService

LOGGER = logging.getLogger(__name__)
SCHEDULER = BackgroundScheduler(timezone="Europe/Paris")


def build_provider():
    settings = get_settings()
    name = settings.fixture_provider.lower()
    if name in {"", "none", "off"}:
        raise ProviderNotConfigured("FIXTURE_PROVIDER is not configured.")
    if name == "espn":
        return EspnFixtureProvider()
    if name == "api_football":
        return ApiFootballFixtureProvider(settings)
    raise ProviderNotConfigured(f"Unknown FIXTURE_PROVIDER: {name}")


def sync_upcoming_matches() -> None:
    settings = get_settings()
    try:
        provider = build_provider()
    except ProviderNotConfigured as exc:
        LOGGER.error("fixture sync skipped", extra={"context": {"message": str(exc)}})
        return
    with SessionLocal() as session:
        UpcomingMatchesService(session, provider, settings).sync(days=max(settings.fixture_window_days, 1))
        from app.analysis.service import analyze_upcoming_matches

        analyze_upcoming_matches(session, settings)


def start_scheduler() -> None:
    if SCHEDULER.running:
        return
    minutes = max(get_settings().fixture_sync_interval_minutes, 15)
    SCHEDULER.add_job(sync_upcoming_matches, "interval", minutes=minutes, id="fixture-sync", replace_existing=True)
    SCHEDULER.start()


def next_run() -> str | None:
    job = SCHEDULER.get_job("fixture-sync")
    if job is None or job.next_run_time is None:
        return None
    return job.next_run_time.isoformat()
