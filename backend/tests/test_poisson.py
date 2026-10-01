"""Dixon-Coles probabilities and a small ratings fit."""

from __future__ import annotations

import numpy as np
import pandas as pd

from app.ml.poisson import DixonColesModel, outcome_probabilities, score_matrix


def test_score_matrix_is_a_distribution() -> None:
    matrix = score_matrix(1.4, 1.1, rho=-0.05)
    assert abs(float(matrix.sum()) - 1) < 1e-8
    probabilities = outcome_probabilities(matrix)
    assert sum(probabilities.values()) == 1 or abs(sum(probabilities.values()) - 1) < 1e-8


def test_home_advantage_increases_home_probability() -> None:
    model = DixonColesModel(
        mu=0.1,
        home_advantage=0.3,
        rho=0.0,
        attack={"A": 0.0, "B": 0.0},
        defense={"A": 0.0, "B": 0.0},
        teams=["A", "B"],
    )
    probabilities = model.predict_proba("A", "B")
    assert probabilities["home"] > probabilities["away"]


def test_fit_separates_a_strong_team() -> None:
    rows = []
    kickoff = pd.Timestamp("2024-01-01", tz="UTC")
    for index in range(24):
        rows.append(
            {
                "home_team": "Strong" if index % 2 == 0 else "Weak",
                "away_team": "Weak" if index % 2 == 0 else "Other",
                "home_goals": 3 if index % 2 == 0 else 0,
                "away_goals": 0 if index % 2 == 0 else 2,
                "kickoff": kickoff + pd.Timedelta(days=index),
            }
        )
    model = DixonColesModel.fit(pd.DataFrame(rows), max_iter=40)
    assert model.attack["Strong"] > model.attack["Weak"]
