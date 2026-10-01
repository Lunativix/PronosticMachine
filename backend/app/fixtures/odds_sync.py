"""Odds for scheduled fixtures. Nothing is stored when the odds provider is not configured."""

from __future__ import annotations

from app.core.config import Settings
from app.data.providers.base import ProviderDisabled
from app.data.providers.odds_api import TheOddsApiProvider


class OddsSyncService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def fetch(self) -> dict[str, object]:
        if not self.settings.odds_api_key:
            raise ProviderDisabled(
                "ODDS_API_KEY is empty. Upcoming odds were not collected and no price was invented."
            )
        frame = TheOddsApiProvider(self.settings).load()
        return {"source": "the-odds-api", "rows": int(len(frame)), "records": frame.to_dict(orient="records")}
