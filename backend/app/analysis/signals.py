"""Signal strength from edge, EV, confidence and data quality. Configurable thresholds."""

from __future__ import annotations

from dataclasses import dataclass

SIGNAL_LABELS = {
    "NO_SIGNAL": "Aucun signal",
    "WEAK_SIGNAL": "Signal faible",
    "MODERATE_SIGNAL": "Signal modéré",
    "STRONG_SIGNAL": "Signal fort",
    "INSUFFICIENT_DATA": "Données insuffisantes",
}


@dataclass(frozen=True)
class SignalConfig:
    min_edge: float = 0.04
    min_ev: float = 0.03
    min_confidence: float = 55.0
    min_data_quality: float = 0.45


class SignalEngine:
    def __init__(self, config: SignalConfig | None = None) -> None:
        self.config = config or SignalConfig()

    def classify(
        self,
        *,
        odds: float | None,
        edge: float | None,
        expected_value: float | None,
        confidence_score: float,
        data_quality: float,
        sufficient_data: bool,
    ) -> str:
        if not sufficient_data or data_quality < self.config.min_data_quality:
            return "INSUFFICIENT_DATA"
        if odds is None or edge is None or expected_value is None:
            return "NO_SIGNAL"
        if (
            edge < self.config.min_edge
            or expected_value < self.config.min_ev
            or confidence_score < self.config.min_confidence
        ):
            return "NO_SIGNAL"
        strong = (
            edge >= self.config.min_edge * 2
            and expected_value >= self.config.min_ev * 2
            and confidence_score >= 70
            and data_quality >= 0.6
        )
        if strong:
            return "STRONG_SIGNAL"
        moderate = (
            edge >= self.config.min_edge * 1.5
            and expected_value >= self.config.min_ev * 1.5
            and confidence_score >= 55
        )
        if moderate:
            return "MODERATE_SIGNAL"
        return "WEAK_SIGNAL"
