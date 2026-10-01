"""Canonical JSON import."""

from __future__ import annotations

import json

import pandas as pd

from app.data.providers.base import FileProvider


class JsonFootballProvider(FileProvider):
    name = "json"

    def load(self) -> pd.DataFrame:
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        matches = payload["matches"] if isinstance(payload, dict) else payload
        frame = pd.DataFrame(matches)
        if "kickoff" in frame.columns:
            frame["kickoff"] = pd.to_datetime(frame["kickoff"], utc=True, errors="coerce")
        frame["sport"] = frame.get("sport", "football")
        return frame

    def extras(self) -> dict[str, pd.DataFrame]:
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            return {}
        return {
            key: pd.DataFrame(payload.get(key, []))
            for key in ("players", "injuries", "player_statistics", "events")
        }
