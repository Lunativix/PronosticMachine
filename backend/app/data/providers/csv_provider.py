"""CSV ingestion for the canonical schema and the football-data.co.uk export."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from app.data.providers.base import FileProvider

DIVISIONS = {
    "E0": "Premier League",
    "E1": "Championship",
    "SP1": "La Liga",
    "I1": "Serie A",
    "D1": "Bundesliga",
    "F1": "Ligue 1",
    "N1": "Eredivisie",
    "P1": "Primeira Liga",
}


class CsvFootballProvider(FileProvider):
    name = "csv"

    def load(self) -> pd.DataFrame:
        frame = pd.read_csv(self.path)
        if {"HomeTeam", "AwayTeam", "FTHG"}.issubset(frame.columns):
            return _from_football_data(frame, self.path)
        return _from_canonical(frame)


def _from_football_data(frame: pd.DataFrame, path: Path) -> pd.DataFrame:
    division = frame["Div"].astype(str) if "Div" in frame.columns else "UNK"
    dates = pd.to_datetime(frame["Date"], dayfirst=True, utc=True, errors="coerce")
    seasons = dates.map(_season_name)
    rows = pd.DataFrame(
        {
            "sport": "football",
            "competition": division.map(lambda code: DIVISIONS.get(code, code)),
            "competition_code": division,
            "season": seasons,
            "kickoff": dates,
            "home_team": frame["HomeTeam"].astype(str),
            "away_team": frame["AwayTeam"].astype(str),
            "home_goals": pd.to_numeric(frame["FTHG"], errors="coerce"),
            "away_goals": pd.to_numeric(frame["FTAG"], errors="coerce"),
            "status": "finished",
            "shots_home": _num(frame, "HS"),
            "shots_away": _num(frame, "AS"),
            "sot_home": _num(frame, "HST"),
            "sot_away": _num(frame, "AST"),
            "corners_home": _num(frame, "HC"),
            "corners_away": _num(frame, "AC"),
            "yellow_home": _num(frame, "HY"),
            "yellow_away": _num(frame, "AY"),
            "red_home": _num(frame, "HR"),
            "red_away": _num(frame, "AR"),
            "odds_home": _first(frame, ["B365H", "PSH", "AvgH"]),
            "odds_draw": _first(frame, ["B365D", "PSD", "AvgD"]),
            "odds_away": _first(frame, ["B365A", "PSA", "AvgA"]),
            "odds_open_home": _num(frame, "B365H") if "PSH" in frame.columns else pd.NA,
            "odds_dispersion": _dispersion(frame),
            "bookmaker": "B365" if "B365H" in frame.columns else "market",
            "source": f"csv:{path.name}",
        }
    )
    return rows


def _from_canonical(frame: pd.DataFrame) -> pd.DataFrame:
    renamed = frame.copy()
    if "kickoff" in renamed.columns:
        renamed["kickoff"] = pd.to_datetime(renamed["kickoff"], utc=True, errors="coerce")
    renamed["sport"] = renamed.get("sport", "football")
    return renamed


def _season_name(value: object) -> str:
    if pd.isna(value):
        return "unknown"
    stamp = pd.Timestamp(value)
    start = stamp.year if stamp.month >= 7 else stamp.year - 1
    return f"{start}/{start + 1}"


def _num(frame: pd.DataFrame, column: str) -> pd.Series:
    if column not in frame.columns:
        return pd.Series([pd.NA] * len(frame))
    return pd.to_numeric(frame[column], errors="coerce")


def _first(frame: pd.DataFrame, columns: list[str]) -> pd.Series:
    for column in columns:
        if column in frame.columns:
            return pd.to_numeric(frame[column], errors="coerce")
    return pd.Series([pd.NA] * len(frame))


def _dispersion(frame: pd.DataFrame) -> pd.Series:
    candidates = [column for column in ("B365H", "PSH", "AvgH", "MaxH") if column in frame.columns]
    if len(candidates) < 2:
        return pd.Series([pd.NA] * len(frame))
    values = frame[candidates].apply(pd.to_numeric, errors="coerce")
    return values.std(axis=1)
