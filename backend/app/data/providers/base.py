"""Provider contracts. The modeling code never imports a vendor SDK."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

import pandas as pd


class ProviderDisabled(RuntimeError):
    """The provider is configured but its credential is empty."""


class BaseDataProvider(ABC):
    name: str

    @abstractmethod
    def load(self) -> pd.DataFrame:
        raise NotImplementedError


class FootballDataProvider(BaseDataProvider):
    """Normalized football matches."""


class OddsDataProvider(BaseDataProvider):
    """Normalized odds snapshots."""


class StatsDataProvider(BaseDataProvider):
    """Optional team or player statistics."""


class FileProvider(FootballDataProvider):
    def __init__(self, path: Path) -> None:
        self.path = path
        self.name = path.suffix.lower().lstrip(".") or "file"
