"""Signal quality is a data-and-model score from 0 to 100, not a win probability.

Components and weights:
- data_quality 0.20: feature completeness in [0, 1]
- history_depth 0.15: min(prior matches, 30) / 30 for the thinner team
- calibration 0.15: 1 - min(ECE, 1). Unknown ECE uses 0.5, never 1.
- model_agreement 0.10: 1 - mean absolute gap between base models. Unknown uses 0.5.
- edge 0.10: clip(edge / 0.15, 0, 1) when edge is positive, else 0
- ev 0.10: clip(ev / 0.20, 0, 1) when EV is positive, else 0
- market_quality 0.10: bookmaker coverage times price agreement
- confidence 0.10: 1 - normalized entropy of the probability vector

signal_quality = 100 * sum(weight * component)
"""

from __future__ import annotations

WEIGHTS = {
    "data_quality": 0.20,
    "history_depth": 0.15,
    "calibration": 0.15,
    "model_agreement": 0.10,
    "edge": 0.10,
    "ev": 0.10,
    "market_quality": 0.10,
    "confidence": 0.10,
}


def _clip(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return float(max(low, min(high, value)))


def market_quality_component(bookmaker_count: int, dispersion: float | None) -> float:
    if bookmaker_count <= 0:
        return 0.0
    coverage = _clip(bookmaker_count / 5.0)
    if bookmaker_count == 1 or dispersion is None:
        agreement = 0.6
    else:
        agreement = 1.0 - _clip(dispersion / 0.15)
    return _clip(0.5 * coverage + 0.5 * agreement)


def signal_quality_score(
    *,
    data_quality: float,
    history_matches: int,
    expected_calibration_error: float | None,
    model_agreement: float | None,
    edge: float | None,
    expected_value: float | None,
    bookmaker_count: int,
    odds_dispersion: float | None,
    confidence: float | None,
) -> tuple[float, dict[str, float]]:
    components = {
        "data_quality": _clip(data_quality),
        "history_depth": _clip(history_matches / 30.0),
        "calibration": 0.5
        if expected_calibration_error is None
        else 1.0 - _clip(expected_calibration_error),
        "model_agreement": 0.5 if model_agreement is None else _clip(model_agreement),
        "edge": _clip((edge or 0.0) / 0.15) if (edge or 0.0) > 0 else 0.0,
        "ev": _clip((expected_value or 0.0) / 0.20) if (expected_value or 0.0) > 0 else 0.0,
        "market_quality": market_quality_component(bookmaker_count, odds_dispersion),
        "confidence": 0.0 if confidence is None else _clip(confidence),
    }
    score = 100.0 * sum(WEIGHTS[name] * value for name, value in components.items())
    return round(score, 2), components


def classify_state(
    *,
    history_matches: int,
    min_history_matches: int,
    confidence: float | None,
    min_model_confidence: float,
    edge: float | None,
    expected_value: float | None,
    min_edge: float,
    min_ev: float,
    has_odds: bool,
) -> str:
    if history_matches < min_history_matches:
        return "INSUFFICIENT_DATA"
    if confidence is None or confidence < min_model_confidence:
        return "LOW_CONFIDENCE"
    if not has_odds:
        return "NO_SIGNAL"
    if edge is None or expected_value is None or edge < min_edge or expected_value < min_ev:
        return "NO_SIGNAL"
    return "SIGNAL"
