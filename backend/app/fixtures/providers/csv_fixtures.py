"""User-supplied upcoming fixtures. The file must already contain real rows."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from app.fixtures.providers.base import BaseFixtureProvider, NormalizedFixture
from app.fixtures.window import in_window


class CsvFixtureProvider(BaseFixtureProvider):
    name = "csv"

    def __init__(self, path: Path) -> None:
        self.path = path

    def get_upcoming_matches(
        self,
        start_date: datetime,
        end_date: datetime,
        competition: str | None = None,
    ) -> list[NormalizedFixture]:
        frame = pd.read_csv(self.path)
        fixtures: list[NormalizedFixture] = []
        for record in frame.itertuples(index=False):
            name = str(getattr(record, "competition"))
            if competition and competition.lower() not in {name.lower(), str(getattr(record, "competition_code", "")).lower()}:
                continue
            kickoff = pd.Timestamp(getattr(record, "kickoff")).to_pydatetime()
            if kickoff.tzinfo is None:
                kickoff = kickoff.replace(tzinfo=timezone.utc)
            if not in_window(kickoff, start_date, end_date):
                continue
            fixtures.append(
                NormalizedFixture(
                    provider="csv",
                    provider_match_id=str(getattr(record, "provider_match_id")),
                    competition_code=str(getattr(record, "competition_code", name)),
                    competition_name=name,
                    country=str(getattr(record, "country", "") or ""),
                    season=str(getattr(record, "season")),
                    home_name=str(getattr(record, "home_team")),
                    away_name=str(getattr(record, "away_team")),
                    home_provider_id=str(getattr(record, "home_provider_id", getattr(record, "home_team"))),
                    away_provider_id=str(getattr(record, "away_provider_id", getattr(record, "away_team"))),
                    kickoff_utc=kickoff.astimezone(timezone.utc),
                    status=str(getattr(record, "status", "SCHEDULED")),
                    venue=_optional(record, "venue"),
                )
            )
        return fixtures


def _optional(record: object, name: str) -> str | None:
    if not hasattr(record, name):
        return None
    value = getattr(record, name)
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    return str(value)
