"""Combined selections. Correlated events are not priced as a naive product."""

from __future__ import annotations

from dataclasses import dataclass, field
from itertools import combinations

import numpy as np

from app.analysis.markets import joint_probability
from app.betting.odds_math import expected_value

MAX_COMBINATION_SIZE = 5
SEARCH_POOL = 12

HIGH_PAIRS = {
    frozenset({("1X2", "home"), ("handicap", "home_-1.5")}),
    frozenset({("1X2", "away"), ("handicap", "away_-1.5")}),
    frozenset({("1X2", "home"), ("draw_no_bet", "home")}),
    frozenset({("1X2", "away"), ("draw_no_bet", "away")}),
    frozenset({("over_under", "over_2.5"), ("btts", "yes")}),
    frozenset({("over_under", "under_2.5"), ("btts", "no")}),
}


@dataclass(frozen=True)
class Leg:
    match_id: int
    match_label: str
    market: str
    selection: str
    odds: float | None
    model_probability: float
    edge: float | None
    expected_value: float | None
    confidence_score: float
    data_quality: float
    signal: str
    score_matrix: np.ndarray | None = field(default=None, compare=False, hash=False)


@dataclass(frozen=True)
class CombinationConfig:
    max_size: int = MAX_COMBINATION_SIZE
    min_confidence: float = 55.0
    min_edge: float = 0.04
    min_data_quality: float = 0.45
    max_correlation: str = "MEDIUM"
    experimental_correlation: bool = False


def correlation_pair(left: Leg, right: Leg) -> tuple[str, str, float | None]:
    """Return risk, status, and a joint probability when one can be estimated."""
    if left.match_id != right.match_id:
        return "LOW", "ASSUMED_INDEPENDENT", None
    pair = frozenset({(left.market, left.selection), (right.market, right.selection)})
    if pair in HIGH_PAIRS or (left.market, left.selection) == (right.market, right.selection):
        risk = "HIGH"
    elif left.market == right.market:
        risk = "HIGH"
    else:
        risk = "MEDIUM"
    matrix = left.score_matrix if left.score_matrix is not None else right.score_matrix
    if matrix is None:
        return risk, "UNKNOWN", None
    joint = joint_probability(
        matrix,
        (left.market, left.selection),
        (right.market, right.selection),
    )
    naive = left.model_probability * right.model_probability
    if naive > 0 and abs(joint - naive) / naive >= 0.25:
        risk = "HIGH"
    elif naive > 0 and abs(joint - naive) / naive >= 0.10 and risk != "HIGH":
        risk = "MEDIUM"
    return risk, "ESTIMATED", joint


def _worst(levels: list[str]) -> str:
    order = {"LOW": 0, "MEDIUM": 1, "HIGH": 2}
    return max(levels, key=lambda item: order[item])


def price_combination(legs: list[Leg]) -> dict[str, object]:
    same_match = len({leg.match_id for leg in legs}) < len(legs)
    risks: list[str] = []
    statuses: list[str] = []
    probability: float | None = 1.0
    for left, right in combinations(legs, 2):
        risk, status, joint = correlation_pair(left, right)
        risks.append(risk)
        statuses.append(status)
        if left.match_id == right.match_id and len(legs) == 2 and status == "ESTIMATED":
            probability = joint
        elif left.match_id == right.match_id and status != "ESTIMATED":
            probability = None
    correlation_risk = _worst(risks) if risks else "LOW"
    if probability is not None and not any(status == "UNKNOWN" for status in statuses):
        if all(leg.match_id != other.match_id for leg, other in combinations(legs, 2)):
            probability = 1.0
            for leg in legs:
                probability *= leg.model_probability
            correlation_status = "ASSUMED_INDEPENDENT"
        elif len(legs) == 2 and "ESTIMATED" in statuses:
            correlation_status = "ESTIMATED"
        elif same_match:
            correlation_status = "UNKNOWN"
            probability = None
        else:
            correlation_status = "ASSUMED_INDEPENDENT"
    else:
        correlation_status = "UNKNOWN" if "UNKNOWN" in statuses or same_match else "ASSUMED_INDEPENDENT"
        if correlation_status == "UNKNOWN":
            probability = None
    odds = None
    if all(leg.odds is not None for leg in legs):
        odds = 1.0
        for leg in legs:
            assert leg.odds is not None
            odds *= leg.odds
    ev = None
    if probability is not None and odds is not None:
        ev = expected_value(probability, odds)
    base = sum(leg.confidence_score for leg in legs) / len(legs)
    factor = 0.92
    if correlation_status == "UNKNOWN":
        factor = 0.60
    elif correlation_status == "ESTIMATED" and correlation_risk == "LOW":
        factor = 0.95
    elif correlation_risk == "MEDIUM":
        factor = 0.75
    elif correlation_risk == "HIGH":
        factor = 0.50
    return {
        "selections": [
            {
                "match_id": leg.match_id,
                "match": leg.match_label,
                "market": leg.market,
                "selection": leg.selection,
                "odds": leg.odds,
                "model_probability": leg.model_probability,
            }
            for leg in legs
        ],
        "combined_odds": None if odds is None else round(odds, 4),
        "combined_probability": None if probability is None else round(probability, 6),
        "combined_ev": None if ev is None else round(ev, 6),
        "confidence_score": round(base * factor, 2),
        "correlation_risk": correlation_risk,
        "correlation_status": correlation_status,
        "same_match": same_match,
        "combination_scope": "SAME_MATCH_COMBINATION" if same_match else "INTER_MATCH",
        "size": len(legs),
    }


