"""API-Football adapter. It stays idle unless API_KEY is set."""

from __future__ import annotations

import pandas as pd

from app.core.config import Settings
from app.data.providers.base import FootballDataProvider, ProviderDisabled


class ApiFootballProvider(FootballDataProvider):
    name = "api_football"

    def __init__(self, settings: Settings, league: int, season: int) -> None:
        self.settings = settings
        self.league = league
        self.season = season

    def load(self) -> pd.DataFrame:
        if not self.settings.api_key:
            raise ProviderDisabled("API_KEY is empty. Import historical files or set API_KEY.")
        import httpx

        response = httpx.get(
            f"{self.settings.api_football_base_url}/fixtures",
            params={"league": self.league, "season": self.season},
            headers={"x-apisports-key": self.settings.api_key},
            timeout=30.0,
        )
        response.raise_for_status()
        return _normalize(response.json())


def _normalize(payload: dict) -> pd.DataFrame:
    rows = []
    for item in payload.get("response", []):
        fixture = item.get("fixture", {})
        teams = item.get("teams", {})
        goals = item.get("goals", {})
        league = item.get("league", {})
        status = fixture.get("status", {}).get("short", "NS")
        rows.append(
            {
                "sport": "football",
                "competition": league.get("name"),
                "competition_code": str(league.get("id")),
                "season": str(league.get("season")),
                "kickoff": fixture.get("date"),
                "home_team": teams.get("home", {}).get("name"),
                "away_team": teams.get("away", {}).get("name"),
                "home_goals": goals.get("home"),
                "away_goals": goals.get("away"),
                "status": "finished" if status in {"FT", "AET", "PEN"} else "scheduled",
                "external_id": str(fixture.get("id")),
                "source": "api-football",
            }
        )
    frame = pd.DataFrame(rows)
    if not frame.empty:
        frame["kickoff"] = pd.to_datetime(frame["kickoff"], utc=True, errors="coerce")
    return frame
