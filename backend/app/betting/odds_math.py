"""Market probabilities, expected value, and staking. These functions are pure."""

from __future__ import annotations

import math

import numpy as np
from scipy.optimize import brentq

SELECTIONS = ("home", "draw", "away")


def implied_probabilities(odds: dict[str, float]) -> dict[str, float]:
    prices = {key: float(odds[key]) for key in odds}
    if any(price <= 1.0 or not math.isfinite(price) for price in prices.values()):
        raise ValueError("Odds must be finite and strictly greater than 1.")
    raw = {key: 1.0 / price for key, price in prices.items()}
    return raw


def overround(raw: dict[str, float]) -> float:
    return float(sum(raw.values()) - 1.0)


def proportional_probabilities(odds: dict[str, float]) -> dict[str, float]:
    raw = implied_probabilities(odds)
    total = sum(raw.values())
    return {key: value / total for key, value in raw.items()}


def shin_probabilities(odds: dict[str, float]) -> dict[str, float]:
    """Shin (1993) margin removal for a complete market."""
    raw = implied_probabilities(odds)
    total = sum(raw.values())
    if total <= 1.0 + 1e-9:
        return {key: value / total for key, value in raw.items()}

    def prices(z: float) -> dict[str, float]:
        output: dict[str, float] = {}
        for key, quote in raw.items():
            inside = z * z + 4.0 * (1.0 - z) * (quote * quote) / total
            output[key] = (math.sqrt(max(inside, 0.0)) - z) / (2.0 * (1.0 - z))
        return output

    def gap(z: float) -> float:
        return sum(prices(z).values()) - 1.0

    z_root = brentq(gap, 1e-9, 1.0 - 1e-9)
    cleaned = prices(z_root)
    scale = sum(cleaned.values())
    return {key: value / scale for key, value in cleaned.items()}


def devig(odds: dict[str, float], method: str = "shin") -> dict[str, float]:
    if method == "proportional":
        return proportional_probabilities(odds)
    if method == "shin":
        return shin_probabilities(odds)
    raise ValueError(f"Unknown margin method: {method}")


def expected_value(probability: float, odds: float) -> float:
    if not 0.0 <= probability <= 1.0:
        raise ValueError("Probability must be inside [0, 1].")
    if odds <= 1.0:
        raise ValueError("Odds must be greater than 1.")
    return float(probability * odds - 1.0)


def model_edge(model_probability: float, market_probability: float) -> float:
    return float(model_probability - market_probability)


def kelly_fraction_full(probability: float, odds: float) -> float:
    b = odds - 1.0
    if b <= 0:
        return 0.0
    q = 1.0 - probability
    fraction = (b * probability - q) / b
    return float(max(0.0, fraction))


def stake_fraction(
    probability: float,
    odds: float,
    method: str,
    *,
    kelly_fraction: float = 0.25,
    max_stake_percent: float = 0.02,
    percent: float = 0.01,
    fixed_stake: float = 10.0,
    bankroll: float = 1000.0,
) -> float:
    """Return a fraction of bankroll. The fraction never exceeds the risk cap."""
    cap = max(0.0, min(max_stake_percent, 1.0))
    if method == "FIXED_STAKE":
        if bankroll <= 0:
            return 0.0
        return float(min(cap, fixed_stake / bankroll))
    if method == "PERCENT_BANKROLL":
        return float(min(cap, max(0.0, percent)))
    if method == "KELLY":
        return float(min(cap, kelly_fraction_full(probability, odds)))
    if method == "FRACTIONAL_KELLY":
        return float(min(cap, kelly_fraction * kelly_fraction_full(probability, odds)))
    raise ValueError(f"Unknown staking method: {method}")


def stake_amount(bankroll: float, fraction: float) -> float:
    if bankroll <= 0 or fraction <= 0:
        return 0.0
    amount = bankroll * fraction
    return float(min(amount, bankroll))


def distribution_confidence(probabilities: dict[str, float]) -> float:
    values = np.array([probabilities[key] for key in probabilities], dtype=float)
    values = np.clip(values, 1e-12, 1.0)
    values = values / values.sum()
    entropy = float(-np.sum(values * np.log(values)))
    max_entropy = math.log(len(values))
    if max_entropy == 0:
        return 1.0
    return float(1.0 - entropy / max_entropy)


def apply_slippage(odds: float, slippage: float, commission: float) -> float:
    """Reduce the net price. slippage and commission are fractions in [0, 1)."""
    if odds <= 1:
        raise ValueError("Odds must be greater than 1.")
    net = 1.0 + (odds - 1.0) * (1.0 - slippage) * (1.0 - commission)
    return float(max(net, 1.0001))
