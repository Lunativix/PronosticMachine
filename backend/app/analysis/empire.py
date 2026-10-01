"""Append-only public facts. A repeated key is updated, not copied."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session, aliased

from app.db.base import utcnow
from app.models import Competition, InformationItem, Match, Team, TrackedProposition


def standings_rows(payload: dict, competition: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for child in payload.get("children") or []:
        if not isinstance(child, dict):
            continue
        group = str(child.get("name") or child.get("abbreviation") or competition)
        entries = ((child.get("standings") or {}).get("entries") or []) if isinstance(child.get("standings"), dict) else []
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            team = str((entry.get("team") or {}).get("displayName") or "")
            if not team:
                continue
            stats = {item.get("name"): item.get("displayValue") for item in entry.get("stats") or [] if isinstance(item, dict)}
            rows.append(
                {
                    "key": f"standing:{competition}:{group}:{team}",
                    "title": f"{team} — {group}",
                    "body": (
                        f"{stats.get('points', '—')} pts, {stats.get('gamesPlayed', '—')} matchs, "
                        f"{stats.get('wins', '—')} V, {stats.get('ties', '—')} N, {stats.get('losses', '—')} D"
                    ),
                    "source": "ESPN",
                }
            )
    return rows


def archive_information(session: Session, readings: list[dict], public: dict[str, object]) -> dict[str, int]:
    existing = {row.external_key: row for row in session.scalars(select(InformationItem)).all()}
    added = 0
    for item in public.get("media") or []:
        if not isinstance(item, dict) or not item.get("title"):
            continue
        key = str(item.get("url") or f"{item.get('source')}:{item.get('title')}")
        added += _put(session, existing, key=key[:240], kind="headline", source=str(item.get("source") or "média"), title=str(item["title"])[:300], url=item.get("url"), body=None)
    for item in public.get("social", {}).get("posts") or []:
        if not isinstance(item, dict) or not item.get("title"):
            continue
        key = str(item.get("url") or item.get("title"))
        added += _put(session, existing, key=key[:240], kind="headline", source=str(item.get("source") or "réseau"), title=str(item["title"])[:300], url=item.get("url"), body=None)
    for row in public.get("standings") or []:
        if not isinstance(row, dict):
            continue
        added += _put(session, existing, key=str(row["key"])[:240], kind="standing", source=str(row.get("source") or "ESPN"), title=str(row["title"])[:300], url=None, body=str(row.get("body") or "")[:500])
    for reading in readings:
        match_id = reading.get("match_id")
        for lineup in reading.get("lineups") or []:
            starters = [player.get("name") for player in lineup.get("players") or [] if player.get("starter") and player.get("name")]
            if not starters or match_id is None:
                continue
            team = str(lineup.get("team") or "Équipe")
            added += _put(
                session,
                existing,
                key=f"lineup:{match_id}:{team}"[:240],
                kind="lineup",
                source="ESPN",
                title=f"{team} — compo publiée",
                url=None,
                body=", ".join(str(name) for name in starters[:11]),
            )
    added += _archive_scores(session, existing)
    added += _archive_settled(session, existing)
    session.commit()
    counts = dict(session.execute(select(InformationItem.kind, func.count()).group_by(InformationItem.kind)).all())
    return {
        "added": added,
        "headlines": int(counts.get("headline") or 0),
        "results": int(counts.get("result") or 0),
        "standings": int(counts.get("standing") or 0),
        "lineups": int(counts.get("lineup") or 0),
        "paper": int(counts.get("paper") or 0),
        "total": int(sum(counts.values())),
    }


def _archive_scores(session: Session, existing: dict[str, InformationItem]) -> int:
    added = 0
    home_t = aliased(Team)
    away_t = aliased(Team)
    rows = session.execute(
        select(Match.id, Match.home_goals, Match.away_goals, Competition.name, home_t.name, away_t.name)
        .join(Competition, Competition.id == Match.competition_id)
        .join(home_t, home_t.id == Match.home_team_id)
        .join(away_t, away_t.id == Match.away_team_id)
        .where(Match.home_goals.is_not(None), Match.away_goals.is_not(None), func.lower(Match.status) == "finished")
    ).all()
    for match_id, home_goals, away_goals, competition, home, away in rows:
        added += _put(
            session,
            existing,
            key=f"score:{match_id}",
            kind="result",
            source=str(competition or "match"),
            title=f"{home} {home_goals}-{away_goals} {away}",
            url=None,
            body=None,
        )
    return added


def _archive_settled(session: Session, existing: dict[str, InformationItem]) -> int:
    added = 0
    rows = session.scalars(select(TrackedProposition).where(TrackedProposition.status.in_(("WON", "LOST")))).all()
    for row in rows:
        added += _put(
            session,
            existing,
            key=f"paper:{row.id}",
            kind="paper",
            source=row.strategy or "agent",
            title=f"{row.selection_label} — {row.status}",
            url=None,
            body=None if row.paper_profit is None else f"profit fictif {row.paper_profit}",
        )
    return added


def _put(session: Session, existing: dict[str, InformationItem], *, key: str, kind: str, source: str, title: str, url: str | None, body: str | None) -> int:
    current = existing.get(key)
    if current is None:
        current = InformationItem(
            created_at=utcnow(),
            updated_at=utcnow(),
            kind=kind,
            source=source[:80],
            external_key=key,
            title=title,
            url=None if not url else str(url)[:400],
            body=body,
        )
        session.add(current)
        existing[key] = current
        return 1
    if current.title != title or current.body != body:
        current.title = title
        current.body = body
        current.updated_at = utcnow()
    return 0
