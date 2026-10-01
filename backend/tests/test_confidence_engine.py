"""Confidence, edge, EV, and combination rules. Correlated events are not multiplied."""

from __future__ import annotations

import numpy as np

from app.analysis.combinations import CombinationConfig, CombinationEngine, Leg, combine_different_matches, pack_disjoint, price_combination
from app.analysis.confidence import ConfidenceEngine, ConfidenceInputs, confidence_level
from app.analysis.markets import catalog, joint_probability, probability_for
from app.analysis.signals import SignalConfig, SignalEngine
from app.betting.odds_math import expected_value, model_edge
from app.ml.poisson import score_matrix


def _leg(**overrides) -> Leg:
    payload = dict(
        match_id=1,
        match_label="A vs B",
        market="1X2",
        selection="home",
        odds=1.8,
        model_probability=0.62,
        edge=0.08,
        expected_value=0.116,
        confidence_score=72,
        data_quality=0.7,
        signal="MODERATE_SIGNAL",
        score_matrix=None,
    )
    payload.update(overrides)
    return Leg(**payload)


def test_confidence_is_not_probability_times_100() -> None:
    engine = ConfidenceEngine()
    scored = engine.score(
        ConfidenceInputs(
            data_quality=0.2,
            history_matches=1,
            calibration_score=None,
            model_agreement=None,
            prediction_stability=None,
            odds_volatility=None,
            information_completeness=None,
            market="1X2",
            historical_market_performance=None,
            edge=None,
            odds_present=False,
        )
    )
    assert scored["confidence_score"] != 90
    assert float(scored["confidence_score"]) < 55
    assert scored["confidence_level"] in {"VERY_LOW", "LOW"}


def test_confidence_levels() -> None:
    assert confidence_level(39) == "VERY_LOW"
    assert confidence_level(40) == "LOW"
    assert confidence_level(55) == "MEDIUM"
    assert confidence_level(70) == "HIGH"
    assert confidence_level(85) == "VERY_HIGH"


def test_edge_and_ev() -> None:
    assert abs(model_edge(0.68, 0.61) - 0.07) < 1e-9
    assert abs(expected_value(0.68, 1.72) - 0.1696) < 1e-9


def test_missing_odds_produce_no_signal() -> None:
    signal = SignalEngine(SignalConfig()).classify(
        odds=None,
        edge=None,
        expected_value=None,
        confidence_score=80,
        data_quality=0.8,
        sufficient_data=True,
    )
    assert signal == "NO_SIGNAL"


def test_insufficient_data() -> None:
    signal = SignalEngine().classify(
        odds=1.8,
        edge=0.1,
        expected_value=0.2,
        confidence_score=80,
        data_quality=0.2,
        sufficient_data=False,
    )
    assert signal == "INSUFFICIENT_DATA"


def test_independent_product() -> None:
    priced = price_combination(
        [
            _leg(match_id=1, model_probability=0.70, odds=1.5),
            _leg(match_id=2, match_label="C vs D", model_probability=0.80, odds=1.4, selection="away"),
        ]
    )
    assert priced["correlation_status"] == "ASSUMED_INDEPENDENT"
    assert abs(float(priced["combined_probability"]) - 0.56) < 1e-9
    assert abs(float(priced["combined_odds"]) - 2.1) < 1e-9


def test_correlated_same_match_is_not_a_product() -> None:
    matrix = score_matrix(1.6, 1.1, -0.05)
    left = _leg(market="over_under", selection="over_2.5", model_probability=probability_for(matrix, "over_under", "over_2.5"), score_matrix=matrix)
    right = _leg(market="btts", selection="yes", model_probability=probability_for(matrix, "btts", "yes"), score_matrix=matrix)
    naive = left.model_probability * right.model_probability
    joint = joint_probability(matrix, ("over_under", "over_2.5"), ("btts", "yes"))
    priced = price_combination([left, right])
    assert priced["combination_scope"] == "SAME_MATCH_COMBINATION"
    assert priced["correlation_risk"] == "HIGH"
    assert abs(float(priced["combined_probability"]) - joint) < 1e-6
    assert abs(float(priced["combined_probability"]) - naive) > 1e-4


def test_unknown_correlation_does_not_multiply() -> None:
    priced = price_combination(
        [
            _leg(market="over_under", selection="over_2.5", score_matrix=None),
            _leg(market="btts", selection="yes", score_matrix=None),
        ]
    )
    assert priced["correlation_status"] == "UNKNOWN"
    assert priced["combined_probability"] is None
    assert priced["combined_ev"] is None


def test_filter_and_max_size_and_duplicates() -> None:
    legs = [
        _leg(match_id=index, match_label=f"M{index}", selection=f"home", confidence_score=80 - index)
        for index in range(1, 7)
    ]
    legs.append(legs[0])
    built = CombinationEngine(CombinationConfig(max_size=2, min_confidence=55)).build(legs)
    sizes = [row["size"] for rows in built.values() for row in rows]
    assert sizes
    assert max(sizes) <= 2
    for rows in built.values():
        flat = [tuple((item["match_id"], item["market"], item["selection"]) for item in row["selections"]) for row in rows]
        assert len(flat) == len(set(flat))


