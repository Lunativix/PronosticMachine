"""Walk-forward backtest keeps training strictly in the past."""

from __future__ import annotations

import pandas as pd

from app.backtesting.engine import run_backtest
from app.core.config import get_settings
from generate_test_data import generate


def test_backtest_is_chronological(monkeypatch) -> None:
    monkeypatch.setenv("MIN_EDGE", "0.0")
    monkeypatch.setenv("MIN_EV", "-1")
    monkeypatch.setenv("MIN_MODEL_CONFIDENCE", "0.0")
    monkeypatch.setenv("MIN_HISTORY_MATCHES", "1")
    monkeypatch.setenv("MODEL_RETRAIN_DAYS", "30")
    get_settings.cache_clear()
    frame = generate(rounds=6)
    payload = run_backtest(None, frame=frame, settings=get_settings(), persist=False, max_iter=25)
    get_settings.cache_clear()
    results = pd.DataFrame(payload["results"])
    assert "final_bankroll" in payload["metrics"]
    if not results.empty:
        assert results["trained_until"].lt(results["kickoff_at"]).all() or True
        trained = pd.to_datetime(results["trained_until"], utc=True)
        kickoff = pd.to_datetime(results["kickoff_at"], utc=True)
        assert (trained < kickoff).all()
        assert kickoff.is_monotonic_increasing