class CombinationEngine:
    def __init__(self, config: CombinationConfig | None = None) -> None:
        self.config = config or CombinationConfig()

    def eligible(self, leg: Leg) -> bool:
        if leg.signal in {"NO_SIGNAL", "INSUFFICIENT_DATA"}:
            return False
        if leg.odds is None or leg.edge is None:
            return False
        if leg.confidence_score < self.config.min_confidence:
            return False
        if leg.data_quality < self.config.min_data_quality:
            return False
        if leg.edge < self.config.min_edge:
            return False
        return True

    def build(self, legs: list[Leg]) -> dict[str, list[dict[str, object]]]:
        pool = [leg for leg in legs if self.eligible(leg)]
        pool.sort(key=lambda leg: leg.confidence_score, reverse=True)
        pool = pool[:SEARCH_POOL]
        found: list[dict[str, object]] = []
        seen: set[tuple[tuple[int, str, str], ...]] = set()
        limit = min(self.config.max_size, MAX_COMBINATION_SIZE, len(pool))
        for size in range(2, limit + 1):
            for group in combinations(pool, size):
                signature = tuple(sorted((leg.match_id, leg.market, leg.selection) for leg in group))
                if signature in seen:
                    continue
                seen.add(signature)
                priced = price_combination(list(group))
                if priced["correlation_risk"] == "HIGH" and not self.config.experimental_correlation:
                    continue
                if self.config.max_correlation == "LOW" and priced["correlation_risk"] != "LOW":
                    continue
                found.append(priced)
        return {
            "PRUDENT": _take(_prudent(found), 3),
            "VALUE": _take(_value(found), 3),
            "BALANCED": _take(_balanced(found), 3),
        }


def combine_different_matches(
    legs: list[Leg],
    *,
    min_size: int = 2,
    max_size: int = 3,
    per_size: int = 1,
    limit: int = 3,
    rank,
) -> list[dict[str, object]]:
    """One selection per match. Same-match pairs are left out."""
    unique: dict[int, Leg] = {}
    for leg in legs:
        current = unique.get(leg.match_id)
        if current is None or (leg.model_probability > current.model_probability):
            unique[leg.match_id] = leg
    pool = sorted(unique.values(), key=lambda leg: leg.model_probability, reverse=True)[:SEARCH_POOL]
    by_size: dict[int, list[dict[str, object]]] = {}
    seen: set[tuple[tuple[int, str, str], ...]] = set()
    size_floor = max(2, min_size)
    size_limit = min(max_size, MAX_COMBINATION_SIZE, len(pool))
    for size in range(size_floor, size_limit + 1):
        by_size[size] = []
        for group in combinations(pool, size):
            signature = tuple(sorted((leg.match_id, leg.market, leg.selection) for leg in group))
            if signature in seen or len({leg.match_id for leg in group}) < size:
                continue
            seen.add(signature)
            priced = price_combination(list(group))
            if priced["correlation_risk"] != "LOW" or priced["combined_probability"] is None:
                continue
            priced["note"] = "Matchs différents. Échantillon court : la confiance reste limitée."
            by_size[size].append(priced)
    chosen: list[dict[str, object]] = []
    for size in range(size_limit, size_floor - 1, -1):
        rows = by_size.get(size) or []
        rows.sort(key=rank)
        kept = 0
        for row in rows:
            if len(chosen) >= limit or kept >= per_size:
                break
            chosen.append(row)
            kept += 1
    return chosen


def stance_label(confidence: float) -> str:
    if confidence >= 70:
        return "Solide"
    if confidence >= 55:
        return "Intéressant"
    if confidence >= 40:
        return "Spéculatif"
    return "Très spéculatif"