def test_high_correlation_excluded_unless_experimental() -> None:
    matrix = score_matrix(1.8, 0.9, 0.0)
    legs = [
        _leg(market="1X2", selection="home", confidence_score=100, model_probability=probability_for(matrix, "1X2", "home"), score_matrix=matrix),
        _leg(market="handicap", selection="home_-1.5", confidence_score=100, model_probability=probability_for(matrix, "handicap", "home_-1.5"), score_matrix=matrix),
    ]
    assert CombinationEngine().build(legs) == {"PRUDENT": [], "VALUE": [], "BALANCED": []}
    experimental = CombinationEngine(CombinationConfig(experimental_correlation=True)).build(legs)
    assert experimental["PRUDENT"] == []
    assert experimental["BALANCED"]
    assert experimental["BALANCED"][0]["correlation_risk"] == "HIGH"


def test_catalog_does_not_invent_odds() -> None:
    rows = catalog(score_matrix(1.4, 1.2, 0.0))
    assert all("odds" not in row for row in rows)
    assert {row["market"] for row in rows} >= {"1X2", "double_chance", "draw_no_bet", "over_under", "btts", "handicap"}


def test_recent_form_needs_three_games_and_does_not_invent() -> None:
    from app.analysis.recent_form import form_probabilities
    from app.fixtures.providers.espn import team_goals

    assert form_probabilities([1, 2], [0, 1], [1, 0, 2], [1, 1, 0]) is None
    probs = form_probabilities([1, 2, 1], [0, 1, 1], [0, 1, 2], [1, 1, 0])
    assert probs is not None
    assert abs(sum(probs.values()) - 1) < 1e-6
    scored, conceded = team_goals(
        [{"homeTeamId": "1", "awayTeamId": "2", "homeTeamScore": "2", "awayTeamScore": "0"}],
        "1",
    )
    assert scored == [2.0]
    assert conceded == [0.0]


def test_prediction_change_changes_stability_component() -> None:
    engine = ConfidenceEngine()
    stable = engine.score(
        ConfidenceInputs(0.8, 20, 0.8, 0.8, 1.0, 0.01, 0.7, "1X2", 0.7, 0.08, True)
    )
    moved = engine.score(
        ConfidenceInputs(0.8, 20, 0.8, 0.8, 0.2, 0.2, 0.7, "1X2", 0.7, 0.08, True)
    )
    assert float(stable["confidence_score"]) > float(moved["confidence_score"])


def test_short_sample_combo_keeps_one_selection_per_match() -> None:
    rows = combine_different_matches(
        [
            _leg(match_id=1, model_probability=0.50, odds=1.9),
            _leg(match_id=1, selection="draw", model_probability=0.30, odds=3.2),
            _leg(match_id=2, match_label="C vs D", model_probability=0.55, odds=1.7),
        ],
        max_size=2,
        limit=1,
        rank=lambda row: -float(row["combined_probability"] or 0),
    )
    assert len(rows) == 1
    assert rows[0]["size"] == 2
    assert abs(float(rows[0]["combined_probability"]) - 0.50 * 0.55) < 1e-9
    assert {item["selection"] for item in rows[0]["selections"]} == {"home"}


def test_positive_ev_with_low_confidence_is_not_balanced() -> None:
    from app.analysis.combinations import profile_for, stance_label

    assert profile_for(confidence=42, expected_value=0.42, size=4) is None
    assert profile_for(confidence=42, expected_value=0.42, size=3) == "VALUE"
    assert profile_for(confidence=60, expected_value=0.05, size=3) == "BALANCED"
    assert profile_for(confidence=75, expected_value=0.02, size=2) == "PRUDENT"
    assert stance_label(42) == "Spéculatif"
    assert stance_label(72) == "Solide"


def test_value_pack_stays_under_the_odds_cap() -> None:
    legs = [
        _leg(match_id=1, odds=1.65, model_probability=0.705, expected_value=0.16, confidence_score=49),
        _leg(match_id=2, odds=2.10, model_probability=0.57, expected_value=0.20, confidence_score=49),
        _leg(match_id=3, odds=2.25, model_probability=0.523, expected_value=0.18, confidence_score=48),
        _leg(match_id=4, odds=2.55, model_probability=0.517, expected_value=0.32, confidence_score=49),
    ]
    packed = pack_disjoint(legs, size=3, min_size=2, count=1, rank_leg=lambda leg: -(leg.expected_value or 0), max_combined_odds=12)
    assert packed
    assert packed[0]["size"] == 3
    assert float(packed[0]["combined_odds"]) <= 12
    assert float(packed[0]["combined_ev"]) > 0


