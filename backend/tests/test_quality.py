"""Data quality rejections stay visible."""

from __future__ import annotations

import pandas as pd

from app.data.quality import validate_matches


def test_invalid_rows_are_reported() -> None:
    frame = pd.DataFrame(
        [
            {
                "kickoff": "2024-01-01T15:00:00Z",
                "home_team": "A",
                "away_team": "B",
                "competition": "L",
                "season": "2024",
                "status": "finished",
                "home_goals": 1,
                "away_goals": 0,
                "odds_home": 2.0,
                "odds_draw": 3.2,
                "odds_away": 3.8,
            },
            {
                "kickoff": "not-a-date",
                "home_team": "A",
                "away_team": "A",
                "competition": "L",
                "season": "2024",
                "status": "finished",
                "home_goals": -1,
                "away_goals": 0,
                "odds_home": 1.0,
                "odds_draw": 3.2,
                "odds_away": 3.8,
            },
            {
                "kickoff": "2024-01-01T15:00:00Z",
                "home_team": "A",
                "away_team": "B",
                "competition": "L",
                "season": "2024",
                "status": "finished",
                "home_goals": 1,
                "away_goals": 0,
                "odds_home": 2.0,
                "odds_draw": 3.2,
                "odds_away": 3.8,
            },
        ]
    )
    valid, report = validate_matches(frame)
    assert report.records_total == 3
    assert report.records_invalid >= 1
    assert report.duplicates >= 1
    assert report.errors
    assert len(valid) == 1
