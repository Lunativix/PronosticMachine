"""Signal robustness. This score is not a win probability and is not probability × 100."""

from __future__ import annotations

from dataclasses import dataclass

# Weights sum to 1. Each input is clipped to [0, 1] before weighting.
WEIGHTS: dict[str, float] = {
    "data_quality": 0.16,
    "history_depth": 0.14,
    "calibration": 0.12,
    "model_agreement": 0.10,
    "prediction_stability": 0.08,
    "odds_stability": 0.08,
    "information_completeness": 0.06,
    "market_importance": 0.10,
    "historical_market_performance": 0.08,
    "edge_support": 0.08,
}

MARKET_IMPORTANCE = {
    "1X2": 0.90,
    "double_chance": 0.82,
    "draw_no_bet": 0.78,
    "over_under": 0.86,
    "btts": 0.80,
    "handicap": 0.62,
}

LEVELS = (
    (85, "VERY_HIGH"),
    (70, "HIGH"),
    (55, "MEDIUM"),
    (40, "LOW"),
    (0, "VERY_LOW"),
)

LEVEL_LABELS = {
    "VERY_HIGH": "Confiance élevée",
    "HIGH": "Confiance élevée",
    "MEDIUM": "Confiance moyenne",
    "LOW": "Confiance faible",
    "VERY_LOW": "Confiance faible",
}


def _clip(value: float) -> float:
    return float(min(1.0, max(0.0, value)))


def confidence_level(score: float) -> str:
    for threshold, name in LEVELS:
        if score >= threshold:
            return name
    return "VERY_LOW"


@dataclass(frozen=True)
class ConfidenceInputs:
    """Missing evidence must be passed as None. It is never treated as perfect evidence."""

    data_quality: float
    history_matches: int
    calibration_score: float | None
    model_agreement: float | None
    prediction_stability: float | None
    odds_volatility: float | None
    information_completeness: float | None
    market: str
    historical_market_performance: float | None
    edge: float | None
    odds_present: bool


class ConfidenceEngine:
    """Documented score in [0, 100].

    confidence = 100 * sum(weight_i * component_i)

    Components in [0, 1]:
    - data_quality: supplied completeness of the match record
    - history_depth: min(history_matches / 30, 1)
    - calibration: supplied historical calibration, else 0.45 (unknown)
    - model_agreement: 1 - mean absolute gap between models, else 0.45
    - prediction_stability: 1 - |p_new - p_previous|, else 0.50
    - odds_stability: 1 - min(price_std / 0.25, 1) when several prices exist;
      0.35 when the price is missing; 0.55 when only one price exists
    - information_completeness: injuries/lineups known, else 0.40
    - market_importance: fixed table, unknown market 0.50
    - historical_market_performance: past hit rate on this market, else 0.50
    - edge_support: clip(edge / 0.12, 0, 1) only when a real price exists, else 0

    A high model probability does not enter this formula.
    """

    def score(self, inputs: ConfidenceInputs) -> dict[str, float | str | dict[str, float]]:
        odds_stability = 0.35
        if inputs.odds_present and inputs.odds_volatility is None:
            odds_stability = 0.55
        elif inputs.odds_volatility is not None:
            odds_stability = 1.0 - min(inputs.odds_volatility / 0.25, 1.0)
        components = {
            "data_quality": _clip(inputs.data_quality),
            "history_depth": _clip(inputs.history_matches / 30.0),
            "calibration": 0.45 if inputs.calibration_score is None else _clip(inputs.calibration_score),
            "model_agreement": 0.45 if inputs.model_agreement is None else _clip(inputs.model_agreement),
            "prediction_stability": 0.50 if inputs.prediction_stability is None else _clip(inputs.prediction_stability),
            "odds_stability": _clip(odds_stability),
            "information_completeness": 0.40
            if inputs.information_completeness is None
            else _clip(inputs.information_completeness),
            "market_importance": MARKET_IMPORTANCE.get(inputs.market, 0.50),
            "historical_market_performance": 0.50
            if inputs.historical_market_performance is None
            else _clip(inputs.historical_market_performance),
            "edge_support": 0.0 if inputs.edge is None or not inputs.odds_present else _clip(inputs.edge / 0.12),
        }
        raw = sum(WEIGHTS[name] * value for name, value in components.items())
        score = round(100.0 * raw, 2)
        level = confidence_level(score)
        return {
            "confidence_score": score,
            "confidence_level": level,
            "confidence_label": LEVEL_LABELS[level],
            "components": components,
        }
