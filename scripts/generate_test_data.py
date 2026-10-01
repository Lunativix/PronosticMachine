"""Synthetic matches for automated tests. These are not real sporting results."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

TEAMS = ["North", "South", "East", "West", "Harbor", "Ridge"]


def generate(seed: int = 7, rounds: int = 10) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    strength = {team: 0.7 + index * 0.15 for index, team in enumerate(TEAMS)}
    rows = []
    kickoff = pd.Timestamp("2023-08-01", tz="UTC")
    match_id = 1
    for _ in range(rounds):
        for home_index, home in enumerate(TEAMS):
            away = TEAMS[(home_index + 1 + (_ % (len(TEAMS) - 1))) % len(TEAMS)]
            if home == away:
                continue
            lambda_home = 1.35 * strength[home] / strength[away]
            lambda_away = 1.05 * strength[away] / strength[home]
            home_goals = int(rng.poisson(lambda_home))
            away_goals = int(rng.poisson(lambda_away))
            true_home = lambda_home / (lambda_home + lambda_away + 0.9)
            price_home = max(1.2, 1.0 / min(true_home * 1.05, 0.85))
            price_away = max(1.4, price_home * (0.8 + strength[away] / strength[home]))
            price_draw = 3.3
            rows.append(
                {
                    "match_id": match_id,
                    "sport": "football",
                    "competition": "Synthetic League",
                    "competition_code": "SYN",
                    "season": "2023/2024",
                    "kickoff": kickoff.isoformat(),
                    "home_team": home,
                    "away_team": away,
                    "home_goals": home_goals,
                    "away_goals": away_goals,
                    "status": "finished",
                    "shots_home": int(8 + home_goals * 2),
                    "shots_away": int(7 + away_goals * 2),
                    "sot_home": int(3 + home_goals),
                    "sot_away": int(2 + away_goals),
                    "possession_home": 55,
                    "possession_away": 45,
                    "corners_home": 5,
                    "corners_away": 4,
                    "yellow_home": 1,
                    "yellow_away": 2,
                    "red_home": 0,
                    "red_away": 0,
                    "xg_home": round(lambda_home, 3),
                    "xg_away": round(lambda_away, 3),
                    "odds_home": round(float(price_home), 2),
                    "odds_draw": price_draw,
                    "odds_away": round(float(price_away), 2),
                    "odds_open_home": round(float(price_home) + 0.05, 2),
                    "bookmaker": "synthetic",
                    "source": "synthetic",
                    "dataset_kind": "synthetic_test_only",
                }
            )
            match_id += 1
            kickoff += pd.Timedelta(days=1)
    return pd.DataFrame(rows)


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    destination = root / "data" / "synthetic" / "football_matches.csv"
    destination.parent.mkdir(parents=True, exist_ok=True)
    frame = generate()
    frame.to_csv(destination, index=False)
    print(f"Wrote {len(frame)} synthetic rows to {destination}")
    print("This file is for tests only and is not a real sporting record.")


if __name__ == "__main__":
    main()
