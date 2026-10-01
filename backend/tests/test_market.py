"""Market math, value, and staking."""

from __future__ import annotations

import pytest

from app.betting.bankroll import open_bankroll, settle
from app.betting.odds_math import (
    devig,
    expected_value,
    kelly_fraction_full,
    proportional_probabilities,
    shin_probabilities,
    stake_fraction,
)
from app.betting.signal_quality import classify_state, signal_quality_score


def test_proportional_probabilities_remove_margin() -> None:
    odds = {"home": 2.0, "draw": 3.4, "away": 4.0}
    probabilities = proportional_probabilities(odds)
    assert sum(probabilities.values()) == pytest.approx(1.0)
    assert probabilities["home"] > probabilities["away"]


def test_shin_probabilities_sum_to_one() -> None:
    probabilities = shin_probabilities({"home": 1.8, "draw": 3.6, "away": 4.5})
    assert sum(probabilities.values()) == pytest.approx(1.0)
    assert all(value > 0 for value in probabilities.values())


def test_devig_methods() -> None:
    odds = {"home": 2.1, "draw": 3.3, "away": 3.6}
    assert sum(devig(odds, "proportional").values()) == pytest.approx(1.0)
    assert sum(devig(odds, "shin").values()) == pytest.approx(1.0)


def test_expected_value() -> None:
    assert expected_value(0.58, 2.0) == pytest.approx(0.16)


def test_kelly_is_capped() -> None:
    full = kelly_fraction_full(0.6, 2.2)
    capped = stake_fraction(0.6, 2.2, "KELLY", max_stake_percent=0.02)
    fractional = stake_fraction(0.6, 2.2, "FRACTIONAL_KELLY", kelly_fraction=0.25, max_stake_percent=0.02)
    assert full > 0.02
    assert capped == pytest.approx(0.02)
    assert fractional <= 0.02


def test_negative_edge_kelly_is_zero() -> None:
    assert kelly_fraction_full(0.2, 2.0) == 0.0


def test_bankroll_cannot_exceed_cap() -> None:
    state = open_bankroll(1000)
    amount, pnl = settle(
        state,
        probability=0.7,
        odds=2.0,
        won=True,
        method="FRACTIONAL_KELLY",
        kelly_fraction=1.0,
        max_stake_percent=0.02,
    )
    assert amount == pytest.approx(20.0)
    assert pnl == pytest.approx(20.0)
    assert state.bankroll == pytest.approx(1020.0)


def test_signal_quality_is_not_a_probability_label() -> None:
    score, components = signal_quality_score(
        data_quality=1,
        history_matches=30,
        expected_calibration_error=0.02,
        model_agreement=0.9,
        edge=0.07,
        expected_value=0.16,
        bookmaker_count=4,
        odds_dispersion=0.02,
        confidence=0.4,
    )
    assert 0 <= score <= 100
    assert set(components) == {
        "data_quality",
        "history_depth",
        "calibration",
        "model_agreement",
        "edge",
        "ev",
        "market_quality",
        "confidence",
    }
    assert classify_state(
        history_matches=2,
        min_history_matches=5,
        confidence=0.9,
        min_model_confidence=0.55,
        edge=0.2,
        expected_value=0.2,
        min_edge=0.04,
        min_ev=0.03,
        has_odds=True,
    ) == "INSUFFICIENT_DATA"
