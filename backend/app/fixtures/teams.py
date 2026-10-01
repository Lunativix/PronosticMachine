"""Resolve provider clubs to internal teams. Ambiguous links are not merged."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Sport, Team, TeamAlias, TeamProviderLink
from app.services.import_service import canonical_name


class TeamNeedsReview(RuntimeError):
    pass


class TeamResolver:
    def __init__(self, session: Session, sport: Sport) -> None:
        self.session = session
        self.sport = sport

    def resolve(self, provider: str, provider_team_id: str, name: str, logo: str | None = None) -> Team:
        link = self.session.scalar(
            select(TeamProviderLink).where(
                TeamProviderLink.provider == provider,
                TeamProviderLink.provider_team_id == provider_team_id,
            )
        )
        if link is not None:
            if link.review_status == "NEEDS_REVIEW":
                raise TeamNeedsReview(name)
            team = self.session.get(Team, link.team_id)
            if team is None:
                raise TeamNeedsReview(name)
            if logo and not team.logo_url:
                team.logo_url = logo
            return team
        key = canonical_name(name)
        alias = self.session.scalar(select(TeamAlias).where(TeamAlias.alias == key))
        team = self.session.get(Team, alias.team_id) if alias is not None else None
        if team is None:
            team = self.session.scalar(
                select(Team).where(Team.sport_id == self.sport.id, Team.canonical_name == key)
            )
        if team is None:
            team = Team(sport_id=self.sport.id, name=name.strip(), canonical_name=key, country=None, logo_url=logo)
            self.session.add(team)
            self.session.flush()
            self.session.add(TeamAlias(team_id=team.id, alias=key, source=provider))
        existing_for_team = self.session.scalar(
            select(TeamProviderLink).where(
                TeamProviderLink.team_id == team.id,
                TeamProviderLink.provider == provider,
                TeamProviderLink.provider_team_id != provider_team_id,
            )
        )
        if existing_for_team is not None and canonical_name(existing_for_team.provider_name) != key:
            self.session.add(
                TeamProviderLink(
                    team_id=team.id,
                    provider=provider,
                    provider_team_id=provider_team_id,
                    provider_name=name.strip(),
                    review_status="NEEDS_REVIEW",
                )
            )
            self.session.flush()
            raise TeamNeedsReview(name)
        self.session.add(
            TeamProviderLink(
                team_id=team.id,
                provider=provider,
                provider_team_id=provider_team_id,
                provider_name=name.strip(),
                review_status="confirmed",
            )
        )
        self.session.flush()
        return team
