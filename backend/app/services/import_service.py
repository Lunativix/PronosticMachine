"""Persist validated matches, statistics, and append-only odds."""

from __future__ import annotations

from datetime import timedelta

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.data.quality import DataQualityReport, validate_matches
from app.db.base import utcnow
from app.models import (
    Bookmaker,
    Competition,
    DataQualityReport as DataQualityReportRow,
    Injury,
    Match,
    Odds,
    Player,
    Season,
    Sport,
    Team,
    TeamAlias,
    TeamStatistic,
)


def canonical_name(value: str) -> str:
    return " ".join(value.strip().casefold().split())


def import_frame(
    session: Session,
    frame: pd.DataFrame,
    *,
    source: str,
    aliases: dict[str, str] | None = None,
) -> DataQualityReport:
    prepared = _apply_aliases(frame, aliases or {})
    valid, report = validate_matches(prepared)
    _store_report(session, source, report)
    if valid.empty:
        session.commit()
        return report
    sport = _get_or_create_sport(session)
    for record in valid.itertuples(index=False):
        competition = _get_or_create_competition(session, sport, record)
        season = _get_or_create_season(session, competition, str(record.season))
        home = _get_or_create_team(session, sport.id, str(record.home_team))
        away = _get_or_create_team(session, sport.id, str(record.away_team))
        match = _upsert_match(session, record, competition.id, season.id, home.id, away.id, source)
        _store_team_stats(session, match, home.id, away.id, record, source)
        _store_odds(session, match, record, source)
    _store_optional_entities(session, frame, sport.id, source)
    session.commit()
    return report


def _apply_aliases(frame: pd.DataFrame, aliases: dict[str, str]) -> pd.DataFrame:
    if not aliases:
        return frame
    work = frame.copy()
    mapping = {canonical_name(key): value for key, value in aliases.items()}
    for column in ("home_team", "away_team"):
        if column in work.columns:
            work[column] = work[column].map(lambda name: mapping.get(canonical_name(str(name)), name))
    return work


def _store_report(session: Session, source: str, report: DataQualityReport) -> None:
    session.add(
        DataQualityReportRow(
            source=source,
            records_total=report.records_total,
            records_valid=report.records_valid,
            records_invalid=report.records_invalid,
            missing_values=report.missing_values,
            duplicates=report.duplicates,
            future_leakage=report.future_leakage,
            warnings=report.warnings,
            errors=report.errors,
        )
    )


def _get_or_create_sport(session: Session) -> Sport:
    sport = session.scalar(select(Sport).where(Sport.code == "football"))
    if sport is None:
        sport = Sport(code="football", name="Football")
        session.add(sport)
        session.flush()
    return sport


def _get_or_create_competition(session: Session, sport: Sport, record: object) -> Competition:
    code = str(getattr(record, "competition_code", getattr(record, "competition")))
    name = str(getattr(record, "competition"))
    row = session.scalar(select(Competition).where(Competition.sport_id == sport.id, Competition.code == code))
    if row is None:
        row = Competition(sport_id=sport.id, code=code, name=name, country=None)
        session.add(row)
        session.flush()
    return row


def _get_or_create_season(session: Session, competition: Competition, name: str) -> Season:
    row = session.scalar(select(Season).where(Season.competition_id == competition.id, Season.name == name))
    if row is None:
        row = Season(competition_id=competition.id, name=name)
        session.add(row)
        session.flush()
    return row


def _get_or_create_team(session: Session, sport_id: int, name: str) -> Team:
    key = canonical_name(name)
    alias = session.scalar(select(TeamAlias).where(TeamAlias.alias == key))
    if alias is not None:
        return session.get(Team, alias.team_id)
    team = session.scalar(select(Team).where(Team.sport_id == sport_id, Team.canonical_name == key))
    if team is None:
        team = Team(sport_id=sport_id, name=name.strip(), canonical_name=key)
        session.add(team)
        session.flush()
        session.add(TeamAlias(team_id=team.id, alias=key, source="import"))
        session.flush()
    return team


