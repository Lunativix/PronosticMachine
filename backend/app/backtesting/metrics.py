"""Betting metrics. Yield is profit over turnover. ROI is profit over the initial bankroll."""

from __future__ import annotations

from collections import defaultdict

import numpy as np
import pandas as pd


def summarize(results: pd.DataFrame, initial_bankroll: float) -> dict[str, float]:
    if results.empty:
        return {"bets": 0, "profit": 0.0, "yield": 0.0, "roi": 0.0, "max_drawdown": 0.0}
    stakes = results["stake"].to_numpy(dtype=float)
    pnl = results["pnl"].to_numpy(dtype=float)
    turnover = float(stakes.sum())
    profit = float(pnl.sum())
    wins = pnl > 0
    losses = pnl < 0
    gross_win = float(pnl[wins].sum()) if wins.any() else 0.0
    gross_loss = abs(float(pnl[losses].sum())) if losses.any() else 0.0
    returns = np.divide(pnl, stakes, out=np.zeros_like(pnl), where=stakes > 0)
    volatility = float(np.std(returns)) if len(returns) else 0.0
    sharpe_like = 0.0 if volatility == 0 else float(np.mean(returns) / volatility * np.sqrt(len(returns)))
    bankroll = initial_bankroll + np.cumsum(pnl)
    peak = np.maximum.accumulate(bankroll)
    drawdown = (peak - bankroll) / np.clip(peak, 1e-9, None)
    return {
        "bets": int(len(results)),
        "profit": profit,
        "turnover": turnover,
        "yield": profit / turnover if turnover else 0.0,
        "roi": profit / initial_bankroll if initial_bankroll else 0.0,
        "win_rate": float(wins.mean()) if len(results) else 0.0,
        "average_odds": float(results["odds"].mean()),
        "median_odds": float(results["odds"].median()),
        "expected_value": float(results["expected_value"].mean()),
        "max_drawdown": float(drawdown.max()) if len(drawdown) else 0.0,
        "sharpe_like": sharpe_like,
        "volatility": volatility,
        "profit_factor": gross_win / gross_loss if gross_loss else gross_win,
        "longest_losing_streak": float(_longest_streak(pnl < 0)),
        "longest_winning_streak": float(_longest_streak(pnl > 0)),
    }


def group_metrics(results: pd.DataFrame, initial_bankroll: float) -> dict[str, list[dict[str, object]]]:
    grouping = {
        "season": "season",
        "competition": "competition",
        "market": "market",
        "model": "model_key",
        "bookmaker": "bookmaker",
    }
    output: dict[str, list[dict[str, object]]] = {}
    for label, column in grouping.items():
        if column not in results.columns:
            continue
        output[label] = _bucket(results, column, initial_bankroll)
    if not results.empty:
        odds_bins = pd.cut(results["odds"], [1, 1.5, 2, 3, 5, 100], include_lowest=True)
        edge_bins = pd.cut(results["edge"], [-1, 0, 0.04, 0.08, 1], include_lowest=True)
        output["odds_range"] = _bucket(results.assign(bucket=odds_bins.astype(str)), "bucket", initial_bankroll)
        output["edge_range"] = _bucket(results.assign(bucket=edge_bins.astype(str)), "bucket", initial_bankroll)
        if "confidence" in results.columns:
            output["confidence"] = _bucket(results.fillna({"confidence": -1}), "confidence", initial_bankroll)
    return output


def _bucket(results: pd.DataFrame, column: str, initial_bankroll: float) -> list[dict[str, object]]:
    rows = []
    for key, part in results.groupby(column, dropna=False):
        metrics = summarize(part, initial_bankroll)
        metrics["key"] = str(key)
        rows.append(metrics)
    return rows


def _longest_streak(mask: np.ndarray) -> int:
    best = current = 0
    for flag in mask:
        current = current + 1 if flag else 0
        best = max(best, current)
    return best


def calibration_table(probabilities: list[float], outcomes: list[int], bins: int = 8) -> list[dict[str, float]]:
    if not probabilities:
        return []
    frame = pd.DataFrame({"p": probabilities, "y": outcomes})
    frame["bin"] = pd.cut(frame["p"], bins=bins, include_lowest=True)
    rows = []
    for interval, part in frame.groupby("bin", observed=False):
        if part.empty:
            continue
        rows.append(
            {
                "bin": str(interval),
                "count": float(len(part)),
                "mean_probability": float(part["p"].mean()),
                "observed_frequency": float(part["y"].mean()),
            }
        )
    return rows
