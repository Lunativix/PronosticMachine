"""The Odds API adapter. It stays idle unless ODDS_API_KEY is set."""

from __future__ import annotations

import pandas as pd

from app.core.config import Settings
from app.data.providers.base import OddsDataProvider, ProviderDisabled


class TheOddsApiProvider(OddsDataProvider):
    name = "the_odds_api"

    def __init__(self, settings: Settings, sport_key: str = "soccer_epl") -> None:
        self.settings = settings
        self.sport_key = sport_key

    def load(self) -> pd.DataFrame:
        if not self.settings.odds_api_key:
            raise ProviderDisabled("ODDS_API_KEY is empty. Odds will come from imported files.")
        import httpx

        response = httpx.get(
            f"{self.settings.odds_api_base_url}/sports/{self.sport_key}/odds",
            params={
                "apiKey": self.settings.odds_api_key,
                "regions": "eu",
                "markets": "h2h",
                "oddsFormat": "decimal",
            },
            timeout=30.0,
        )
        response.raise_for_status()
        return _normalize(response.json())


def _normalize(payload: list[dict]) -> pd.DataFrame:
    rows = []
    for event in payload:
        for bookmaker in event.get("bookmakers", []):
            for market in bookmaker.get("markets", []):
                prices = {item.get("name"): item.get("price") for item in market.get("outcomes", [])}
                rows.append(
                    {
                        "external_id": event.get("id"),
                        "kickoff": event.get("commence_time"),
                        "home_team": event.get("home_team"),
                        "away_team": event.get("away_team"),
                        "bookmaker": bookmaker.get("key"),
                        "market": "1X2",
                        "odds_home": prices.get(event.get("home_team")),
                        "odds_away": prices.get(event.get("away_team")),
                        "odds_draw": prices.get("Draw"),
                        "odds_timestamp": bookmaker.get("last_update") or event.get("commence_time"),
                        "source": "the-odds-api",
                    }
                )
    frame = pd.DataFrame(rows)
    if not frame.empty:
        frame["kickoff"] = pd.to_datetime(frame["kickoff"], utc=True, errors="coerce")
        frame["odds_timestamp"] = pd.to_datetime(frame["odds_timestamp"], utc=True, errors="coerce")
    return frame
