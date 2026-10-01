"""Short-sample Poisson built only from scored and conceded goals the provider returned."""

from __future__ import annotations

import numpy as np

from app.ml.poisson import outcome_probabilities, score_matrix

HOME_ADVANTAGE = 1.08
MIN_GAMES = 3


def lambdas(home_for: list[float], home_against: list[float], away_for: list[float], away_against: list[float]) -> tuple[float, float] | None:
    if min(len(home_for), len(home_against), len(away_for), len(away_against)) < MIN_GAMES:
        return None
    home_attack = float(np.mean(home_for))
    home_defense = float(np.mean(home_against))
    away_attack = float(np.mean(away_for))
    away_defense = float(np.mean(away_against))
    lambda_home = max(0.15, ((home_attack + away_defense) / 2.0) * HOME_ADVANTAGE)
    lambda_away = max(0.15, (away_attack + home_defense) / 2.0)
    return lambda_home, lambda_away


def form_probabilities(
    home_for: list[float],
    home_against: list[float],
    away_for: list[float],
    away_against: list[float],
) -> dict[str, float] | None:
    rates = lambdas(home_for, home_against, away_for, away_against)
    if rates is None:
        return None
    return outcome_probabilities(score_matrix(rates[0], rates[1], 0.0))