def _upsert_match(session, record, competition_id, season_id, home_id, away_id, source) -> Match:
    kickoff = pd.Timestamp(record.kickoff).to_pydatetime()
    existing = session.scalar(
        select(Match).where(
            Match.competition_id == competition_id,
            Match.kickoff_at == kickoff,
            Match.home_team_id == home_id,
            Match.away_team_id == away_id,
            Match.source == source,
        )
    )
    home_goals = _none_if_na(getattr(record, "home_goals", None))
    away_goals = _none_if_na(getattr(record, "away_goals", None))
    status = str(getattr(record, "status", "finished" if home_goals is not None else "scheduled"))
    if existing is None:
        existing = Match(
            competition_id=competition_id,
            season_id=season_id,
            kickoff_at=kickoff,
            home_team_id=home_id,
            away_team_id=away_id,
            home_goals=None if home_goals is None else int(home_goals),
            away_goals=None if away_goals is None else int(away_goals),
            status=status,
            source=source,
            external_id=str(getattr(record, "external_id", "") or "") or None,
            quality="valid",
            source_priority=1.0,
        )
        session.add(existing)
        session.flush()
    return existing


def _store_team_stats(session, match: Match, home_id: int, away_id: int, record: object, source: str) -> None:
    for team_id, side in ((home_id, "home"), (away_id, "away")):
        payload = {
            "shots": _none_if_na(getattr(record, f"shots_{side}", None)),
            "shots_on_target": _none_if_na(getattr(record, f"sot_{side}", None)),
            "possession": _none_if_na(getattr(record, f"possession_{side}", None)),
            "corners": _none_if_na(getattr(record, f"corners_{side}", None)),
            "yellow_cards": _none_if_na(getattr(record, f"yellow_{side}", None)),
            "red_cards": _none_if_na(getattr(record, f"red_{side}", None)),
            "xg": _none_if_na(getattr(record, f"xg_{side}", None)),
            "xga": _none_if_na(getattr(record, f"xg_{'away' if side == 'home' else 'home'}", None)),
        }
        if all(value is None for value in payload.values()):
            continue
        exists = session.scalar(
            select(TeamStatistic).where(
                TeamStatistic.match_id == match.id,
                TeamStatistic.team_id == team_id,
                TeamStatistic.source == source,
            )
        )
        if exists is None:
            session.add(TeamStatistic(match_id=match.id, team_id=team_id, source=source, quality="valid", **payload))


def _store_odds(session, match: Match, record: object, source: str) -> None:
    prices = {
        "home": _none_if_na(getattr(record, "odds_home", None)),
        "draw": _none_if_na(getattr(record, "odds_draw", None)),
        "away": _none_if_na(getattr(record, "odds_away", None)),
    }
    if any(price is None for price in prices.values()):
        return
    code = str(getattr(record, "bookmaker", "market") or "market")
    bookmaker = session.scalar(select(Bookmaker).where(Bookmaker.code == code))
    if bookmaker is None:
        bookmaker = Bookmaker(code=code, name=code)
        session.add(bookmaker)
        session.flush()
    captured = getattr(record, "odds_timestamp", None)
    captured_at = pd.Timestamp(captured).to_pydatetime() if _none_if_na(captured) is not None else match.kickoff_at - timedelta(minutes=1)
    for selection, price in prices.items():
        exists = session.scalar(
            select(Odds).where(
                Odds.match_id == match.id,
                Odds.bookmaker_id == bookmaker.id,
                Odds.market == "1X2",
                Odds.selection == selection,
                Odds.captured_at == captured_at,
                Odds.status == "active",
            )
        )
        if exists is None:
            session.add(
                Odds(
                    match_id=match.id,
                    bookmaker_id=bookmaker.id,
                    market="1X2",
                    selection=selection,
                    price=float(price),
                    captured_at=captured_at,
                    status="active",
                    source=source,
                    quality="valid",
                    imported_at=utcnow(),
                )
            )


def _store_optional_entities(session: Session, frame: pd.DataFrame, sport_id: int, source: str) -> None:
    if "player_name" not in frame.columns:
        return
    for record in frame.itertuples(index=False):
        player_name = _none_if_na(getattr(record, "player_name", None))
        if player_name is None:
            continue
        team_name = _none_if_na(getattr(record, "player_team", None))
        team = _get_or_create_team(session, sport_id, str(team_name)) if team_name else None
        player = Player(team_id=None if team is None else team.id, name=str(player_name), source=source) if False else None
        existing = session.scalar(select(Player).where(Player.name == str(player_name)))
        if existing is None:
            existing = Player(team_id=None if team is None else team.id, name=str(player_name))
            session.add(existing)
            session.flush()
        if _none_if_na(getattr(record, "injury_status", None)) is not None:
            session.add(
                Injury(
                    player_id=existing.id,
                    team_id=None if team is None else team.id,
                    player_name=str(player_name),
                    status=str(getattr(record, "injury_status")),
                    reason=_none_if_na(getattr(record, "injury_reason", None)),
                    source=source,
                    quality="valid",
                )
            )


def _none_if_na(value: object) -> object | None:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except TypeError:
        return value
    return value
