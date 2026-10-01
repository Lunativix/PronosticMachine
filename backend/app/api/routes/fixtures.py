"""Upcoming fixture endpoints."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.analysis.service import latest_snapshot
from app.db.session import get_db
from app.fixtures.providers.base import ProviderNotConfigured
from app.fixtures.scheduler import build_provider, next_run
from app.fixtures.service import UpcomingMatchesService, competitions_in_window, upcoming_query
from app.fixtures.window import PARIS, get_upcoming_window
from app.models import Competition, FixtureSyncRun, MarketAnalysis, Match, Team

router = APIRouter()
DISCLAIMER = "Les probabilités sont des estimations statistiques et ne garantissent aucun résultat."


@router.get("/fixtures/upcoming")
def list_upcoming(
    days: int = Query(60, ge=1, le=90),
    competition: str | None = None,
    status: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    team: str | None = None,
    q: str | None = None,
    competition_id: list[int] = Query(default=[]),
    view: str = Query("all", pattern="^(all|signals|no_signals)$"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> dict:
    start, end = get_upcoming_window(days=days)
    if date_from:
        start = date_from.astimezone(PARIS) if date_from.tzinfo else date_from.replace(tzinfo=PARIS)
    if date_to:
        end = date_to.astimezone(PARIS) if date_to.tzinfo else date_to.replace(tzinfo=PARIS)
    rows = upcoming_query(db, start, end, competition, status, competition_id or None)
    if team or q:
        needle = (q or team or "").casefold()
        rows = [row for row in rows if needle in _label(db, row).casefold()]
    if view in {"signals", "no_signals"}:
        signaled = _signaled_match_ids(db)
        rows = [row for row in rows if (row.id in signaled) is (view == "signals")]
    total = len(rows)
    page = rows[offset : offset + limit]
    return {
        "disclaimer": DISCLAIMER,
        "window": {"start": start.isoformat(), "end": end.isoformat()},
        "total": total,
        "limit": limit,
        "offset": offset,
        "matches": [_match(db, row) for row in page],
    }


@router.get("/fixtures/competitions")
def fixture_competitions(days: int = Query(60, ge=1, le=90), db: Session = Depends(get_db)) -> dict:
    start, end = get_upcoming_window(days=days)
    items = competitions_in_window(db, start, end)
    return {"disclaimer": DISCLAIMER, "total": len(items), "items": items}


@router.get("/fixtures/calendar")
def calendar(
    days: int = Query(60, ge=1, le=90),
    competition_id: list[int] = Query(default=[]),
    db: Session = Depends(get_db),
) -> dict:
    start, end = get_upcoming_window(days=days)
    rows = upcoming_query(db, start, end, None, None, competition_id or None)
    signaled = _signaled_match_ids(db)
    buckets: dict[str, dict[str, set[int] | int]] = {}
    for row in rows:
        local = row.scheduled_at_local or row.kickoff_at.isoformat()
        key = local[:10]
        bucket = buckets.setdefault(key, {"matches": 0, "competitions": set(), "signals": 0})
        bucket["matches"] = int(bucket["matches"]) + 1
        competitions = bucket["competitions"]
        assert isinstance(competitions, set)
        competitions.add(row.competition_id)
        if row.id in signaled:
            bucket["signals"] = int(bucket["signals"]) + 1
    days_out = []
    for key in sorted(buckets):
        bucket = buckets[key]
        competitions = bucket["competitions"]
        assert isinstance(competitions, set)
        days_out.append(
            {
                "date": key,
                "matches": bucket["matches"],
                "competitions": len(competitions),
                "signals": bucket["signals"],
                "propositions": bucket["signals"],
            }
        )
    return {"disclaimer": DISCLAIMER, "days": days_out}


@router.get("/competitions/coverage")
def coverage(
    q: str | None = None,
    country: str | None = None,
    continent: str | None = None,
    competition_type: str | None = None,
    gender: str | None = None,
    age_category: str | None = None,
    tier: int | None = None,
    season: str | None = None,
    fixtures_available: bool | None = None,
    odds_available: bool | None = None,
    sort: str = Query("country", pattern="^(name|country|fixtures|last_sync)$"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> dict:
    statement = select(Competition).where(Competition.source.is_not(None), Competition.source != "")
    if q:
        needle = f"%{q.casefold()}%"
        statement = statement.where(
            or_(func.lower(Competition.name).like(needle), func.lower(Competition.country).like(needle), func.lower(Competition.code).like(needle))
        )
    if country:
        statement = statement.where(func.lower(Competition.country) == country.casefold())
    if continent:
        statement = statement.where(func.lower(Competition.continent) == continent.casefold())
    if competition_type:
        statement = statement.where(Competition.competition_type == competition_type)
    if gender:
        statement = statement.where(Competition.gender == gender)
    if age_category:
        statement = statement.where(Competition.age_category == age_category)
    if tier is not None:
        statement = statement.where(Competition.tier == tier)
    if season:
        statement = statement.where(Competition.current_season == season)
    if fixtures_available is not None:
        statement = statement.where(Competition.fixtures_available.is_(fixtures_available))
    if odds_available is not None:
        statement = statement.where(Competition.odds_available.is_(odds_available))
    rows = db.scalars(statement).all()
    start, end = get_upcoming_window(days=14)
    counts = _fixture_counts(db, start, end)
    if sort == "name":
        rows.sort(key=lambda row: row.name.casefold())
    elif sort == "fixtures":
        rows.sort(key=lambda row: counts.get(row.id, 0), reverse=True)
    elif sort == "last_sync":
        rows.sort(key=lambda row: row.last_sync or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    else:
        rows.sort(key=lambda row: ((row.country or ""), row.name.casefold()))
    discovered = db.scalar(select(func.count()).select_from(Competition).where(Competition.source.is_not(None), Competition.source != "")) or 0
    with_fixtures = db.scalar(
        select(func.count()).select_from(Competition).where(Competition.source.is_not(None), Competition.source != "", Competition.fixtures_available.is_(True))
    ) or 0
    with_odds = db.scalar(
        select(func.count()).select_from(Competition).where(Competition.source.is_not(None), Competition.source != "", Competition.odds_available.is_(True))
    ) or 0
    active = db.scalar(
        select(func.count()).select_from(Competition).where(Competition.source.is_not(None), Competition.source != "", Competition.active.is_(True))
    ) or 0
    run = db.scalar(select(FixtureSyncRun).order_by(FixtureSyncRun.started_at.desc()))
    page = rows[offset : offset + limit]
    return {
        "disclaimer": DISCLAIMER,
        "total_discovered": int(discovered),
        "active": int(active),
        "with_fixtures": int(with_fixtures),
        "with_odds": int(with_odds),
        "filtered": len(rows),
        "limit": limit,
        "offset": offset,
        "last_sync": None if run is None or run.finished_at is None else run.finished_at.isoformat(),
        "sync_status": None if run is None else run.status,
        "items": [_competition_row(row, counts.get(row.id, 0)) for row in page],
    }


@router.get("/dashboard/overview")
def overview(db: Session = Depends(get_db)) -> dict:
    start, end = get_upcoming_window(days=14)
    matches = upcoming_query(db, start, end, None, None)
    discovered = db.scalar(select(func.count()).select_from(Competition).where(Competition.source.is_not(None), Competition.source != "")) or 0
    run = db.scalar(select(FixtureSyncRun).order_by(FixtureSyncRun.started_at.desc()))
    return {
        "disclaimer": DISCLAIMER,
        "matches": len(matches),
        "competitions": int(discovered),
        "signals": len(_signaled_match_ids(db) & {row.id for row in matches}),
        "sync_status": None if run is None else run.status,
        "last_sync": None if run is None or run.finished_at is None else run.finished_at.isoformat(),
        "syncing": bool(run and run.status == "running"),
    }


@router.post("/fixtures/sync")
def sync_now(days: int = 60, competition: str | None = None, db: Session = Depends(get_db)) -> dict:
    try:
        provider = build_provider()
    except ProviderNotConfigured as exc:
        raise HTTPException(400, str(exc)) from exc
    run = UpcomingMatchesService(db, provider).sync(days=days, competition=competition)
    return {"disclaimer": DISCLAIMER, **_run(run)}


@router.get("/fixtures/sync/status")
def sync_status(db: Session = Depends(get_db)) -> dict:
    run = db.scalar(select(FixtureSyncRun).order_by(FixtureSyncRun.started_at.desc()))
    return {"disclaimer": DISCLAIMER, "next_sync": next_run(), "last_sync": None if run is None else _run(run)}


def _run(run: FixtureSyncRun) -> dict:
    duration = None
    if run.finished_at:
        duration = (run.finished_at - run.started_at).total_seconds()
    return {
        "status": run.status,
        "last_sync": run.started_at.isoformat(),
        "finished_at": None if run.finished_at is None else run.finished_at.isoformat(),
        "duration": duration,
        "matches_found": run.matches_found,
        "matches_inserted": run.matches_inserted,
        "matches_updated": run.matches_updated,
        "matches_unchanged": run.matches_unchanged,
        "rescheduled": run.rescheduled,
        "cancelled": run.cancelled,
        "errors": run.errors,
        "report": run.report,
        "window": {
            "start": None if run.window_start is None else run.window_start.isoformat(),
            "end": None if run.window_end is None else run.window_end.isoformat(),
        },
    }


def _match(db: Session, row: Match) -> dict:
    home = db.get(Team, row.home_team_id)
    away = db.get(Team, row.away_team_id)
    competition = db.get(Competition, row.competition_id)
    return {
        "id": row.id,
        "provider_match_id": row.external_id,
        "competition": None if competition is None else competition.name,
        "home_team": None if home is None else home.name,
        "away_team": None if away is None else away.name,
        "scheduled_at_utc": row.kickoff_at.isoformat(),
        "scheduled_at_local": row.scheduled_at_local,
        "status": row.status,
        "venue": row.venue,
        "source": row.source,
        "last_seen_at": None if row.last_seen_at is None else row.last_seen_at.isoformat(),
        "analysis_state": row.analysis_state,
        "home_goals": row.home_goals,
        "away_goals": row.away_goals,
    }


def _signaled_match_ids(db: Session) -> set[int]:
    stamp = latest_snapshot(db)
    if stamp is None:
        return set()
    rows = db.scalars(
        select(MarketAnalysis.match_id).where(
            MarketAnalysis.created_at == stamp,
            MarketAnalysis.signal.notin_(["NO_SIGNAL", "INSUFFICIENT_DATA"]),
        )
    ).all()
    return set(rows)


def _fixture_counts(db: Session, start: datetime, end: datetime) -> dict[int, int]:
    rows = db.execute(
        select(Match.competition_id, func.count())
        .where(Match.kickoff_at >= start.astimezone(timezone.utc), Match.kickoff_at <= end.astimezone(timezone.utc))
        .group_by(Match.competition_id)
    ).all()
    return {int(competition_id): int(count) for competition_id, count in rows}


def _competition_row(row: Competition, fixtures: int) -> dict:
    return {
        "id": row.id,
        "country": row.country or "—",
        "name": row.name,
        "competition_type": row.competition_type or "OTHER",
        "season": row.current_season or "—",
        "fixtures_j14": fixtures,
        "odds_available": bool(row.odds_available),
        "fixtures_available": bool(row.fixtures_available),
        "last_sync": None if row.last_sync is None else row.last_sync.isoformat(),
        "gender": row.gender,
        "age_category": row.age_category,
        "continent": row.continent,
        "tier": row.tier,
        "provider_competition_id": row.provider_competition_id,
    }


def _label(db: Session, row: Match) -> str:
    payload = _match(db, row)
    return f"{payload['home_team']} {payload['away_team']} {payload['competition']}"
