"""Sport adapters. V1 implements football only."""

from __future__ import annotations

from abc import ABC, abstractmethod


class SportAdapter(ABC):
    code: str

    @abstractmethod
    def market(self) -> str:
        raise NotImplementedError


class FootballAdapter(SportAdapter):
    code = "football"

    def market(self) -> str:
        return "1X2"
