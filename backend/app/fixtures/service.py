"""Store upcoming fixtures, keep schedule history, and never invent a match."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.base import utcnow
from app.fixtures.discovery import CompetitionDiscoveryService
from app.fixtures.providers.base import BaseFixtureProvider, NormalizedCompetition, NormalizedFixture, ProviderNotConfigured
from app.fixtures.teams import TeamNeedsReview, TeamResolver
from app.fixtures.window import PARIS, get_upcoming_window
from app.models import Bookmaker, Competition, FixtureChange, FixtureSyncRun, Match, Odds, Season, Sport
from app.services.import_service import _get_or_create_sport

LOGGER = logging.getLogger(__name__)


class UpcomingMatchesService:
    def __init__(self, session: Session, provider: BaseFixtureProvider, settings: Settings | None = None) -> None:
        self.session = session
        self.provider = provider
        self.settings = settings or get_settings()

    def sync(self, days: int = 14, competition: str | None = None, now: datetime | None = None) -> FixtureSyncRun:
        start, end = get_upcoming_window(now, days)
        run = FixtureSyncRun(
            started_at=utcnow(),
            status="running",
            window_start=start.astimezone(timezone.utc),
            window_end=end.astimezone(timezone.utc),
            provider=self.provider.name,
            errors=[],
        )
        self.session.add(run)
        self.session.flush()
        errors: list[dict[str, str]] = []
        leagues: list[NormalizedCompetition] = []
        fixtures: list[NormalizedFixture] = []
        try:
            if competition is None:
                CompetitionDiscoveryService(self.session, self.provider).sync()
            leagues = self._provider_leagues()
            if self.provider.name == "espn":
                fixtures = self.provider.get_upcoming_matches(start, end, competition, leagues=leagues)
            else:
                fixtures = self.provider.get_upcoming_matches(start, end, competition)
        except ProviderNotConfigured as exc:
            errors.append({"provider": self.provider.name, "competition": "", "endpoint": "", "status": "", "message": str(exc)})
            fixtures = []
        except Exception as exc:
            errors.append({"provider": self.provider.name, "competition": "", "endpoint": "", "status": "", "message": str(exc)})
            fixtures = []
            LOGGER.warning("fixture provider failed", extra={"context": {"provider": self.provider.name, "error": str(exc)}})
        sport = _get_or_create_sport(self.session)
        resolver = TeamResolver(self.session, sport)
        inserted = updated = unchanged = rescheduled = cancelled = 0
        seen: set[str] = set()
        for fixture in fixtures:
            if fixture.provider_match_id in seen:
                continue
            seen.add(fixture.provider_match_id)
            try:
                outcome = self._upsert(sport, resolver, fixture)
            except TeamNeedsReview as exc:
                errors.append(
                    {
                        "provider": fixture.provider,
                        "competition": fixture.competition_name,
                        "endpoint": fixture.competition_code,
                        "status": "NEEDS_REVIEW",
                        "message": f"Ambiguous team: {exc}",
                    }
                )
                continue
            inserted += outcome == "inserted"
            updated += outcome == "updated"
            unchanged += outcome == "unchanged"
            rescheduled += outcome == "rescheduled"
            cancelled += outcome == "cancelled"
        self._mark_coverage(leagues if "leagues" in locals() else [], {item.competition_code for item in fixtures})
        run.matches_found = len(seen)
        run.matches_inserted = inserted
        run.matches_updated = updated
        run.matches_unchanged = unchanged
        run.rescheduled = rescheduled
        run.cancelled = cancelled
        run.errors = errors
        run.finished_at = utcnow()
        run.status = "error" if errors and not seen else "ok"
        run.report = render_report(run, competition)
        self.session.commit()
        LOGGER.info(run.report)
        return run

    def _provider_leagues(self) -> list[NormalizedCompetition]:
        rows = self.session.scalars(
            select(Competition).where(Competition.source == self.provider.name, Competition.active.is_(True))
        ).all()
        return [
            NormalizedCompetition(
                provider=row.source or self.provider.name,
                provider_competition_id=row.provider_competition_id or row.code,
                name=row.name,
                normalized_name=row.normalized_name or row.name.casefold(),
                country=row.country or "",
                country_code=row.country_code or "",
                continent=row.continent or "",
                gender=row.gender or "",
                age_category=row.age_category or "senior",
                competition_type=row.competition_type or "OTHER",
                tier=row.tier,
                season=row.current_season or "",
                season_start=row.season_start,
                season_end=row.season_end,
            )
            for row in rows
        ]

    def _mark_coverage(self, leagues: list[NormalizedCompetition], codes_with_fixtures: set[str]) -> None:
        if not leagues:
            return
        rows = self.session.scalars(select(Competition).where(Competition.source == self.provider.name)).all()
        now = utcnow()
        for row in rows:
            code = row.provider_competition_id or row.code
            row.fixtures_available = code in codes_with_fixtures
            row.last_sync = now
            row.odds_available = _competition_has_odds(self.session, row.id)

    def _upsert(self, sport: Sport, resolver: TeamResolver, fixture: NormalizedFixture) -> str:
        competition = _competition(self.session, sport, fixture)
        season = _season(self.session, competition, fixture.season)
        home = resolver.resolve(fixture.provider, fixture.home_provider_id, fixture.home_name, fixture.home_logo)
        away = resolver.resolve(fixture.provider, fixture.away_provider_id, fixture.away_name, fixture.away_logo)
        source = fixture.provider
        existing = self.session.scalar(
            select(Match).where(Match.source == source, Match.external_id == fixture.provider_match_id)
        )
        if existing is None:
            existing = _cross_source_match(self.session, competition.id, home.id, away.id, fixture.kickoff_utc)
        local = fixture.kickoff_utc.astimezone(PARIS).isoformat()
        now = utcnow()
        if existing is None:
            self.session.add(
                Match(
                    competition_id=competition.id,
                    season_id=season.id,
                    kickoff_at=fixture.kickoff_utc,
                    scheduled_at_local=local,
                    home_team_id=home.id,
                    away_team_id=away.id,
                    home_goals=fixture.home_goals,
                    away_goals=fixture.away_goals,
                    status=fixture.status,
                    source=source,
                    external_id=fixture.provider_match_id,
                    venue=fixture.venue,
                    referee=fixture.referee,
                    round_name=fixture.round_name,
                    matchday=fixture.matchday,
                    first_seen_at=now,
                    last_seen_at=now,
                    source_updated_at=now,
                    analysis_state="FIXTURE_IMPORTED",
                    quality="valid",
                    source_priority=1.0,
                )
            )
            self.session.flush()
            created = self.session.scalar(select(Match).where(Match.source == source, Match.external_id == fixture.provider_match_id))
            _store_quotes(self.session, created, fixture)
            return "inserted"
        changed = False
        outcome = "unchanged"
        if abs((_aware(existing.kickoff_at) - fixture.kickoff_utc).total_seconds()) >= 60:
            self.session.add(
                FixtureChange(
                    match_id=existing.id,
                    old_datetime=existing.kickoff_at,
                    new_datetime=fixture.kickoff_utc,
                    old_status=existing.status,
                    new_status=fixture.status,
                    source=source,
                )
            )
            existing.kickoff_at = fixture.kickoff_utc
            existing.scheduled_at_local = local
            changed = True
            outcome = "rescheduled"
        if existing.status != fixture.status:
            if outcome != "rescheduled":
                self.session.add(
                    FixtureChange(
                        match_id=existing.id,
                        old_datetime=existing.kickoff_at,
                        new_datetime=fixture.kickoff_utc,
                        old_status=existing.status,
                        new_status=fixture.status,
                        source=source,
                    )
                )
            existing.status = fixture.status
            changed = True
            outcome = "cancelled" if fixture.status == "CANCELLED" else "updated" if outcome == "unchanged" else outcome
        if fixture.status == "FINISHED" and fixture.home_goals is not None:
            existing.home_goals = fixture.home_goals
            existing.away_goals = fixture.away_goals
            changed = True
        existing.last_seen_at = now
        existing.source_updated_at = now
        existing.venue = fixture.venue or existing.venue
        _store_quotes(self.session, existing, fixture)
        if not changed:
            return "unchanged"
        return outcome


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def render_report(run: FixtureSyncRun, competition: str | None) -> str:
    duration = 0.0
    if run.finished_at and run.started_at:
        duration = (_aware(run.finished_at) - _aware(run.started_at)).total_seconds()
    lines = [
        "FIXTURE SYNC",
        f"Start: {run.started_at.isoformat()}",
        f"End: {run.finished_at.isoformat() if run.finished_at else ''}",
        f"Competitions: {competition or 'configured'}",
        f"Matches found: {run.matches_found}",
        f"Inserted: {run.matches_inserted}",
        f"Updated: {run.matches_updated}",
        f"Unchanged: {run.matches_unchanged}",
        f"Rescheduled: {run.rescheduled}",
        f"Cancelled: {run.cancelled}",
        f"Errors: {len(run.errors or [])}",
        f"Duration: {duration:.2f} seconds",
    ]
    for error in run.errors or []:
        lines.append(
            f"ERROR provider={error.get('provider')} competition={error.get('competition')} "
            f"endpoint={error.get('endpoint')} status={error.get('status')} message={error.get('message')}"
        )
    return "\n".join(lines)


def _competition(session: Session, sport: Sport, fixture: NormalizedFixture) -> Competition:
    row = session.scalar(
        select(Competition).where(Competition.sport_id == sport.id, Competition.code == fixture.competition_code)
    )
    if row is None:
        row = Competition(
            sport_id=sport.id,
            code=fixture.competition_code,
            name=fixture.competition_name,
            country=fixture.country or None,
        )
        session.add(row)
        session.flush()
    return row


def _season(session: Session, competition: Competition, name: str) -> Season:
    row = session.scalar(select(Season).where(Season.competition_id == competition.id, Season.name == name))
    if row is None:
        row = Season(competition_id=competition.id, name=name or "unknown")
        session.add(row)
        session.flush()
    return row


def _cross_source_match(session: Session, competition_id: int, home_id: int, away_id: int, kickoff: datetime) -> Match | None:
    low = kickoff - timedelta(hours=3)
    high = kickoff + timedelta(hours=3)
    rows = session.scalars(
        select(Match).where(
            Match.competition_id == competition_id,
            Match.home_team_id == home_id,
            Match.away_team_id == away_id,
            Match.kickoff_at >= low,
            Match.kickoff_at <= high,
        )
    ).all()
    if len(rows) == 1:
        return rows[0]
    return None


def _store_quotes(session: Session, match: Match | None, fixture: NormalizedFixture) -> None:
    if match is None:
        return
    now = utcnow()
    for quote in fixture.odds:
        price = quote.get("price")
        market = str(quote.get("market") or "")
        selection = str(quote.get("selection") or "")
        if not isinstance(price, (int, float)) or float(price) <= 1 or not market or not selection:
            continue
        code = str(quote.get("bookmaker") or fixture.provider).casefold().replace(" ", "-")
        bookmaker = session.scalar(select(Bookmaker).where(Bookmaker.code == code))
        if bookmaker is None:
            bookmaker = Bookmaker(code=code, name=str(quote.get("bookmaker") or fixture.provider))
            session.add(bookmaker)
            session.flush()
        latest = session.scalar(
            select(Odds)
            .where(Odds.match_id == match.id, Odds.bookmaker_id == bookmaker.id, Odds.market == market, Odds.selection == selection)
            .order_by(Odds.captured_at.desc())
        )
        if latest is not None and latest.price is not None and abs(float(latest.price) - float(price)) < 1e-6:
            continue
        session.add(
            Odds(
                match_id=match.id,
                bookmaker_id=bookmaker.id,
                market=market,
                selection=selection,
                price=float(price),
                captured_at=now,
                status="active",
                source=fixture.provider,
            )
        )


def _competition_has_odds(session: Session, competition_id: int) -> bool:
    match_ids = select(Match.id).where(Match.competition_id == competition_id)
    return session.scalar(select(Odds.id).where(Odds.match_id.in_(match_ids)).limit(1)) is not None


def upcoming_query(
    session: Session,
    start: datetime,
    end: datetime,
    competition: str | None,
    status: str | None,
    competition_ids: list[int] | None = None,
):
    statement = select(Match).where(Match.kickoff_at >= start.astimezone(timezone.utc), Match.kickoff_at <= end.astimezone(timezone.utc))
    if status:
        statement = statement.where(func.lower(Match.status) == status.lower())
    if competition_ids:
        statement = statement.where(Match.competition_id.in_(competition_ids))
    if competition:
        wanted = competition.casefold()
        statement = statement.join(Competition, Competition.id == Match.competition_id).where(
            or_(func.lower(Competition.code) == wanted, func.lower(Competition.name) == wanted)
        )
    return session.scalars(statement.order_by(Match.kickoff_at)).all()


DISPLAY_NAMES = {
    "uefa.champions": "Ligue des champions",
    "uefa.champions_qual": "Ligue des champions, qualifications",
    "uefa.europa": "Ligue Europa",
    "uefa.europa.conf": "Ligue Europa Conférence",
    "uefa.nations": "Ligue des nations",
    "uefa.w.nations": "Ligue des nations féminine",
    "uefa.wchampions": "Ligue des champions féminine",
    "concacaf.nations.league": "Ligue des nations CONCACAF",
}


def competitions_in_window(session: Session, start: datetime, end: datetime) -> list[dict[str, object]]:
    """Every discovered competition, with the real number of fixtures in the window."""
    counts = dict(
        session.execute(
            select(Match.competition_id, func.count(Match.id))
            .where(Match.kickoff_at >= start.astimezone(timezone.utc), Match.kickoff_at <= end.astimezone(timezone.utc))
            .group_by(Match.competition_id)
        ).all()
    )
    rows = session.scalars(select(Competition).where(Competition.source.is_not(None), Competition.source != "")).all()
    items = []
    for row in rows:
        code = row.provider_competition_id or row.code
        items.append(
            {
                "id": row.id,
                "name": row.name,
                "display_name": DISPLAY_NAMES.get(code, row.name),
                "country": row.country or "International",
                "code": code,
                "matches": int(counts.get(row.id, 0)),
            }
        )
    items.sort(key=lambda item: (-int(item["matches"]), str(item["display_name"]).casefold()))
    return items