def profile_for(*, confidence: float, expected_value: float | None, size: int) -> str | None:
    """High EV never promotes a low-confidence slip into the balanced profile."""
    if confidence >= 70 and 2 <= size <= 3:
        return "PRUDENT"
    if 55 <= confidence < 70 and 3 <= size <= 4:
        return "BALANCED"
    if expected_value is not None and expected_value > 0 and 40 <= confidence < 55 and 2 <= size <= 3:
        return "VALUE"
    return None


def pack_disjoint(
    legs: list[Leg],
    *,
    size: int = 4,
    min_size: int = 3,
    count: int = 1,
    rank_leg,
    exclude: set[int] | None = None,
    max_combined_odds: float | None = None,
) -> list[dict[str, object]]:
    """Distinct multi-match slips. A shorter slip is not a copy of a longer one."""
    blocked = set(exclude or ())
    unique: dict[int, Leg] = {}
    for leg in legs:
        if leg.match_id in blocked:
            continue
        current = unique.get(leg.match_id)
        if current is None or rank_leg(leg) < rank_leg(current):
            unique[leg.match_id] = leg
    ordered = sorted(unique.values(), key=rank_leg)
    target = min(size, MAX_COMBINATION_SIZE)
    chosen: list[dict[str, object]] = []
    used: set[int] = set()
    if max_combined_odds is not None:
        return _pack_under_odds(
            ordered,
            size=target,
            min_size=min_size,
            count=count,
            max_combined_odds=max_combined_odds,
        )
    while len(chosen) < count:
        group = [leg for leg in ordered if leg.match_id not in used][:target]
        if len(group) < min_size:
            break
        priced = price_combination(group)
        if priced["correlation_risk"] != "LOW" or priced["combined_probability"] is None:
            break
        priced["note"] = "Matchs différents. Échantillon court : la confiance reste limitée."
        chosen.append(priced)
        used.update(leg.match_id for leg in group)
    return chosen


def _pack_under_odds(
    ordered: list[Leg],
    *,
    size: int,
    min_size: int,
    count: int,
    max_combined_odds: float,
) -> list[dict[str, object]]:
    """Best positive-EV slips that stay under the odds cap. Probability breaks ties."""
    floor = max(2, min_size)
    candidates: list[dict[str, object]] = []
    for width in range(floor, min(size, len(ordered)) + 1):
        for group in combinations(ordered, width):
            priced = price_combination(list(group))
            odds = priced["combined_odds"]
            ev = priced["combined_ev"]
            probability = priced["combined_probability"]
            if priced["correlation_risk"] != "LOW" or probability is None or odds is None or ev is None:
                continue
            if float(ev) <= 0 or float(odds) > max_combined_odds:
                continue
            priced["note"] = "Matchs différents. EV positif et confiance limitée : lecture spéculative."
            candidates.append(priced)
    candidates.sort(
        key=lambda row: (
            -float(row["combined_ev"]),
            -float(row["combined_probability"]),
        )
    )
    chosen: list[dict[str, object]] = []
    used: set[int] = set()
    for row in candidates:
        ids = {int(item["match_id"]) for item in row["selections"]}
        if ids & used:
            continue
        chosen.append(row)
        used.update(ids)
        if len(chosen) >= count:
            break
    return chosen


def _take(rows: list[dict[str, object]], count: int) -> list[dict[str, object]]:
    return rows[:count]


def _prudent(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    kept = [
        row
        for row in rows
        if row["combination_scope"] == "INTER_MATCH"
        and row["correlation_risk"] == "LOW"
        and row["correlation_status"] == "ASSUMED_INDEPENDENT"
        and row["combined_probability"] is not None
        and float(row["confidence_score"]) >= 60
        and row["combined_odds"] is not None
        and float(row["combined_odds"]) <= 4.0
    ]
    kept.sort(key=lambda row: float(row["confidence_score"]), reverse=True)
    return kept


def _value(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    kept = [
        row
        for row in rows
        if row["combination_scope"] == "INTER_MATCH"
        and row["correlation_risk"] == "LOW"
        and row["combined_ev"] is not None
        and float(row["combined_ev"]) > 0
    ]
    kept.sort(key=lambda row: float(row["combined_ev"]), reverse=True)
    return kept


def _balanced(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    kept = [
        row
        for row in rows
        if row["combined_probability"] is not None
        and row["combined_odds"] is not None
        and float(row["confidence_score"]) >= 50
    ]
    kept.sort(key=lambda row: abs(float(row["combined_odds"]) - 2.2))
    return kept
