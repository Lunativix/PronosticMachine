"""Paper-betting loop. A pick is won or lost only when the real score is stored."""

from __future__ import annotations

import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

LOG = ROOT / "data" / "amelioration.log"
PAUSE_SECONDS = 20 * 60


def _log(message: str) -> None:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    line = f"{datetime.now(timezone.utc).isoformat()} {message}\n"
    with LOG.open("a", encoding="utf-8") as handle:
        handle.write(line)


def _readings(session):
    from sqlalchemy import select

    from app.analysis.service import latest_probability_snapshot
    from app.api.routes.analysis import _readings as readings_from_rows
    from app.models import MarketAnalysis

    stamp = latest_probability_snapshot(session)
    if stamp is None:
        return []
    rows = session.scalars(select(MarketAnalysis).where(MarketAnalysis.created_at == stamp)).all()
    return readings_from_rows(session, list(rows))


def _refresh_scores(session) -> None:
    from datetime import datetime

    from app.core.config import get_settings
    from app.fixtures.providers.espn import EspnFixtureProvider
    from app.fixtures.service import UpcomingMatchesService
    from app.fixtures.window import PARIS

    # Midnight keeps matches that already kicked off. A window starting at "now" drops them.
    start = datetime.now(PARIS).replace(hour=0, minute=0, second=0, microsecond=0)
    UpcomingMatchesService(session, EspnFixtureProvider(), get_settings()).sync(days=2, now=start)


def cycle() -> None:
    from app.analysis.tracking import experiment_report, record_experiments
    from app.db.session import SessionLocal

    with SessionLocal() as session:
        readings = _readings(session)
        recorded = record_experiments(session, readings)
        report = experiment_report(session)
    public: dict = {}
    from app.analysis.briefing import collect_public, write_brief
    from app.analysis.empire import archive_information
    from app.db.session import SessionLocal as ArchiveSession

    try:
        public = collect_public()
        with ArchiveSession() as session:
            empire = archive_information(session, readings, public)
        brief = write_brief(readings, report, public, empire)
        _log(
            "empire "
            f"total={empire['total']} ajoutes={empire['added']} scores={empire['results']} "
            f"articles={empire['headlines']} classements={empire['standings']}"
        )
    except Exception as exc:
        _log(f"veille_failed {exc}")
    with SessionLocal() as session:
        try:
            _refresh_scores(session)
        except Exception as exc:
            _log(f"refresh_scores_failed {exc}")
        settled_again = record_experiments(session, [])
        report = experiment_report(session)
        if public:
            empire = archive_information(session, readings, public)
            write_brief(readings, report, public, empire)
    parts = [
        f"{item['strategy']}: {item['won']}/{item['settled']} profit={item['paper_profit']}"
        for item in report
    ]
    summary = ", ".join(parts) if parts else "aucun résultat réel"
    _log(
        "paris_fictifs "
        f"crees={recorded['created']} regles={recorded['settled'] + settled_again['settled']} "
        f"{summary}"
    )


def main() -> None:
    _log("amelioration demarree. Mise imaginaire de 1. Aucun score n'est inventé.")
    while True:
        try:
            cycle()
        except Exception:
            _log(traceback.format_exc().replace("\n", " | "))
        time.sleep(PAUSE_SECONDS)


if __name__ == "__main__":
    main()
