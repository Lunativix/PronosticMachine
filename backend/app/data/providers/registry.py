"""Provider selection from configuration."""

from __future__ import annotations

from pathlib import Path

from app.core.config import Settings
from app.data.providers.api_football import ApiFootballProvider
from app.data.providers.base import BaseDataProvider, ProviderDisabled
from app.data.providers.csv_provider import CsvFootballProvider
from app.data.providers.json_provider import JsonFootballProvider
from app.data.providers.odds_api import TheOddsApiProvider


def football_provider(
    settings: Settings,
    path: Path | None = None,
    league: int = 39,
    season: int = 2024,
) -> BaseDataProvider:
    if path is not None:
        if path.suffix.lower() == ".json":
            return JsonFootballProvider(path)
        return CsvFootballProvider(path)
    if settings.data_provider.lower() == "api_football":
        return ApiFootballProvider(settings, league=league, season=season)
    raise ProviderDisabled("No file path was provided and DATA_PROVIDER is not an API.")


def odds_provider(settings: Settings, sport_key: str = "soccer_epl") -> TheOddsApiProvider:
    return TheOddsApiProvider(settings, sport_key=sport_key)
