"""Read stored backtests and predictions for the dashboard."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import BacktestResult, BacktestRun, BankrollSnapshot, BetOpportunity, Competition, Match, Prediction


def performance(session: Session) -> dict[str, object]:
    synthetic = session.scalar(
        select(func.count()).select_from(Competition).where(Competition.name.ilike("%synthetic%"))
    ) or 0
    matches = session.scalar(select(func.count()).select_from(Match)) or 0
    signals = session.scalar(
        select(func.count()).select_from(BetOpportunity).where(BetOpportunity.state == "SIGNAL")
    ) or 0
    predictions = session.scalar(select(func.count()).select_from(Prediction)) or 0
    latest = session.scalar(select(BacktestRun).order_by(BacktestRun.created_at.desc()))
    snapshots = []
    if latest is not None:
        rows = session.scalars(
            select(BankrollSnapshot).where(BankrollSnapshot.run_id == latest.id).order_by(BankrollSnapshot.as_of)
        ).all()
        snapshots = [
            {"as_of": row.as_of.isoformat(), "bankroll": row.bankroll, "drawdown": row.drawdown} for row in rows
        ]
    settled = session.scalars(select(BacktestResult)).all()
    return {
        "matches": matches,
        "synthetic_dataset": bool(synthetic),
        "predictions": predictions,
        "signals": signals,
        "latest_backtest": None
        if latest is None
        else {"id": latest.id, "name": latest.name, "metrics": latest.metrics, "staking": latest.staking},
        "bankroll": snapshots,
        "results": [
            {
                "kickoff_at": row.kickoff_at.isoformat(),
                "pnl": row.pnl,
                "odds": row.odds,
                "edge": row.edge,
                "outcome": row.outcome,
                "season": row.season,
                "competition": row.competition,
                "market": row.market,
                "model_key": row.model_key,
                "bookmaker": row.bookmaker,
                "confidence": row.confidence,
            }
            for row in settled
        ],
    }
