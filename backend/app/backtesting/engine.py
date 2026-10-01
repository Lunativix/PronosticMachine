"""Walk-forward backtest. Training rows are always strictly earlier than the match."""

from __future__ import annotations

from datetime import timedelta

import pandas as pd
from sqlalchemy.orm import Session

from app.backtesting.metrics import group_metrics, summarize
from app.betting.bankroll import open_bankroll, settle
from app.betting.odds_math import apply_slippage
from app.betting.value_engine import analyze_market
from app.core.config import Settings, get_settings
from app.features.football import build_feature_table
from app.ml.poisson import DixonColesModel
from app.models import BacktestResult, BacktestRun, BankrollSnapshot
from app.services.match_frame import matches_frame


def run_backtest(
    session: Session | None,
    *,
    frame: pd.DataFrame | None = None,
    settings: Settings | None = None,
    staking: str = "FRACTIONAL_KELLY",
    window_mode: str = "expanding",
    rolling_days: int = 365,
    name: str = "walk-forward",
    commission: float = 0.0,
    slippage: float = 0.0,
    max_iter: int = 40,
    persist: bool = True,
) -> dict[str, object]:
    settings = settings or get_settings()
    data = frame.copy() if frame is not None else matches_frame(session)  # type: ignore[arg-type]
    data["kickoff"] = pd.to_datetime(data["kickoff"], utc=True)
    data = data.sort_values(["kickoff", "match_id"]).reset_index(drop=True)
    if not data["kickoff"].is_monotonic_increasing:
        data = data.sort_values(["kickoff", "match_id"]).reset_index(drop=True)
    features = build_feature_table(data)
    merged = data.merge(features, on="match_id", suffixes=("", "_f"))
    bankroll = open_bankroll(settings.initial_bankroll)
    rows: list[dict[str, object]] = []
    snapshots: list[dict[str, object]] = []
    model: DixonColesModel | None = None
    trained_until: pd.Timestamp | None = None
    home_pnl = 0.0
    favorite_pnl = 0.0
    benchmark_stakes = 0.0
    for record in merged.itertuples(index=False):
        if str(record.status).lower() != "finished":
            continue
        prior = data[data["kickoff"] < record.kickoff]
        prior = prior[prior["status"].astype(str).str.lower().eq("finished")]
        if window_mode == "rolling":
            cutoff = pd.Timestamp(record.kickoff) - pd.Timedelta(days=rolling_days)
            prior = prior[prior["kickoff"] >= cutoff]
        if len(prior) < 12:
            continue
        needs_fit = model is None or trained_until is None or (
            pd.Timestamp(record.kickoff) - trained_until
        ) >= timedelta(days=settings.model_retrain_days)
        if needs_fit:
            model = DixonColesModel.fit(prior, max_iter=max_iter)
            trained_until = pd.Timestamp(prior["kickoff"].max())
        assert trained_until is not None and trained_until < pd.Timestamp(record.kickoff)
        assert model is not None
        probabilities = model.predict_proba(str(record.home_team), str(record.away_team))
        history = int(min(record.home_history_n or 0, record.away_history_n or 0))
        odds = _odds(record)
        actual = _result(record.home_goals, record.away_goals)
        if odds:
            unit = 1.0
            home_pnl += unit * (odds["home"] - 1) if actual == "home" else -unit
            favorite = min(odds, key=odds.get)
            favorite_pnl += unit * (odds[favorite] - 1) if actual == favorite else -unit
            benchmark_stakes += unit
            values = analyze_market(
                probabilities,
                odds,
                data_quality=float(record.completeness or 0),
                history_matches=history,
                expected_calibration_error=None,
                model_agreement=None,
                bookmaker_count=int(getattr(record, "bookmaker_count", 1) or 1),
                odds_dispersion=_maybe(getattr(record, "odds_dispersion", None)),
                min_edge=settings.min_edge,
                min_ev=settings.min_ev,
                min_model_confidence=settings.min_model_confidence,
                min_history_matches=settings.min_history_matches,
            )
            chosen = max(values, key=lambda item: item.expected_value)
            if chosen.state == "SIGNAL":
                filled = apply_slippage(chosen.odds, slippage, commission)
                amount, pnl = settle(
                    bankroll,
                    probability=chosen.model_probability,
                    odds=filled,
                    won=chosen.selection == actual,
                    method=staking,
                    kelly_fraction=settings.kelly_fraction,
                    max_stake_percent=settings.max_stake_percent,
                    fixed_stake=settings.fixed_stake,
                )
                rows.append(
                    {
                        "match_id": int(record.match_id),
                        "kickoff_at": pd.Timestamp(record.kickoff).to_pydatetime(),
                        "market": "1X2",
                        "selection": chosen.selection,
                        "odds": filled,
                        "stake": amount,
                        "pnl": pnl,
                        "bankroll_after": bankroll.bankroll,
                        "edge": chosen.edge,
                        "expected_value": chosen.expected_value,
                        "outcome": "win" if chosen.selection == actual else "loss",
                        "state": chosen.state,
                        "trained_until": trained_until.to_pydatetime(),
                        "competition": str(record.competition),
                        "season": str(record.season),
                        "bookmaker": str(getattr(record, "bookmaker", "market")),
                        "model_key": "poisson",
                        "confidence": chosen.confidence,
                    }
                )
        snapshots.append(
            {
                "as_of": pd.Timestamp(record.kickoff).to_pydatetime(),
                "bankroll": bankroll.bankroll,
                "drawdown": bankroll.max_drawdown,
                "peak": bankroll.peak,
            }
        )
    result_frame = pd.DataFrame(rows)
    metrics = summarize(result_frame, settings.initial_bankroll)
    metrics["max_drawdown_path"] = bankroll.max_drawdown
    metrics["final_bankroll"] = bankroll.bankroll
    metrics["benchmark_home_yield"] = home_pnl / benchmark_stakes if benchmark_stakes else 0.0
    metrics["benchmark_favorite_yield"] = favorite_pnl / benchmark_stakes if benchmark_stakes else 0.0
    payload = {
        "metrics": metrics,
        "groups": group_metrics(result_frame, settings.initial_bankroll),
        "results": rows,
        "snapshots": snapshots,
        "window_mode": window_mode,
        "staking": staking,
    }
    if persist and session is not None:
        _persist(session, name, staking, window_mode, payload)
    return payload


def _persist(session: Session, name: str, staking: str, window_mode: str, payload: dict[str, object]) -> None:
    run = BacktestRun(
        name=name,
        model_key="poisson",
        staking=staking,
        window_mode=window_mode,
        parameters={"staking": staking, "window_mode": window_mode},
        metrics=payload["metrics"],
    )
    session.add(run)
    session.flush()
    for row in payload["results"]:  # type: ignore[union-attr]
        session.add(BacktestResult(run_id=run.id, **row))
    for row in payload["snapshots"]:  # type: ignore[union-attr]
        session.add(BankrollSnapshot(run_id=run.id, **row))
    session.commit()
    payload["run_id"] = run.id


def _odds(record: object) -> dict[str, float] | None:
    values = {}
    for key, attr in (("home", "odds_home"), ("draw", "odds_draw"), ("away", "odds_away")):
        value = _maybe(getattr(record, attr, None))
        if value is None or value <= 1:
            return None
        values[key] = float(value)
    return values


def _result(home_goals: float, away_goals: float) -> str:
    if home_goals > away_goals:
        return "home"
    if home_goals == away_goals:
        return "draw"
    return "away"


def _maybe(value: object) -> float | None:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except TypeError:
        pass
    return float(value)
