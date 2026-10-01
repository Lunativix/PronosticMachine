"""Load stored matches into the modeling frame."""

from __future__ import annotations

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Bookmaker, Competition, Injury, Match, Odds, Season, Team, TeamStatistic


def matches_frame(session: Session) -> pd.DataFrame:
    home = Team.__table__.alias("home_team")
    away = Team.__table__.alias("away_team")
    statement = (
        select(
            Match.id,
            Match.kickoff_at,
            Match.home_goals,
            Match.away_goals,
            Match.status,
            Match.source,
            home.c.name,
            away.c.name,
            Competition.name,
            Season.name,
        )
        .join(home, home.c.id == Match.home_team_id)
        .join(away, away.c.id == Match.away_team_id)
        .join(Competition, Competition.id == Match.competition_id)
        .join(Season, Season.id == Match.season_id)
        .order_by(Match.kickoff_at, Match.id)
    )
    rows = session.execute(statement).all()
    frame = pd.DataFrame(
        rows,
        columns=[
            "match_id",
            "kickoff",
            "home_goals",
            "away_goals",
            "status",
            "source",
            "home_team",
            "away_team",
            "competition",
            "season",
        ],
    )
    if frame.empty:
        return frame
    frame = _attach_stats(session, frame)
    frame = _attach_odds(session, frame)
    frame = _attach_absences(session, frame)
    return frame


def _attach_stats(session: Session, frame: pd.DataFrame) -> pd.DataFrame:
    stats = session.execute(
        select(
            TeamStatistic.match_id,
            Team.name,
            TeamStatistic.shots,
            TeamStatistic.shots_on_target,
            TeamStatistic.possession,
            TeamStatistic.corners,
            TeamStatistic.yellow_cards,
            TeamStatistic.red_cards,
            TeamStatistic.xg,
            TeamStatistic.xga,
        ).join(Team, Team.id == TeamStatistic.team_id)
    ).all()
    if not stats:
        return frame
    table = pd.DataFrame(
        stats,
        columns=["match_id", "team", "shots", "sot", "possession", "corners", "yellow", "red", "xg", "xga"],
    )
    merged = frame.copy()
    for side, team_column in (("home", "home_team"), ("away", "away_team")):
        side_table = table.rename(columns={"team": team_column})
        side_table = side_table.add_prefix("") 
        renamed = {
            "shots": f"shots_{side}",
            "sot": f"sot_{side}",
            "possession": f"possession_{side}",
            "corners": f"corners_{side}",
            "yellow": f"yellow_{side}",
            "red": f"red_{side}",
            "xg": f"xg_{side}",
            "xga": f"xga_{side}",
        }
        piece = table.merge(
            frame[["match_id", team_column]],
            left_on=["match_id", "team"],
            right_on=["match_id", team_column],
            how="inner",
        )
        piece = piece.rename(columns=renamed)
        keep = ["match_id", *renamed.values()]
        merged = merged.merge(piece[keep], on="match_id", how="left")
    return merged


def _attach_odds(session: Session, frame: pd.DataFrame) -> pd.DataFrame:
    rows = session.execute(
        select(Odds.match_id, Odds.selection, Odds.price, Odds.captured_at, Bookmaker.code, Match.kickoff_at)
        .join(Bookmaker, Bookmaker.id == Odds.bookmaker_id)
        .join(Match, Match.id == Odds.match_id)
        .where(Odds.status == "active", Odds.price.is_not(None))
    ).all()
    if not rows:
        return frame
    quotes = pd.DataFrame(rows, columns=["match_id", "selection", "price", "captured_at", "bookmaker", "kickoff"])
    quotes["captured_at"] = pd.to_datetime(quotes["captured_at"], utc=True)
    quotes["kickoff"] = pd.to_datetime(quotes["kickoff"], utc=True)
    prematch = quotes[quotes["captured_at"] <= quotes["kickoff"]]
    if prematch.empty:
        return frame
    latest = prematch.sort_values("captured_at").groupby(["match_id", "selection"], as_index=False).tail(1)
    opening = prematch.sort_values("captured_at").groupby(["match_id", "selection"], as_index=False).head(1)
    pivot = latest.pivot(index="match_id", columns="selection", values="price")
    pivot = pivot.rename(columns={"home": "odds_home", "draw": "odds_draw", "away": "odds_away"})
    open_home = opening[opening["selection"] == "home"][["match_id", "price"]].rename(
        columns={"price": "odds_open_home"}
    )
    books = latest.groupby("match_id")["bookmaker"].nunique().rename("bookmaker_count")
    dispersion = prematch[prematch["selection"] == "home"].groupby("match_id")["price"].std().rename("odds_dispersion")
    book = latest[latest["selection"] == "home"][["match_id", "bookmaker"]]
    merged = frame.merge(pivot.reset_index(), on="match_id", how="left")
    merged = merged.merge(open_home, on="match_id", how="left")
    merged = merged.merge(books.reset_index(), on="match_id", how="left")
    merged = merged.merge(dispersion.reset_index(), on="match_id", how="left")
    merged = merged.merge(book, on="match_id", how="left")
    return merged


def _attach_absences(session: Session, frame: pd.DataFrame) -> pd.DataFrame:
    injuries = session.execute(select(Injury.team_id, Injury.match_id, Team.name).join(Team, Team.id == Injury.team_id)).all()
    if not injuries:
        return frame
    table = pd.DataFrame(injuries, columns=["team_id", "match_id", "team"])
    counts = table.groupby(["match_id", "team"]).size().rename("absent").reset_index()
    home = counts.rename(columns={"team": "home_team", "absent": "home_absent"})
    away = counts.rename(columns={"team": "away_team", "absent": "away_absent"})
    merged = frame.merge(home[["match_id", "home_team", "home_absent"]], on=["match_id", "home_team"], how="left")
    return merged.merge(away[["match_id", "away_team", "away_absent"]], on=["match_id", "away_team"], how="left")
