"""Train the active model versions from the imported database."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.db.session import SessionLocal
from app.ml.train import train_all


def main() -> None:
    with SessionLocal() as session:
        versions = train_all(session)
    for row in versions:
        print(row.model_key, row.version, row.metrics)


if __name__ == "__main__":
    main()
