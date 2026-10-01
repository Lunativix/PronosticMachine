"""Import a user CSV or JSON file. Synthetic files require --synthetic."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.core.config import get_settings
from app.data.providers.registry import football_provider
from app.db.session import SessionLocal
from app.services.import_service import import_frame


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit("Usage: python scripts/import_data.py <file> [--synthetic]")
    path = Path(sys.argv[1])
    synthetic = "--synthetic" in sys.argv
    if "synthetic" in path.as_posix().lower() and not synthetic:
        raise SystemExit("Refusing to import a synthetic file without --synthetic.")
    frame = football_provider(get_settings(), path).load()
    with SessionLocal() as session:
        report = import_frame(session, frame, source=path.name)
    print(report.as_dict())


if __name__ == "__main__":
    main()
