"""Dixon-Coles bivariate Poisson score model (Maher 1982, Dixon and Coles 1997)."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.stats import poisson

MAX_GOALS = 8


def dixon_coles_tau(home_goals: int, away_goals: int, lambda_home: float, lambda_away: float, rho: float) -> float:
    if home_goals == 0 and away_goals == 0:
        return 1.0 - lambda_home * lambda_away * rho
    if home_goals == 0 and away_goals == 1:
        return 1.0 + lambda_home * rho
    if home_goals == 1 and away_goals == 0:
        return 1.0 + lambda_away * rho
    if home_goals == 1 and away_goals == 1:
        return 1.0 - rho
    return 1.0


def score_matrix(lambda_home: float, lambda_away: float, rho: float, max_goals: int = MAX_GOALS) -> np.ndarray:
    matrix = np.zeros((max_goals + 1, max_goals + 1))
    for home_goals in range(max_goals + 1):
        for away_goals in range(max_goals + 1):
            independent = poisson.pmf(home_goals, lambda_home) * poisson.pmf(away_goals, lambda_away)
            matrix[home_goals, away_goals] = independent * max(
                dixon_coles_tau(home_goals, away_goals, lambda_home, lambda_away, rho),
                1e-12,
            )
    total = matrix.sum()
    if total <= 0:
        return np.full_like(matrix, 1.0 / matrix.size)
    return matrix / total


def outcome_probabilities(matrix: np.ndarray) -> dict[str, float]:
    home = float(np.tril(matrix, k=-1).sum())
    draw = float(np.trace(matrix))
    away = float(np.triu(matrix, k=1).sum())
    total = home + draw + away
    return {"home": home / total, "draw": draw / total, "away": away / total}


@dataclass
class DixonColesModel:
    """Attack and defence ratings estimated only from the matches passed to fit."""

    mu: float
    home_advantage: float
    rho: float
    attack: dict[str, float]
    defense: dict[str, float]
    teams: list[str]
    xi: float = 0.003

    def lambdas(self, home: str, away: str) -> tuple[float, float]:
        attack_home = self.attack.get(home, 0.0)
        attack_away = self.attack.get(away, 0.0)
        defense_home = self.defense.get(home, 0.0)
        defense_away = self.defense.get(away, 0.0)
        lambda_home = float(np.exp(self.mu + self.home_advantage + attack_home - defense_away))
        lambda_away = float(np.exp(self.mu + attack_away - defense_home))
        return lambda_home, lambda_away

    def predict_proba(self, home: str, away: str) -> dict[str, float]:
        lambda_home, lambda_away = self.lambdas(home, away)
        return outcome_probabilities(score_matrix(lambda_home, lambda_away, self.rho))

    def explain(self, home: str, away: str) -> list[dict[str, float | str]]:
        lambda_home, lambda_away = self.lambdas(home, away)
        return [
            {"name": "intercept", "value": self.mu, "target": "both"},
            {"name": "home_advantage", "value": self.home_advantage, "target": "lambda_home"},
            {"name": "home_attack", "value": self.attack.get(home, 0.0), "target": "lambda_home"},
            {"name": "away_defense", "value": -self.defense.get(away, 0.0), "target": "lambda_home"},
            {"name": "away_attack", "value": self.attack.get(away, 0.0), "target": "lambda_away"},
            {"name": "home_defense", "value": -self.defense.get(home, 0.0), "target": "lambda_away"},
            {"name": "lambda_home", "value": lambda_home, "target": "score"},
            {"name": "lambda_away", "value": lambda_away, "target": "score"},
            {"name": "rho", "value": self.rho, "target": "low_score_dependence"},
        ]

    @classmethod
    def fit(cls, matches: pd.DataFrame, *, xi: float = 0.003, max_iter: int = 80) -> DixonColesModel:
        frame = matches.dropna(subset=["home_team", "away_team", "home_goals", "away_goals"]).copy()
        frame["kickoff"] = pd.to_datetime(frame["kickoff"], utc=True)
        frame = frame.sort_values("kickoff")
        teams = sorted(set(frame["home_team"]).union(frame["away_team"]))
        index = {team: position for position, team in enumerate(teams)}
        n_teams = len(teams)
        if n_teams < 2 or frame.empty:
            raise ValueError("Dixon-Coles requires at least two teams and one finished match.")
        latest = frame["kickoff"].max()
        weights = np.exp(-xi * (latest - frame["kickoff"]).dt.total_seconds().to_numpy() / 86400.0)
        home_idx = frame["home_team"].map(index).to_numpy()
        away_idx = frame["away_team"].map(index).to_numpy()
        home_goals = frame["home_goals"].to_numpy(dtype=int)
        away_goals = frame["away_goals"].to_numpy(dtype=int)
        n_free = n_teams - 1
        start = np.zeros(3 + 2 * n_free)
        start[0] = np.log(max(float(frame[["home_goals", "away_goals"]].mean().mean()), 0.2))

        def unpack(params: np.ndarray) -> tuple[float, float, float, np.ndarray, np.ndarray]:
            mu = params[0]
            home_adv = params[1]
            rho = params[2]
            attack = np.zeros(n_teams)
            defense = np.zeros(n_teams)
            attack[:n_free] = params[3 : 3 + n_free]
            defense[:n_free] = params[3 + n_free :]
            attack[-1] = -attack[:n_free].sum()
            defense[-1] = -defense[:n_free].sum()
            return mu, home_adv, rho, attack, defense

        def loss(params: np.ndarray) -> float:
            mu, home_adv, rho, attack, defense = unpack(params)
            lambda_home = np.exp(mu + home_adv + attack[home_idx] - defense[away_idx])
            lambda_away = np.exp(mu + attack[away_idx] - defense[home_idx])
            log_prob = poisson.logpmf(home_goals, lambda_home) + poisson.logpmf(away_goals, lambda_away)
            tau = np.ones(len(frame))
            for row, (hg, ag, lh, la) in enumerate(zip(home_goals, away_goals, lambda_home, lambda_away, strict=True)):
                if hg <= 1 and ag <= 1:
                    tau[row] = max(dixon_coles_tau(int(hg), int(ag), float(lh), float(la), rho), 1e-12)
            return float(-np.sum(weights * (log_prob + np.log(tau))))

        bounds = [(-2, 2), (-1, 2), (-0.2, 0.2)] + [(-2, 2)] * (2 * n_free)
        result = minimize(loss, start, method="L-BFGS-B", bounds=bounds, options={"maxiter": max_iter})
        mu, home_adv, rho, attack, defense = unpack(result.x)
        return cls(
            mu=float(mu),
            home_advantage=float(home_adv),
            rho=float(rho),
            attack={team: float(attack[index[team]]) for team in teams},
            defense={team: float(defense[index[team]]) for team in teams},
            teams=teams,
            xi=xi,
        )