def test_standings_keep_only_published_rows() -> None:
    from app.analysis.empire import standings_rows

    rows = standings_rows(
        {"children": [{"name": "Groupe A", "standings": {"entries": [{"team": {"displayName": "Italy"}, "stats": [{"name": "points", "displayValue": "0"}, {"name": "gamesPlayed", "displayValue": "1"}]}]}}]},
        "uefa.nations",
    )
    assert rows[0]["title"] == "Italy — Groupe A"
    assert "0 pts" in rows[0]["body"]
    assert standings_rows({}, "uefa.nations") == []


def test_public_notes_keep_only_supplied_facts() -> None:
    from app.analysis.briefing import headlines_from_espn, lineup_notes, social_from_reddit, strategy_note

    notes = lineup_notes([{"lineups": [{"team": "A", "players": [{"name": "Un", "starter": True}]}]}])
    assert notes["published"] == 1
    assert "Un" in notes["examples"][0]
    assert headlines_from_espn({"articles": [{"headline": "Titre réel"}]})[0]["title"] == "Titre réel"
    assert headlines_from_espn({}) == []
    assert social_from_reddit("<html>")["status"] == "indisponible"
    assert "Aucune stratégie" in strategy_note([])


def test_paper_profit_uses_the_price_and_does_not_invent_a_score() -> None:
    from app.analysis.tracking import _experiment_markets, _paper_profit

    assert _paper_profit(True, 2.20) == 1.2
    assert _paper_profit(False, 2.20) == -1.0
    assert _paper_profit(True, None) is None
    markets = _experiment_markets(
        {
            "home_team": "A",
            "away_team": "B",
            "markets": [
                {"selection": "home", "odds": 1.65, "model_probability": 0.70, "ev": 0.15, "confidence_score": 49},
                {"selection": "away", "odds": 2.40, "model_probability": 0.48, "ev": 0.15, "confidence_score": 49},
            ],
        }
    )
    assert markets["probabilite"]["selection"] == "home"
    assert markets["favorite"]["selection"] == "home"
    assert "value" in markets


def test_a_bet_after_kickoff_does_not_teach_and_a_small_band_stays_raw() -> None:
    from datetime import datetime, timedelta, timezone

    from app.analysis.tracking import calibrate_new, counts_for_learning, kickoff_still_ahead

    kickoff = datetime(2026, 9, 26, 18, 0, tzinfo=timezone.utc)
    assert counts_for_learning(kickoff - timedelta(hours=2), kickoff)
    assert not counts_for_learning(kickoff + timedelta(minutes=5), kickoff)
    assert not kickoff_still_ahead(kickoff, now=kickoff + timedelta(minutes=1))
    samples = [("value", 0.70, True)] * 7
    assert calibrate_new(0.62, "value", samples) == 0.62
    taught = [("value", 0.62, won) for won in ([True] * 6 + [False] * 4)]
    adjusted = calibrate_new(0.62, "value", taught)
    assert adjusted < 0.62
    assert adjusted > 0.55


def test_results_shrink_later_probabilities_without_rewriting_the_past() -> None:
    from app.analysis.tracking import apply_calibration

    raw = 0.70
    unchanged = apply_calibration(raw, {"weight": 0.0, "hit_rate": None})
    shrunk = apply_calibration(raw, {"weight": 0.5, "hit_rate": 0.40})
    assert unchanged == raw
    assert shrunk < raw
    assert abs(shrunk - 0.55) < 1e-9


def test_agent_picks_the_priced_outcome_and_does_not_invent() -> None:
    from app.analysis.agent import build_pronostics

    picks = build_pronostics(
        [
            {
                "match_id": 1,
                "match": "A vs B",
                "home_team": "A",
                "away_team": "B",
                "competition": "Test",
                "narrative": ["Domicile A : forme WWDL. Sur 5 matchs renseignés, buts marqués 1.40, encaissés 0.80."],
                "markets": [
                    {"selection": "home", "odds": 1.8, "model_probability": 0.55, "edge": 0.02, "ev": 0.01, "confidence_score": 42, "data_quality": 0.33},
                    {"selection": "away", "odds": 21.0, "model_probability": 0.9, "edge": 0.5, "ev": 2.0, "confidence_score": 42, "data_quality": 0.33},
                ],
            }
        ]
    )
    assert len(picks) == 1
    assert picks[0]["selection_label"] == "A"
    assert "pari sûr" in picks[0]["reason"]
    assert build_pronostics([{"match": "C vs D", "markets": [{"selection": "home", "odds": None, "model_probability": 0.6}]}]) == []


def test_profiles_do_not_reuse_the_same_matches() -> None:
    legs = [_leg(match_id=index, match_label=f"M{index}", model_probability=0.7 - index * 0.02, odds=1.6 + index * 0.15) for index in range(1, 9)]
    first = pack_disjoint(legs, size=4, count=1, rank_leg=lambda leg: -leg.model_probability)
    used = {item["match_id"] for item in first[0]["selections"]}
    second = pack_disjoint(legs, size=4, count=1, rank_leg=lambda leg: abs(leg.odds - 2.2), exclude=used)
    assert len(first[0]["selections"]) == 4
    assert used.isdisjoint({item["match_id"] for item in second[0]["selections"]})
