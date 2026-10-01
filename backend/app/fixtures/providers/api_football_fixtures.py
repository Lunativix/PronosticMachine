"""API-Football fixtures. Idle unless API_KEY is set. Follows every result page."""

from __future__ import annotations

from datetime import datetime, timezone

import httpx

from app.core.config import Settings
from app.fixtures.catalog import active_competitions
from app.fixtures.http_client import RateLimiter, request_with_retry
from app.fixtures.providers.base import BaseFixtureProvider, NormalizedFixture, ProviderNotConfigured
from app.fixtures.window import in_window

STATUS_MAP = {
    "NS": "SCHEDULED",
    "TBD": "SCHEDULED",
    "1H": "LIVE",
    "HT": "LIVE",
    "2H": "LIVE",
    "ET": "LIVE",
    "BT": "LIVE",
    "P": "LIVE",
    "LIVE": "LIVE",
    "FT": "FINISHED",
    "AET": "FINISHED",
    "PEN": "FINISHED",
    "PST": "POSTPONED",
    "CANC": "CANCELLED",
    "ABD": "CANCELLED",
    "AWD": "FINISHED",
    "WO": "FINISHED",
    "SUSP": "SUSPENDED",
    "INT": "SUSPENDED",
}


class ApiFootballFixtureProvider(BaseFixtureProvider):
    name = "api_football"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.limiter = RateLimiter(0.35)

    def get_upcoming_matches(
        self,
        start_date: datetime,
        end_date: datetime,
        competition: str | None = None,
    ) -> list[NormalizedFixture]:
        if not self.settings.api_key:
            raise ProviderNotConfigured("API_KEY is empty. Fixture provider api_football is not configured.")
        start = start_date.astimezone(timezone.utc).date().isoformat()
        end = end_date.astimezone(timezone.utc).date().isoformat()
        found: dict[str, NormalizedFixture] = {}
        with httpx.Client(timeout=30.0) as client:
            for row in active_competitions(self.name, competition):
                page = 1
                while page < 50:
                    self.limiter.wait()
                    payload = self._page(client, row.providers[self.name], row.season, start, end, page)
                    for item in payload.get("response") or []:
                        fixture = _parse(item, row.name, row.country)
                        if fixture and in_window(fixture.kickoff_utc, start_date, end_date):
                            found[fixture.provider_match_id] = fixture
                    paging = payload.get("paging") or {}
                    total = int(paging.get("total") or 1)
                    if page >= total:
                        break
                    page += 1
        return list(found.values())

    def _page(self, client: httpx.Client, league: str, season: str, start: str, end: str, page: int) -> dict:
        def send() -> httpx.Response:
            return client.get(
                f"{self.settings.api_football_base_url}/fixtures",
                params={"league": league, "season": season, "from": start, "to": end, "page": page},
                headers={"x-apisports-key": self.settings.api_key},
            )

        response = request_with_retry(send)
        response.raise_for_status()
        return response.json()


def _parse(item: dict, competition: str, country: str) -> NormalizedFixture | None:
    fixture = item.get("fixture") or {}
    teams = item.get("teams") or {}
    goals = item.get("goals") or {}
    status = STATUS_MAP.get((fixture.get("status") or {}).get("short") or "", "UNKNOWN")
    if not fixture.get("id") or not fixture.get("date"):
        return None
    kickoff = datetime.fromisoformat(str(fixture["date"]).replace("Z", "+00:00")).astimezone(timezone.utc)
    home = teams.get("home") or {}
    away = teams.get("away") or {}
    return NormalizedFixture(
        provider="api-football",
        provider_match_id=str(fixture["id"]),
        competition_code=str((item.get("league") or {}).get("id") or ""),
        competition_name=competition,
        country=country,
        season=str((item.get("league") or {}).get("season") or ""),
        home_name=str(home.get("name") or ""),
        away_name=str(away.get("name") or ""),
        home_provider_id=str(home.get("id") or ""),
        away_provider_id=str(away.get("id") or ""),
        kickoff_utc=kickoff,
        status=status,
        home_goals=goals.get("home") if status in {"FINISHED", "LIVE"} else None,
        away_goals=goals.get("away") if status in {"FINISHED", "LIVE"} else None,
        venue=(fixture.get("venue") or {}).get("name"),
        referee=fixture.get("referee"),
        round_name=(item.get("league") or {}).get("round"),
        home_logo=home.get("logo"),
        away_logo=away.get("logo"),
    )
