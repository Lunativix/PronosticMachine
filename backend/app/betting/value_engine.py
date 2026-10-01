"""Value engine. Outputs are statistical signals, never guaranteed outcomes."""

from __future__ import annotations

from dataclasses import dataclass

from app.betting.odds_math import devig, distribution_confidence, expected_value, model_edge, overround
from app.betting.signal_quality import classify_state, signal_quality_score


@dataclass(frozen=True)
class ValueResult:
    selection: str
    odds: float
    model_probability: float
    market_probability: float
    edge: float
    expected_value: float
    market_margin: float
    confidence: float
    signal_quality: float
    state: str
    components: dict[str, float]
    label: str


def analyze_market(
    model_probabilities: dict[str, float],
    odds: dict[str, float],
    *,
    method: str = "shin",
    data_quality: float,
    history_matches: int,
    expected_calibration_error: float | None,
    model_agreement: float | None,
    bookmaker_count: int,
    odds_dispersion: float | None,
    min_edge: float,
    min_ev: float,
    min_model_confidence: float,
    min_history_matches: int,
) -> list[ValueResult]:
    market = devig(odds, method)
    raw = {key: 1.0 / odds[key] for key in odds}
    margin = overround(raw)
    confidence = distribution_confidence(model_probabilities)
    results: list[ValueResult] = []
    for selection, price in odds.items():
        model_p = float(model_probabilities[selection])
        market_p = float(market[selection])
        edge = model_edge(model_p, market_p)
        ev = expected_value(model_p, price)
        quality, components = signal_quality_score(
            data_quality=data_quality,
            history_matches=history_matches,
            expected_calibration_error=expected_calibration_error,
            model_agreement=model_agreement,
            edge=edge,
            expected_value=ev,
            bookmaker_count=bookmaker_count,
            odds_dispersion=odds_dispersion,
            confidence=confidence,
        )
        state = classify_state(
            history_matches=history_matches,
            min_history_matches=min_history_matches,
            confidence=confidence,
            min_model_confidence=min_model_confidence,
            edge=edge,
            expected_value=ev,
            min_edge=min_edge,
            min_ev=min_ev,
            has_odds=True,
        )
        results.append(
            ValueResult(
                selection=selection,
                odds=price,
                model_probability=model_p,
                market_probability=market_p,
                edge=edge,
                expected_value=ev,
                market_margin=margin,
                confidence=confidence,
                signal_quality=quality,
                state=state,
                components=components,
                label="Model Signal" if state == "SIGNAL" else state,
            )
        )
    return results
