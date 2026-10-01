"""Markets derived from a Dixon-Coles score matrix. No odds are created here."""

from __future__ import annotations

import numpy as np

LINES = (0.5, 1.5, 2.5, 3.5)


def _grid(matrix: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    home = np.arange(matrix.shape[0])[:, None]
    away = np.arange(matrix.shape[1])[None, :]
    return home, away


def probability_for(matrix: np.ndarray, market: str, selection: str) -> float:
    mask = selection_mask(matrix, market, selection)
    total = float(matrix.sum())
    if total <= 0:
        raise ValueError("Score matrix is empty.")
    return float(matrix[mask].sum() / total)


def selection_mask(matrix: np.ndarray, market: str, selection: str) -> np.ndarray:
    home, away = _grid(matrix)
    total_goals = home + away
    if market == "1X2" and selection == "home":
        return home > away
    if market == "1X2" and selection == "draw":
        return home == away
    if market == "1X2" and selection == "away":
        return home < away
    if market == "double_chance" and selection == "1X":
        return home >= away
    if market == "double_chance" and selection == "X2":
        return home <= away
    if market == "double_chance" and selection == "12":
        return home != away
    if market == "draw_no_bet" and selection == "home":
        return home > away
    if market == "draw_no_bet" and selection == "away":
        return home < away
    if market == "btts" and selection == "yes":
        return (home > 0) & (away > 0)
    if market == "btts" and selection == "no":
        return ~((home > 0) & (away > 0))
    if market == "handicap" and selection == "home_-1.5":
        return home >= away + 2
    if market == "handicap" and selection == "away_-1.5":
        return away >= home + 2
    if market == "over_under" and selection.startswith(("over_", "under_")):
        side, raw = selection.split("_", 1)
        line = float(raw)
        if line not in LINES:
            raise ValueError(f"Unsupported total line: {line}")
        return total_goals > line if side == "over" else total_goals < line
    raise ValueError(f"Unsupported market selection: {market} {selection}")


def catalog(matrix: np.ndarray) -> list[dict[str, float | str]]:
    """Every market this score model can price. Odds stay absent until a provider supplies them."""
    rows: list[dict[str, float | str]] = []
    specs = [
        ("1X2", "home"),
        ("1X2", "draw"),
        ("1X2", "away"),
        ("double_chance", "1X"),
        ("double_chance", "X2"),
        ("double_chance", "12"),
        ("draw_no_bet", "home"),
        ("draw_no_bet", "away"),
        ("btts", "yes"),
        ("btts", "no"),
        ("handicap", "home_-1.5"),
        ("handicap", "away_-1.5"),
    ]
    for line in LINES:
        specs.append(("over_under", f"over_{line}"))
        specs.append(("over_under", f"under_{line}"))
    for market, selection in specs:
        rows.append(
            {
                "market": market,
                "selection": selection,
                "model_probability": probability_for(matrix, market, selection),
            }
        )
    return rows


def joint_probability(matrix: np.ndarray, left: tuple[str, str], right: tuple[str, str]) -> float:
    mask = selection_mask(matrix, *left) & selection_mask(matrix, *right)
    total = float(matrix.sum())
    return float(matrix[mask].sum() / total)
