"""Discover competitions the configured provider actually exposes. Nothing is invented."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.base import utcnow
from app.fixtures.providers.base import BaseFixtureProvider, NormalizedCompetition
from app.models import Competition, Season, Sport
from app.services.import_service import _get_or_create_sport

TIER_RE = re.compile(r"(?:^|\.)(?:w\.)?([1-4])$")
AGE_RE = re.compile(r"\bu(1[7-9]|2[0-3])\b", re.I)

CONTINENTS = {
    "england": "Europe",
    "france": "Europe",
    "spain": "Europe",
    "italy": "Europe",
    "germany": "Europe",
    "netherlands": "Europe",
    "portugal": "Europe",
    "scotland": "Europe",
    "turkey": "Europe",
    "belgium": "Europe",
    "usa": "North America",
    "united states": "North America",
    "mexico": "North America",
    "canada": "North America",
    "brazil": "South America",
    "argentina": "South America",
    "saudi arabia": "Asia",
    "japan": "Asia",
    "australia": "Oceania",
    "china": "Asia",
}


@dataclass(frozen=True)
class StoredDiscovery:
    found: int
    inserted: int
    updated: int


def season_label(year: int | None, start: datetime | None, end: datetime | None) -> str:
    """Label the season from the provider dates. The calendar year is never assumed."""
    if start and end and start.year != end.year:
        return f"{start.year}/{str(end.year)[-2:]}"
    if year:
        return str(year)
    if start:
        return str(start.year)
    return ""


def competition_type(slug: str, name: str) -> str:
    text = f"{slug} {name}".lower()
    slug_l = slug.lower()
    if AGE_RE.search(slug_l.replace(".", " ")):
        return "YOUTH"
    if "friendly" in text:
        return "FRIENDLY"
    if "playoff" in text or "relegation" in text or "barrage" in text:
        return "PLAYOFF"
    if "qual" in text:
        return "QUALIFICATION"
    if "conference" in text or "europa.conf" in slug_l:
        return "CONFERENCE_LEAGUE"
    if "europa" in text and "conference" not in text:
        return "EUROPA_LEAGUE"
    if "champions" in text:
        return "CHAMPIONS_LEAGUE"
    if any(token in text for token in ("cup", "copa", "coupe", "pokal", "taca", "trophy")):
        return "CUP"
    if slug_l.startswith(("fifa.", "uefa.", "caf.", "afc.", "concacaf.", "conmebol.", "global.")):
        return "INTERNATIONAL"
    return "LEAGUE"


def age_category(slug: str) -> str:
    match = AGE_RE.search(slug.lower().replace(".", " "))
    if match:
        return f"U{match.group(1)}"
    return "senior"


def continent_for(country_slug: str, competition_slug: str) -> str:
    slug = competition_slug.lower()
    if slug.startswith(("uefa.", "eng.", "fra.", "esp.", "ita.", "ger.", "ned.", "por.", "sco.", "tur.")):
        return "Europe"
    if slug.startswith(("concacaf.", "usa.", "mex.")):
        return "North America"
    if slug.startswith("conmebol."):
        return "South America"
    if slug.startswith("caf."):
        return "Africa"
    if slug.startswith("afc."):
        return "Asia"
    if slug.startswith(("aus.", "ofc.")):
        return "Oceania"
    return CONTINENTS.get(country_slug.lower(), "")


def tier_for(slug: str) -> int | None:
    match = TIER_RE.search(slug.lower())
    if not match:
        return None
    return int(match.group(1))


class CompetitionDiscoveryService:
    def __init__(self, session: Session, provider: BaseFixtureProvider) -> None:
        self.session = session
        self.provider = provider

    def sync(self) -> StoredDiscovery:
        if not hasattr(self.provider, "discover_competitions"):
            return StoredDiscovery(0, 0, 0)
        found = self.provider.discover_competitions()
        sport = _get_or_create_sport(self.session)
        inserted = updated = 0
        for item in found:
            outcome = self._upsert(sport, item)
            inserted += outcome == "inserted"
            updated += outcome == "updated"
        self.session.commit()
        return StoredDiscovery(len(found), inserted, updated)

    def _upsert(self, sport: Sport, item: NormalizedCompetition) -> str:
        row = self.session.scalar(
            select(Competition).where(Competition.sport_id == sport.id, Competition.code == item.provider_competition_id)
        )
        created = row is None
        if row is None:
            row = Competition(sport_id=sport.id, code=item.provider_competition_id[:40], name=item.name)
            self.session.add(row)
        row.name = item.name
        row.country = item.country or None
        row.provider = item.provider
        row.provider_competition_id = item.provider_competition_id
        row.normalized_name = item.normalized_name
        row.country_code = item.country_code or None
        row.continent = item.continent or None
        row.gender = item.gender
        row.age_category = item.age_category
        row.competition_type = item.competition_type
        row.tier = item.tier
        row.current_season = item.season or None
        row.season_start = item.season_start
        row.season_end = item.season_end
        row.active = True
        row.source = item.provider
        row.last_sync = utcnow()
        self.session.flush()
        if item.season:
            season = self.session.scalar(
                select(Season).where(Season.competition_id == row.id, Season.name == item.season)
            )
            if season is None:
                self.session.add(
                    Season(
                        competition_id=row.id,
                        name=item.season,
                        start_date=item.season_start,
                        end_date=item.season_end,
                    )
                )
            else:
                season.start_date = item.season_start
                season.end_date = item.season_end
        return "inserted" if created else "updated"


def parse_provider_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
