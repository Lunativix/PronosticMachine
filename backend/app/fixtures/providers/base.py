"""Provider-neutral upcoming fixtures."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class NormalizedFixture:
    provider: str
    provider_match_id: str
    competition_code: str
    competition_name: str
    country: str
    season: str
    home_name: str
    away_name: str
    home_provider_id: str
    away_provider_id: str
    kickoff_utc: datetime
    status: str
    home_goals: int | None = None
    away_goals: int | None = None
    venue: str | None = None
    referee: str | None = None
    round_name: str | None = None
    matchday: int | None = None
    home_logo: str | None = None
    away_logo: str | None = None
    odds: list[dict[str, object]] = field(default_factory=list)


@dataclass(frozen=True)
class NormalizedCompetition:
    provider: str
    provider_competition_id: str
    name: str
    normalized_name: str
    country: str
    country_code: str
    continent: str
    gender: str
    age_category: str
    competition_type: str
    tier: int | None
    season: str
    season_start: datetime | None
    season_end: datetime | None


class ProviderNotConfigured(RuntimeError):
    """The selected fixture provider has no credentials."""


class BaseFixtureProvider(ABC):
    name: str

    def discover_competitions(self) -> list[NormalizedCompetition]:
        return []

    @abstractmethod
    def get_upcoming_matches(
        self,
        start_date: datetime,
        end_date: datetime,
        competition: str | None = None,
    ) -> list[NormalizedFixture]:
        raise NotImplementedError
