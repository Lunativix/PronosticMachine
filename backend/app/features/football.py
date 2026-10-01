"""Causal football features. At kickoff T only matches with kickoff < T are visible."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import numpy as np
import pandas as pd

FEATURE_VERSION = "football-v1"

MODEL_FEATURE_COLUMNS = [
    "home_points_pg_5",
    "home_points_pg_10",
    "home_gd_pg_5",
    "home_gd_pg_10",
    "home_gf_pg_5",
    "home_ga_pg_5",
    "home_gf_pg_10",
    "home_ga_pg_10",
    "away_points_pg_5",
    "away_points_pg_10",
    "away_gd_pg_5",
    "away_gd_pg_10",
    "away_gf_pg_5",
    "away_ga_pg_5",
    "away_gf_pg_10",
    "away_ga_pg_10",
    "home_home_points_pg_5",
    "home_home_gf_pg_5",
    "home_home_ga_pg_5",
    "home_home_xg_pg_5",
    "home_home_xga_pg_5",
    "away_away_points_pg_5",
    "away_away_gf_pg_5",
    "away_away_ga_pg_5",
    "away_away_xg_pg_5",
    "away_away_xga_pg_5",
    "home_shots_pg_5",
    "away_shots_pg_5",
    "home_sot_pg_5",
    "away_sot_pg_5",
    "home_possession_pg_5",
    "away_possession_pg_5",
    "home_corners_pg_5",
    "away_corners_pg_5",
    "home_cards_pg_5",
    "away_cards_pg_5",
    "home_xg_pg_5",
    "home_xga_pg_5",
    "away_xg_pg_5",
    "away_xga_pg_5",
    "home_rest_days",
    "away_rest_days",
    "home_matches_14d",
    "away_matches_14d",
    "home_rank",
    "away_rank",
    "rank_gap",
    "h2h_home_weight",
    "home_absent",
    "away_absent",
    "has_xg",
    "has_possession",
    "has_injuries",
    "home_history_n",
    "away_history_n",
]

MARKET_FEATURE_COLUMNS = [
    "odds_home",
    "odds_draw",
    "odds_away",
    "odds_open_home",
    "odds_move_home",
    "market_implied_home",
    "odds_dispersion",
    "has_market",
]

FORBIDDEN_FEATURE_COLUMNS = {"home_goals", "away_goals", "result", "ftr"}


class TemporalLeakageError(RuntimeError):
    """A feature lookup observed an event at or after the prediction cutoff."""


@dataclass
class TeamMatch:
    kickoff: pd.Timestamp
    opponent: str
    goals_for: float
    goals_against: float
    points: float
    venue: str
    competition: str
    season: str
    shots: float | None = None
    shots_on_target: float | None = None
    possession: float | None = None
    corners: float | None = None
    cards: float | None = None
    xg: float | None = None
    xga: float | None = None


def assert_history_before(history: list[TeamMatch], as_of: datetime | pd.Timestamp) -> None:
    cutoff = pd.Timestamp(as_of)
    if cutoff.tzinfo is None:
        cutoff = cutoff.tz_localize("UTC")
    for item in history:
        kickoff = item.kickoff
        if kickoff.tzinfo is None:
            kickoff = kickoff.tz_localize("UTC")
        if kickoff >= cutoff:
            raise TemporalLeakageError(
                f"History contains {kickoff.isoformat()} which is not before {cutoff.isoformat()}."
            )


def build_feature_table(frame: pd.DataFrame) -> pd.DataFrame:
    """Build one feature row per match. Future rows in the frame cannot affect earlier rows."""
    if frame.empty:
        return pd.DataFrame()
    work = frame.copy()
    work["kickoff"] = pd.to_datetime(work["kickoff"], utc=True)
    work = work.sort_values(["kickoff", "match_id"]).reset_index(drop=True)
    histories: dict[str, list[TeamMatch]] = {}
    rows: list[dict[str, object]] = []
    for record in work.itertuples(index=False):
        home = str(record.home_team)
        away = str(record.away_team)
        home_hist = list(histories.get(home, []))
        away_hist = list(histories.get(away, []))
        assert_history_before(home_hist, record.kickoff)
        assert_history_before(away_hist, record.kickoff)
        features = features_from_history(home_hist, away_hist, record)
        rows.append(features)
        if _is_finished(record):
            _append_result(histories, record)
    return pd.DataFrame(rows)


def features_from_history(home_hist: list[TeamMatch], away_hist: list[TeamMatch], record: object) -> dict[str, object]:
    kickoff = pd.Timestamp(getattr(record, "kickoff"))
    if kickoff.tzinfo is None:
        kickoff = kickoff.tz_localize("UTC")
    assert_history_before(home_hist, kickoff)
    assert_history_before(away_hist, kickoff)
    home = str(getattr(record, "home_team"))
    away = str(getattr(record, "away_team"))
    season = str(getattr(record, "season"))
    competition = str(getattr(record, "competition"))
    row: dict[str, object] = {
        "match_id": getattr(record, "match_id"),
        "kickoff": kickoff,
        "home_team": home,
        "away_team": away,
        "competition": competition,
        "season": season,
    }
    row.update(_window_block(home_hist, "home"))
    row.update(_window_block(away_hist, "away"))
    row.update(_venue_block([item for item in home_hist if item.venue == "home"], "home_home"))
    row.update(_venue_block([item for item in away_hist if item.venue == "away"], "away_away"))
    row["home_rest_days"] = _rest_days(home_hist, kickoff)
    row["away_rest_days"] = _rest_days(away_hist, kickoff)
    row["home_matches_14d"] = _recent_count(home_hist, kickoff, 14)
    row["away_matches_14d"] = _recent_count(away_hist, kickoff, 14)
    home_rank, away_rank = _ranks(home_hist, away_hist, home, away, competition, season)
    row["home_rank"] = home_rank
    row["away_rank"] = away_rank
    row["rank_gap"] = None if home_rank is None or away_rank is None else away_rank - home_rank
    row["h2h_home_weight"] = _h2h(home_hist, away, kickoff)
    row["home_absent"] = _optional_float(record, "home_absent")
    row["away_absent"] = _optional_float(record, "away_absent")
    row["has_xg"] = float(row["home_xg_pg_5"] is not None or row["away_xg_pg_5"] is not None)
    row["has_possession"] = float(row["home_possession_pg_5"] is not None)
    row["has_injuries"] = float(row["home_absent"] is not None or row["away_absent"] is not None)
    row["home_history_n"] = float(len(home_hist))
    row["away_history_n"] = float(len(away_hist))
    market = _market_block(record, kickoff)
    row.update(market)
    row["completeness"] = _completeness(row)
    return row


def _window_block(history: list[TeamMatch], prefix: str) -> dict[str, float | None]:
    output: dict[str, float | None] = {}
    for window in (5, 10):
        sample = history[-window:]
        output[f"{prefix}_points_pg_{window}"] = _mean([item.points for item in sample])
        output[f"{prefix}_gd_pg_{window}"] = _mean(
            [item.goals_for - item.goals_against for item in sample]
        )
        output[f"{prefix}_gf_pg_{window}"] = _mean([item.goals_for for item in sample])
        output[f"{prefix}_ga_pg_{window}"] = _mean([item.goals_against for item in sample])
    last5 = history[-5:]
    output[f"{prefix}_shots_pg_5"] = _mean_optional([item.shots for item in last5])
    output[f"{prefix}_sot_pg_5"] = _mean_optional([item.shots_on_target for item in last5])
    output[f"{prefix}_possession_pg_5"] = _mean_optional([item.possession for item in last5])
    output[f"{prefix}_corners_pg_5"] = _mean_optional([item.corners for item in last5])
    output[f"{prefix}_cards_pg_5"] = _mean_optional([item.cards for item in last5])
    output[f"{prefix}_xg_pg_5"] = _mean_optional([item.xg for item in last5])
    output[f"{prefix}_xga_pg_5"] = _mean_optional([item.xga for item in last5])
    return output


def _venue_block(history: list[TeamMatch], prefix: str) -> dict[str, float | None]:
    sample = history[-5:]
    return {
        f"{prefix}_points_pg_5": _mean([item.points for item in sample]),
        f"{prefix}_gf_pg_5": _mean([item.goals_for for item in sample]),
        f"{prefix}_ga_pg_5": _mean([item.goals_against for item in sample]),
        f"{prefix}_xg_pg_5": _mean_optional([item.xg for item in sample]),
        f"{prefix}_xga_pg_5": _mean_optional([item.xga for item in sample]),
    }


def _mean(values: list[float]) -> float | None:
    if not values:
        return None
    return float(np.mean(values))


def _mean_optional(values: list[float | None]) -> float | None:
    clean = [value for value in values if value is not None and not np.isnan(value)]
    if not clean:
        return None
    return float(np.mean(clean))


def _rest_days(history: list[TeamMatch], kickoff: pd.Timestamp) -> float | None:
    if not history:
        return None
    delta = kickoff - history[-1].kickoff
    return float(delta.total_seconds() / 86400.0)


def _recent_count(history: list[TeamMatch], kickoff: pd.Timestamp, days: int) -> float:
    cutoff = kickoff - pd.Timedelta(days=days)
    return float(sum(1 for item in history if item.kickoff >= cutoff))


def _ranks(
    home_hist: list[TeamMatch],
    away_hist: list[TeamMatch],
    home: str,
    away: str,
    competition: str,
    season: str,
) -> tuple[float | None, float | None]:
    table: dict[str, list[float]] = {home: [0.0, 0.0], away: [0.0, 0.0]}
    for item in home_hist:
        if item.competition == competition and item.season == season:
            table[home][0] += item.points
            table[home][1] += item.goals_for - item.goals_against
    for item in away_hist:
        if item.competition == competition and item.season == season:
            table[away][0] += item.points
            table[away][1] += item.goals_for - item.goals_against
    if table[home] == [0.0, 0.0] and table[away] == [0.0, 0.0] and not home_hist and not away_hist:
        return None, None
    order = sorted(table, key=lambda name: (table[name][0], table[name][1]), reverse=True)
    return float(order.index(home) + 1), float(order.index(away) + 1)


def _h2h(home_hist: list[TeamMatch], away: str, kickoff: pd.Timestamp) -> float | None:
    meetings = [item for item in home_hist if item.opponent == away]
    if not meetings:
        return None
    weights = []
    values = []
    for item in meetings:
        days = max((kickoff - item.kickoff).total_seconds() / 86400.0, 0.0)
        weight = float(np.exp(-days / 365.0))
        weights.append(weight)
        values.append(item.points * weight)
    total = sum(weights)
    if total <= 0:
        return None
    return float(sum(values) / total)


def _market_block(record: object, kickoff: pd.Timestamp) -> dict[str, float | None]:
    stamped = getattr(record, "odds_timestamp", None)
    if stamped is not None and not (isinstance(stamped, float) and np.isnan(stamped)):
        odds_time = pd.Timestamp(stamped)
        if odds_time.tzinfo is None:
            odds_time = odds_time.tz_localize("UTC")
        if odds_time > kickoff:
            return _empty_market()
    odds_home = _optional_float(record, "odds_home")
    odds_draw = _optional_float(record, "odds_draw")
    odds_away = _optional_float(record, "odds_away")
    opening = _optional_float(record, "odds_open_home")
    dispersion = _optional_float(record, "odds_dispersion")
    implied = None if odds_home is None or odds_home <= 1 else 1.0 / odds_home
    move = None if opening is None or odds_home is None else odds_home - opening
    return {
        "odds_home": odds_home,
        "odds_draw": odds_draw,
        "odds_away": odds_away,
        "odds_open_home": opening,
        "odds_move_home": move,
        "market_implied_home": implied,
        "odds_dispersion": dispersion,
        "has_market": float(odds_home is not None and odds_draw is not None and odds_away is not None),
    }


def _empty_market() -> dict[str, float | None]:
    return {
        "odds_home": None,
        "odds_draw": None,
        "odds_away": None,
        "odds_open_home": None,
        "odds_move_home": None,
        "market_implied_home": None,
        "odds_dispersion": None,
        "has_market": 0.0,
    }


def _completeness(row: dict[str, object]) -> float:
    tracked = [column for column in MODEL_FEATURE_COLUMNS if not column.startswith("has_")]
    present = sum(row.get(column) is not None for column in tracked)
    return float(present / len(tracked))


def _optional_float(record: object, name: str) -> float | None:
    if not hasattr(record, name):
        return None
    value = getattr(record, name)
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return None
    try:
        if pd.isna(value):
            return None
    except TypeError:
        pass
    return float(value)


def _is_finished(record: object) -> bool:
    status = str(getattr(record, "status", "")).lower()
    home = getattr(record, "home_goals", None)
    away = getattr(record, "away_goals", None)
    return status == "finished" and home is not None and away is not None and not pd.isna(home)


def _append_result(histories: dict[str, list[TeamMatch]], record: object) -> None:
    kickoff = pd.Timestamp(getattr(record, "kickoff"))
    if kickoff.tzinfo is None:
        kickoff = kickoff.tz_localize("UTC")
    home = str(getattr(record, "home_team"))
    away = str(getattr(record, "away_team"))
    home_goals = float(getattr(record, "home_goals"))
    away_goals = float(getattr(record, "away_goals"))
    histories.setdefault(home, []).append(
        _team_match(record, kickoff, away, home_goals, away_goals, "home", "home")
    )
    histories.setdefault(away, []).append(
        _team_match(record, kickoff, home, away_goals, home_goals, "away", "away")
    )


def _team_match(
    record: object,
    kickoff: pd.Timestamp,
    opponent: str,
    goals_for: float,
    goals_against: float,
    venue: str,
    side: str,
) -> TeamMatch:
    points = 3.0 if goals_for > goals_against else 1.0 if goals_for == goals_against else 0.0
    prefix = "home" if side == "home" else "away"
    other = "away" if side == "home" else "home"
    return TeamMatch(
        kickoff=kickoff,
        opponent=opponent,
        goals_for=goals_for,
        goals_against=goals_against,
        points=points,
        venue=venue,
        competition=str(getattr(record, "competition")),
        season=str(getattr(record, "season")),
        shots=_optional_float(record, f"shots_{prefix}"),
        shots_on_target=_optional_float(record, f"sot_{prefix}"),
        possession=_optional_float(record, f"possession_{prefix}"),
        corners=_optional_float(record, f"corners_{prefix}"),
        cards=_cards(record, prefix),
        xg=_optional_float(record, f"xg_{prefix}"),
        xga=_optional_float(record, f"xg_{other}"),
    )


def _cards(record: object, prefix: str) -> float | None:
    yellow = _optional_float(record, f"yellow_{prefix}")
    red = _optional_float(record, f"red_{prefix}")
    if yellow is None and red is None:
        return None
    return float((yellow or 0.0) + (red or 0.0))
