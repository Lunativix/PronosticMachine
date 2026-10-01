"""Competition discovery uses only what the provider returns."""

from datetime import datetime, timezone

from app.fixtures.discovery import CompetitionDiscoveryService, competition_type, season_label
from app.fixtures.providers.base import BaseFixtureProvider, NormalizedCompetition, NormalizedFixture
from app.models import Competition


class CatalogProvider(BaseFixtureProvider):
    name = "espn"

    def __init__(self, rows: list[NormalizedCompetition]) -> None:
        self.rows = rows

    def discover_competitions(self) -> list[NormalizedCompetition]:
        return self.rows

    def get_upcoming_matches(self, start_date, end_date, competition=None, leagues=None):
        return []


def _row(slug: str, name: str, season: str = "2025/26") -> NormalizedCompetition:
    return NormalizedCompetition(
        provider="espn",
        provider_competition_id=slug,
        name=name,
        normalized_name=name.casefold(),
        country="France",
        country_code="FRA",
        continent="Europe",
        gender="men",
        age_category="senior",
        competition_type=competition_type(slug, name),
        tier=1,
        season=season,
        season_start=datetime(2025, 8, 1, tzinfo=timezone.utc),
        season_end=datetime(2026, 5, 31, tzinfo=timezone.utc),
    )


def test_season_label_comes_from_provider_dates() -> None:
    start = datetime(2025, 8, 1, tzinfo=timezone.utc)
    end = datetime(2026, 5, 31, tzinfo=timezone.utc)
    assert season_label(2025, start, end) == "2025/26"
    assert season_label(2024, datetime(2024, 2, 1, tzinfo=timezone.utc), datetime(2024, 12, 1, tzinfo=timezone.utc)) == "2024"


def test_competition_types() -> None:
    assert competition_type("fra.1", "Ligue 1") == "LEAGUE"
    assert competition_type("fra.coupe_de_france", "Coupe de France") == "CUP"
    assert competition_type("uefa.champions", "UEFA Champions League") == "CHAMPIONS_LEAGUE"
    assert competition_type("uefa.champions_qual", "Champions League Qualifying") == "QUALIFICATION"
    assert competition_type("fifa.world.u20", "U-20 World Cup") == "YOUTH"
    assert competition_type("eng.w.1", "Women's Super League") == "LEAGUE"


def test_discovery_stores_only_provider_rows(session) -> None:
    provider = CatalogProvider([_row("fra.1", "Ligue 1"), _row("bra.1", "Brasileirão")])
    result = CompetitionDiscoveryService(session, provider).sync()
    assert result.found == 2
    stored = session.query(Competition).filter(Competition.source == "espn").all()
    assert {row.provider_competition_id for row in stored} == {"fra.1", "bra.1"}
    assert all(row.current_season == "2025/26" for row in stored)


def test_second_discovery_does_not_duplicate(session) -> None:
    provider = CatalogProvider([_row("fra.1", "Ligue 1")])
    CompetitionDiscoveryService(session, provider).sync()
    CompetitionDiscoveryService(session, provider).sync()
    assert session.query(Competition).filter(Competition.provider_competition_id == "fra.1").count() == 1


def test_fixture_competitions_endpoint(client) -> None:
    response = client.get("/fixtures/competitions?days=14")
    assert response.status_code == 200
    payload = response.json()
    assert isinstance(payload["items"], list)
    assert payload["total"] == len(payload["items"])


def test_coverage_pagination(client) -> None:
    response = client.get("/competitions/coverage?limit=1&offset=0")
    assert response.status_code == 200
    payload = response.json()
    assert payload["limit"] == 1
    assert "total_discovered" in payload
    assert len(payload["items"]) <= 1
