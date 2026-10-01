"""Competition catalog. Provider codes stay outside the sync engine."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

CATALOG_PATH = Path(__file__).with_name("competitions.yaml")


@dataclass(frozen=True)
class CompetitionConfig:
    catalog_id: str
    name: str
    country: str
    priority: int
    active: bool
    season: str
    providers: dict[str, str]


def load_competitions(path: Path | None = None) -> list[CompetitionConfig]:
    payload = yaml.safe_load((path or CATALOG_PATH).read_text(encoding="utf-8"))
    rows = []
    for item in payload.get("competitions", []):
        rows.append(
            CompetitionConfig(
                catalog_id=str(item["id"]),
                name=str(item["name"]),
                country=str(item.get("country") or ""),
                priority=int(item.get("priority") or 0),
                active=bool(item.get("active", True)),
                season=str(item.get("season") or ""),
                providers={str(key): str(value) for key, value in (item.get("providers") or {}).items()},
            )
        )
    return rows


def active_competitions(provider: str, only: str | None = None) -> list[CompetitionConfig]:
    selected = []
    for row in load_competitions():
        if not row.active or provider not in row.providers:
            continue
        if only and only.lower() not in {row.catalog_id.lower(), row.name.lower(), row.providers[provider].lower()}:
            continue
        selected.append(row)
    return sorted(selected, key=lambda row: (-row.priority, row.name))
