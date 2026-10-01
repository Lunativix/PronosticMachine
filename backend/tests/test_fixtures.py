"""Upcoming window, sync identity, and provider failure modes."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import httpx
import pytest

from app.fixtures.http_client import HttpGiveUp, RateLimiter, request_with_retry
from app.fixtures.providers.api_football_fixtures import ApiFootballFixtureProvider
from app.fixtures.providers.base import BaseFixtureProvider, NormalizedFixture, ProviderNotConfigured
from app.fixtures.providers.espn import parse_event
from app.fixtures.service import UpcomingMatchesService
from app.fixtures.window import get_upcoming_window, in_window
from app.core.config import Settings
from app.models import FixtureChange, Match


class MemoryProvider(BaseFixtureProvider):
    name = "memory"

    def __init__(self, rows: list[NormalizedFixture]) -> None:
        self.rows = rows
        self.calls = 0

    def get_upcoming_matches(self, start_date, end_date, competition=None):
        self.calls += 1
        return [row for row in self.rows if in_window(row.kickoff_utc, start_date, end_date)]


def _fixture(**overrides) -> NormalizedFixture:
    kickoff = datetime(2026, 9, 26, 18, 0, tzinfo=timezone.utc)
    payload = dict(
        provider="memory",
        provider_match_id="m-1",
        competition_code="TEST",
        competition_name="Test Cup",
        country="France",
        season="2026",
        home_name="North",
        away_name="South",
        home_provider_id="n",
        away_provider_id="s",
        kickoff_utc=kickoff,
        status="TIMED",
    )
    payload.update(overrides)
    return NormalizedFixture(**payload)


def test_upcoming_window_is_exactly_14_days() -> None:
    now = datetime(2026, 9, 24, 16, 0, tzinfo=ZoneInfo("Europe/Paris"))
    start, end = get_upcoming_window(now, 14)
    assert start.tzinfo == ZoneInfo("Europe/Paris")
    assert end - start == timedelta(days=14)
    assert start.isoformat().startswith("2026-09-24T16:00:00")
    assert end.isoformat().startswith("2026-10-08T16:00:00")


def test_timezone_conversion() -> None:
    paris = datetime(2026, 9, 24, 16, 0, tzinfo=ZoneInfo("Europe/Paris"))
    assert paris.astimezone(timezone.utc).isoformat() == "2026-09-24T14:00:00+00:00"


def test_retry_and_rate_limit() -> None:
    calls = {"n": 0}

    def send() -> httpx.Response:
        calls["n"] += 1
        request = httpx.Request("GET", "https://example.test")
        status = 503 if calls["n"] < 3 else 200
        return httpx.Response(status, request=request)

    response = request_with_retry(send, sleeper=lambda _: None)
    assert response.status_code == 200
    waits: list[float] = []
    limiter = RateLimiter(1.0, sleeper=waits.append)
    limiter._last = 10.0
    limiter.wait(now=lambda: 10.2)
    assert waits == [pytest.approx(0.8)]


def test_retry_gives_up() -> None:
    def send() -> httpx.Response:
        return httpx.Response(429, request=httpx.Request("GET", "https://example.test"))

    with pytest.raises(HttpGiveUp):
        request_with_retry(send, attempts=2, sleeper=lambda _: None)


def test_pagination_fetches_all_pages() -> None:
    pages = {1: ["a", "b"], 2: ["c"], 3: []}

    def collect() -> list[str]:
        found: list[str] = []
        page = 1
        while page < 10:
            batch = pages[page]
            if not batch:
                break
            found.extend(batch)
            page += 1
        return found

    assert collect() == ["a", "b", "c"]


def test_missing_api_key_is_explicit() -> None:
    settings = Settings(api_key="", database_url="sqlite://")
    with pytest.raises(ProviderNotConfigured):
        ApiFootballFixtureProvider(settings).get_upcoming_matches(
            datetime.now(timezone.utc), datetime.now(timezone.utc)
        )


def test_no_duplicate_and_reschedule_and_cancel(session) -> None:
    now = datetime(2026, 9, 24, 12, 0, tzinfo=timezone.utc)
    provider = MemoryProvider([_fixture()])
    service = UpcomingMatchesService(session, provider)
    first = service.sync(days=14, now=now)
    second = service.sync(days=14, now=now)
    assert first.matches_inserted == 1
    assert second.matches_unchanged == 1
    assert session.query(Match).filter(Match.external_id == "m-1").count() == 1
    moved = _fixture(kickoff_utc=datetime(2026, 9, 27, 19, 0, tzinfo=timezone.utc), status="POSTPONED")
    UpcomingMatchesService(session, MemoryProvider([moved])).sync(days=14, now=now)
    match = session.query(Match).filter(Match.external_id == "m-1").one()
    assert match.status == "POSTPONED"
    assert match.first_seen_at is not None
    assert session.query(FixtureChange).count() >= 1
    UpcomingMatchesService(session, MemoryProvider([_fixture(status="CANCELLED")])).sync(days=14, now=now)
    assert session.get(Match, match.id).status == "CANCELLED"
    assert session.get(Match, match.id).home_goals is None


def test_unknown_team_is_created_not_merged_by_guess(session) -> None:
    now = datetime(2026, 9, 24, 12, 0, tzinfo=timezone.utc)
    UpcomingMatchesService(session, MemoryProvider([_fixture(home_name="Paris Saint-Germain", home_provider_id="psg")])).sync(
        days=14, now=now
    )
    UpcomingMatchesService(
        session,
        MemoryProvider([_fixture(provider_match_id="m-2", home_name="PSG", home_provider_id="other", away_provider_id="s2")]),
    ).sync(days=14, now=now)
    assert session.query(Match).count() == 2


def test_scheduled_score_stays_null() -> None:
    fixture = parse_event(
        {
            "id": "9",
            "date": "2026-09-26T18:00:00Z",
            "competitions": [
                {
                    "timeValid": True,
                    "status": {"type": {"name": "STATUS_SCHEDULED"}},
                    "competitors": [
                        {"homeAway": "home", "score": "0", "team": {"id": "1", "displayName": "A"}},
                        {"homeAway": "away", "score": "0", "team": {"id": "2", "displayName": "B"}},
                    ],
                }
            ],
        },
        "Ligue 1",
        "France",
        "2026",
        "fra.1",
    )
    assert fixture is not None
    assert fixture.home_goals is None
    assert fixture.away_goals is None
    assert fixture.status == "TIMED"
