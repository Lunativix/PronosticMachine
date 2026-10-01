"""Compare stored analyses with later results. Stored probabilities are never rewritten."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.analysis.markets import probability_for
from app.models import CombinationAnalysis, MarketAnalysis, Match

import numpy as np


def _settled(match: Match, market: str, selection: str) -> bool | None:
    if match.home_goals is None or match.away_goals is None or str(match.status).lower() != "finished":
        return None
    matrix = np.zeros((max(match.home_goals, match.away_goals) + 1,) * 2)
    matrix[match.home_goals, match.away_goals] = 1.0
    try:
        return probability_for(matrix, market, selection) == 1.0
    except ValueError:
        return None


def selection_performance(session: Session) -> dict[str, object]:
    rows = session.scalars(select(MarketAnalysis).where(MarketAnalysis.model_probability.is_not(None))).all()
    resolved: list[tuple[MarketAnalysis, bool]] = []
    for row in rows:
        match = session.get(Match, row.match_id)
        if match is None or row.model_probability is None:
            continue
        outcome = _settled(match, row.market, row.selection)
        if outcome is None:
            continue
        resolved.append((row, outcome))
    if not resolved:
        return {"resolved": 0, "note": "Aucun résultat réel n'est encore relié à une analyse enregistrée."}
    brier = float(np.mean([(row.model_probability - float(hit)) ** 2 for row, hit in resolved]))
    hits = sum(1 for _, hit in resolved if hit)
    pnl = []
    for row, hit in resolved:
        if row.odds is None:
            continue
        pnl.append((row.odds - 1.0) if hit else -1.0)
    stake = float(len(pnl))
    roi = None if stake == 0 else float(sum(pnl) / stake)
    drawdown = _drawdown(pnl)
    return {
        "resolved": len(resolved),
        "hit_rate": hits / len(resolved),
        "brier": brier,
        "roi": roi,
        "yield": roi,
        "drawdown": drawdown,
        "by_confidence": _group(resolved, lambda row: row.confidence_level),
        "by_market": _group(resolved, lambda row: row.market),
        "note": "Les probabilités enregistrées ne sont pas recalibrées après le résultat.",
    }


def combination_performance(session: Session) -> dict[str, object]:
    rows = session.scalars(select(CombinationAnalysis)).all()
    resolved = 0
    hits = 0
    pnl: list[float] = []
    for row in rows:
        outcomes: list[bool] = []
        open_leg = False
        for leg in row.selections:
            match = session.get(Match, int(leg["match_id"]))
            if match is None:
                open_leg = True
                break
            outcome = _settled(match, str(leg["market"]), str(leg["selection"]))
            if outcome is None:
                open_leg = True
                break
            outcomes.append(outcome)
        if open_leg or not outcomes or row.combined_odds is None:
            continue
        won = all(outcomes)
        resolved += 1
        hits += int(won)
        pnl.append((row.combined_odds - 1.0) if won else -1.0)
    if resolved == 0:
        return {"resolved": 0}
    stake = float(len(pnl))
    return {
        "resolved": resolved,
        "hit_rate": hits / resolved,
        "roi": sum(pnl) / stake,
        "drawdown": _drawdown(pnl),
    }


def _group(rows: list[tuple[MarketAnalysis, bool]], key) -> dict[str, dict[str, float]]:
    buckets: dict[str, list[bool]] = {}
    for row, hit in rows:
        buckets.setdefault(str(key(row)), []).append(hit)
    return {
        name: {"count": float(len(values)), "hit_rate": sum(values) / len(values)}
        for name, values in buckets.items()
    }


def _drawdown(pnl: list[float]) -> float | None:
    if not pnl:
        return None
    equity = 0.0
    peak = 0.0
    worst = 0.0
    for value in pnl:
        equity += value
        peak = max(peak, equity)
        worst = min(worst, equity - peak)
    return float(worst)
