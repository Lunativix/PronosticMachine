"""Real historical results from the public football-data.co.uk files. No API key."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import httpx

from app.data.providers.csv_provider import DIVISIONS

BASE_URL = "https://www.football-data.co.uk/mmz4281"


class RemoteDataError(RuntimeError):
    """The public file could not be downloaded."""


def current_season_code(today: datetime | None = None) -> str:
    moment = today or datetime.now(timezone.utc)
    start = moment.year if moment.month >= 7 else moment.year - 1
    return f"{str(start)[2:]}{str(start + 1)[2:]}"


def previous_season_code(season: str) -> str:
    start = int(season[:2])
    end = int(season[2:])
    return f"{start - 1:02d}{end - 1:02d}"


def file_url(division: str, season: str) -> str:
    code = division.upper()
    if code not in DIVISIONS:
        raise ValueError(f"Unknown competition code: {division}. Expected one of {', '.join(sorted(DIVISIONS))}.")
    if len(season) != 4 or not season.isdigit():
        raise ValueError("Season must look like 2526 for 2025/2026.")
    return f"{BASE_URL}/{season}/{code}.csv"


def download_division(division: str, season: str, destination: Path, client: httpx.Client | None = None) -> Path:
    url = file_url(division, season)
    own_client = client is None
    http = client or httpx.Client(timeout=40.0, follow_redirects=True)
    try:
        response = http.get(url)
    finally:
        if own_client:
            http.close()
    if response.status_code == 404:
        raise RemoteDataError(f"No public file for {division.upper()} {season}.")
    response.raise_for_status()
    text = response.content.decode("utf-8-sig")
    header = text.splitlines()[0] if text else ""
    if "HomeTeam" not in header:
        raise RemoteDataError(f"Unexpected file from {url}.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(text, encoding="utf-8")
    return destination
