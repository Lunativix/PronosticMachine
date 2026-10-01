"""Record-level validation. Critical failures are reported, never dropped silently."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

import pandas as pd


@dataclass
class DataQualityReport:
    records_total: int = 0
    records_valid: int = 0
    records_invalid: int = 0
    missing_values: int = 0
    duplicates: int = 0
    future_leakage: int = 0
    warnings: list[dict[str, object]] = field(default_factory=list)
    errors: list[dict[str, object]] = field(default_factory=list)

    def as_dict(self) -> dict[str, object]:
        return {
            "records_total": self.records_total,
            "records_valid": self.records_valid,
            "records_invalid": self.records_invalid,
            "missing_values": self.missing_values,
            "duplicates": self.duplicates,
            "future_leakage": self.future_leakage,
            "warnings": self.warnings,
            "errors": self.errors,
        }


def _error(report: DataQualityReport, row: int, code: str, message: str) -> None:
    report.errors.append({"row": row, "code": code, "message": message})


def _warn(report: DataQualityReport, row: int, code: str, message: str) -> None:
    report.warnings.append({"row": row, "code": code, "message": message})


def validate_matches(frame: pd.DataFrame, *, as_of: datetime | None = None) -> tuple[pd.DataFrame, DataQualityReport]:
    report = DataQualityReport(records_total=int(len(frame)))
    if frame.empty:
        return frame.copy(), report

    work = frame.copy()
    work["_row"] = work.index.astype(int)
    work["_valid"] = True
    required = ["kickoff", "home_team", "away_team", "competition", "season"]
    for column in required:
        if column not in work.columns:
            work[column] = pd.NA
    missing_mask = work[required].isna().any(axis=1) | (work["home_team"].astype(str).str.strip() == "")
    for idx in work.index[missing_mask]:
        report.missing_values += int(work.loc[idx, required].isna().sum())
        _error(report, int(work.loc[idx, "_row"]), "missing_critical", "Critical match fields are missing.")
    work.loc[missing_mask, "_valid"] = False

    kickoff = pd.to_datetime(work["kickoff"], utc=True, errors="coerce")
    bad_dates = kickoff.isna() & work["_valid"]
    for idx in work.index[bad_dates]:
        _error(report, int(work.loc[idx, "_row"]), "invalid_date", "Kickoff could not be parsed.")
    work.loc[bad_dates, "_valid"] = False
    work["kickoff"] = kickoff

    if "home_goals" in work.columns:
        for side in ("home_goals", "away_goals"):
            if side not in work.columns:
                work[side] = pd.NA
            numeric = pd.to_numeric(work[side], errors="coerce")
            impossible = numeric.notna() & ((numeric < 0) | (numeric > 25))
            for idx in work.index[impossible]:
                _error(report, int(work.loc[idx, "_row"]), "impossible_score", f"{side} is outside 0..25.")
            work.loc[impossible, "_valid"] = False
            work[side] = numeric

    if "status" not in work.columns:
        work["status"] = "scheduled"
    finished = work["status"].astype(str).str.lower().eq("finished") & work["_valid"]
    incomplete_score = finished & (work["home_goals"].isna() | work["away_goals"].isna())
    for idx in work.index[incomplete_score]:
        _error(report, int(work.loc[idx, "_row"]), "incomplete_score", "Finished match is missing a score.")
    work.loc[incomplete_score, "_valid"] = False

    same_team = work["_valid"] & work["home_team"].astype(str).str.casefold().eq(
        work["away_team"].astype(str).str.casefold()
    )
    for idx in work.index[same_team]:
        _error(report, int(work.loc[idx, "_row"]), "same_team", "Home and away teams are identical.")
    work.loc[same_team, "_valid"] = False

    keys = ["competition", "season", "kickoff", "home_team", "away_team"]
    duplicated = work["_valid"] & work.duplicated(keys, keep="first")
    report.duplicates = int(duplicated.sum())
    for idx in work.index[duplicated]:
        _error(report, int(work.loc[idx, "_row"]), "duplicate", "Duplicate match identity in the batch.")
    work.loc[duplicated, "_valid"] = False

    if as_of is not None:
        cutoff = pd.Timestamp(as_of)
        if cutoff.tzinfo is None:
            cutoff = cutoff.tz_localize(timezone.utc)
        leaked = work["_valid"] & work["kickoff"].gt(cutoff) & finished
        report.future_leakage = int(leaked.sum())
        for idx in work.index[leaked]:
            _error(
                report,
                int(work.loc[idx, "_row"]),
                "future_leakage",
                "Finished result is timestamped after the training cutoff.",
            )
        work.loc[leaked, "_valid"] = False

    _check_stats(work, report)
    _check_odds(work, report)

    report.records_valid = int(work["_valid"].sum())
    report.records_invalid = report.records_total - report.records_valid
    valid = work.loc[work["_valid"]].drop(columns=["_valid", "_row"])
    return valid.reset_index(drop=True), report


def _check_stats(work: pd.DataFrame, report: DataQualityReport) -> None:
    pairs = [("shots_home", "sot_home"), ("shots_away", "sot_away")]
    for shots, sot in pairs:
        if shots not in work.columns or sot not in work.columns:
            continue
        shot_v = pd.to_numeric(work[shots], errors="coerce")
        sot_v = pd.to_numeric(work[sot], errors="coerce")
        bad = shot_v.notna() & sot_v.notna() & (sot_v > shot_v)
        for idx in work.index[bad]:
            _warn(report, int(work.loc[idx, "_row"]), "impossible_stat", f"{sot} exceeds {shots}.")
            work.loc[idx, shots] = pd.NA
            work.loc[idx, sot] = pd.NA
    for column in ("possession_home", "possession_away"):
        if column not in work.columns:
            continue
        values = pd.to_numeric(work[column], errors="coerce")
        bad = values.notna() & ((values < 0) | (values > 100))
        for idx in work.index[bad]:
            _warn(report, int(work.loc[idx, "_row"]), "impossible_stat", f"{column} is outside 0..100.")
            work.loc[idx, column] = pd.NA


def _check_odds(work: pd.DataFrame, report: DataQualityReport) -> None:
    for column in ("odds_home", "odds_draw", "odds_away"):
        if column not in work.columns:
            continue
        values = pd.to_numeric(work[column], errors="coerce")
        bad = values.notna() & (values <= 1.0)
        for idx in work.index[bad]:
            _error(report, int(work.loc[idx, "_row"]), "invalid_odds", f"{column} must be greater than 1.")
        work.loc[bad, "_valid"] = False
    if "odds_timestamp" in work.columns:
        stamped = pd.to_datetime(work["odds_timestamp"], utc=True, errors="coerce")
        late = work["_valid"] & stamped.notna() & work["kickoff"].notna() & stamped.gt(work["kickoff"])
        report.future_leakage += int(late.sum())
        for idx in work.index[late]:
            _warn(
                report,
                int(work.loc[idx, "_row"]),
                "post_kickoff_odds",
                "Odds timestamp is after kickoff and will be excluded from pre-match features.",
            )
            for column in ("odds_home", "odds_draw", "odds_away"):
                if column in work.columns:
                    work.loc[idx, column] = pd.NA
