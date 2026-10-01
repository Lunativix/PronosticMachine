"""Download real match files and store them through the normal importer."""

from __future__ import annotations

from pathlib import Path

import httpx
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.data.providers.csv_provider import DIVISIONS
from app.data.providers.football_data_uk import (
    RemoteDataError,
    current_season_code,
    download_division,
    previous_season_code,
)
from app.data.providers.registry import football_provider
from app.services.import_service import import_frame


def sync_real_matches(
    session: Session,
    competitions: list[str] | None = None,
    season: str | None = None,
    settings: Settings | None = None,
) -> dict[str, object]:
    settings = settings or get_settings()
    codes = [code.upper() for code in (competitions or ["E0"])]
    unknown = [code for code in codes if code not in DIVISIONS]
    if unknown:
        raise ValueError(f"Unknown competitions: {', '.join(unknown)}")
    requested = season or current_season_code()
    reports: list[dict[str, object]] = []
    with httpx.Client(timeout=40.0, follow_redirects=True) as client:
        for code in codes:
            used_season, path = _download_with_fallback(code, requested, settings.raw_dir, client)
            frame = football_provider(settings, path).load()
            source = f"football-data.co.uk:{code}:{used_season}"
            report = import_frame(session, frame, source=source)
            reports.append(
                {
                    "competition": DIVISIONS[code],
                    "code": code,
                    "season": used_season,
                    "file": str(path),
                    "source": source,
                    **report.as_dict(),
                }
            )
    return {"provider": "football-data.co.uk", "imports": reports}


def _download_with_fallback(
    code: str,
    season: str,
    raw_dir: Path,
    client: httpx.Client,
) -> tuple[str, Path]:
    candidates = [season]
    previous = previous_season_code(season)
    if previous not in candidates:
        candidates.append(previous)
    last_error: Exception | None = None
    for candidate in candidates:
        destination = raw_dir / "football-data" / candidate / f"{code}.csv"
        try:
            return candidate, download_division(code, candidate, destination, client)
        except RemoteDataError as exc:
            last_error = exc
    raise RemoteDataError(str(last_error) if last_error else f"No file for {code}")
