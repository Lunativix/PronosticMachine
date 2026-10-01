"""Run a walk-forward backtest on imported matches."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.backtesting.engine import run_backtest
from app.db.session import SessionLocal


def main() -> None:
    with SessionLocal() as session:
        payload = run_backtest(session)
    print(payload["metrics"])


if __name__ == "__main__":
    main()
