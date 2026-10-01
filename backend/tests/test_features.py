"""Temporal causality of the feature builder."""

from __future__ import annotations

import pandas as pd
import pytest

from app.features.football import (
    FORBIDDEN_FEATURE_COLUMNS,
    MODEL_FEATURE_COLUMNS,
    TemporalLeakageError,
    TeamMatch,
    build_feature_table,
    features_from_history,
)


def _frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "match_id": 1,
                "kickoff": "2024-01-01T15:00:00Z",
                "home_team": "A",
                "away_team": "B",
                "home_goals": 1,
                "away_goals": 0,
                "status": "finished",
                "competition": "L",
                "season": "2024",
                "shots_home": 10,
                "shots_away": 8,
            },
            {
                "match_id": 2,
                "kickoff": "2024-01-08T15:00:00Z",
                "home_team": "A",
                "away_team": "C",
                "home_goals": 2,
                "away_goals": 2,
                "status": "finished",
                "competition": "L",
                "season": "2024",
                "shots_home": 12,
                "shots_away": 9,
            },
        ]
    )


def test_no_future_data_leakage() -> None:
    base = _frame()
    clean = build_feature_table(base)
    future = base.copy()
    future.loc[len(future)] = {
        "match_id": 3,
        "kickoff": "2024-02-01T15:00:00Z",
        "home_team": "A",
        "away_team": "B",
        "home_goals": 20,
        "away_goals": 0,
        "status": "finished",
        "competition": "L",
        "season": "2024",
        "shots_home": 40,
        "shots_away": 1,
    }
    with_future = build_feature_table(future)
    left = clean[MODEL_FEATURE_COLUMNS].reset_index(drop=True).astype("object")
    right = with_future.loc[with_future["match_id"].isin([1, 2]), MODEL_FEATURE_COLUMNS].reset_index(drop=True)
    right = right.astype("object").where(pd.notna(right), None)
    left = left.where(pd.notna(left), None)
    pd.testing.assert_frame_equal(left, right, check_dtype=False)
    changed = base.copy()
    changed.loc[changed["match_id"] == 2, "home_goals"] = 9
    again = build_feature_table(changed)
    pd.testing.assert_series_equal(
        clean.loc[clean["match_id"] == 2, "home_gf_pg_5"].reset_index(drop=True),
        again.loc[again["match_id"] == 2, "home_gf_pg_5"].reset_index(drop=True),
        check_names=False,
    )
    assert FORBIDDEN_FEATURE_COLUMNS.isdisjoint(MODEL_FEATURE_COLUMNS)


def test_future_history_raises() -> None:
    history = [
        TeamMatch(
            kickoff=pd.Timestamp("2024-02-01", tz="UTC"),
            opponent="B",
            goals_for=20,
            goals_against=0,
            points=3,
            venue="home",
            competition="L",
            season="2024",
        )
    ]
    record = pd.Series(
        {
            "match_id": 1,
            "kickoff": pd.Timestamp("2024-01-01", tz="UTC"),
            "home_team": "A",
            "away_team": "B",
            "competition": "L",
            "season": "2024",
        }
    )
    with pytest.raises(TemporalLeakageError):
        features_from_history(history, [], record)
