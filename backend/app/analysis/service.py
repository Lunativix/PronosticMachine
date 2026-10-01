"""Analyze the next 14 days. Markets come from the score model. Odds come only from stored prices."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone

import numpy as np
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.analysis.combinations import CombinationConfig, CombinationEngine, Leg
from app.analysis.confidence import ConfidenceEngine, ConfidenceInputs
from app.analysis.markets import catalog
from app.analysis.signals import SIGNAL_LABELS, SignalConfig, SignalEngine
from app.betting.odds_math import devig, expected_value, model_edge
from app.core.config import Settings, get_settings
from app.core.security import load_artifact
from app.fixtures.service import upcoming_query
from app.fixtures.window import get_upcoming_window
from app.ml.poisson import DixonColesModel, score_matrix
from app.models import Alert, CombinationAnalysis, Injury, MarketAnalysis, Match, ModelVersion, Odds, Team

TWO_WAY = {
    "btts": ("yes", "no"),
    "draw_no_bet": ("home", "away"),
    "handicap": ("home_-1.5", "away_-1.5"),
}


def analyze_upcoming_matches(session: Session, settings: Settings | None = None) -> dict[str, int]:
    settings = settings or get_settings()
    start, end = get_upcoming_window(days=14)
    matches = upcoming_query(session, start, end, None, None)
    model_row, poisson = _active_poisson(session, settings)
    calibration = None
    if model_row and model_row.metrics.get("ece") is not None:
        calibration = max(0.0, 1.0 - float(model_row.metrics["ece"]))
    signal_engine = SignalEngine(
        SignalConfig(
            min_edge=settings.min_edge,
            min_ev=settings.min_ev,
            min_confidence=settings.min_confidence_score,
            min_data_quality=settings.min_data_quality,
        )
    )
    confidence_engine = ConfidenceEngine()
    created = datetime.now(timezone.utc)
    legs: list[Leg] = []
    stored = 0
    for match in matches:
        home = session.get(Team, match.home_team_id)
        away = session.get(Team, match.away_team_id)
        if home is None or away is None:
            continue
        label = f"{home.name} vs {away.name}"
        history = _history_count(session, match.home_team_id, match.away_team_id)
        known = poisson is not None and home.name in poisson.teams and away.name in poisson.teams
        sufficient = bool(known and history >= settings.min_history_matches)
        quality = min(1.0, history / 30.0) if known else 0.15
        injuries = _injury_completeness(session, match)
        prices = _latest_prices(session, match.id)
        matrix = None
        factors: list[dict[str, object]] = []
        if known and poisson is not None:
            lambda_home, lambda_away = poisson.lambdas(home.name, away.name)
            matrix = score_matrix(lambda_home, lambda_away, poisson.rho)
            factors = [
                {"name": item["name"], "value": item["value"], "target": item["target"]}
                for item in poisson.explain(home.name, away.name)
            ]
        rows = catalog(matrix) if matrix is not None else []
        if not rows:
            stored += _store_gap(session, match, model_row, created, quality, history, label)
            continue
        market_probs = _market_probabilities(rows, prices)
        primary: tuple[str, str, float] | None = None
        for row in rows:
            market = str(row["market"])
            selection = str(row["selection"])
            probability = float(row["model_probability"])
            odds = prices.get((market, selection))
            market_probability = market_probs.get((market, selection))
            edge = model_edge(probability, market_probability) if market_probability is not None else None
            ev = expected_value(probability, odds) if odds is not None else None
            previous = _previous_probability(session, match.id, market, selection)
            stability = None if previous is None else 1.0 - min(abs(probability - previous), 1.0)
            volatility = _odds_volatility(session, match.id, market, selection)
            scored = confidence_engine.score(
                ConfidenceInputs(
                    data_quality=quality,
                    history_matches=history,
                    calibration_score=calibration,
                    model_agreement=None,
                    prediction_stability=stability,
                    odds_volatility=volatility,
                    information_completeness=injuries,
                    market=market,
                    historical_market_performance=None,
                    edge=edge,
                    odds_present=odds is not None,
                )
            )
            signal = signal_engine.classify(
                odds=odds,
                edge=edge,
                expected_value=ev,
                confidence_score=float(scored["confidence_score"]),
                data_quality=quality,
                sufficient_data=sufficient,
            )
            explanation = _explanation(factors, odds is not None, sufficient, history, injuries)
            session.add(
                MarketAnalysis(
                    match_id=match.id,
                    created_at=created,
                    model_version_id=None if model_row is None else model_row.id,
                    model_version="" if model_row is None else model_row.version,
                    market=market,
                    selection=selection,
                    odds=odds,
                    model_probability=probability,
                    market_probability=market_probability,
                    edge=edge,
                    expected_value=ev,
                    confidence_score=float(scored["confidence_score"]),
                    confidence_level=str(scored["confidence_level"]),
                    signal=signal,
                    data_quality=quality,
                    sample_size=history,
                    calibration=calibration,
                    model_agreement=None,
                    explanation=explanation,
                    sufficient_data=sufficient,
                )
            )
            stored += 1
            if signal not in {"NO_SIGNAL", "INSUFFICIENT_DATA"} and (
                primary is None or (edge or -1) > primary[2]
            ):
                primary = (market, selection, edge or 0.0)
            if signal not in {"NO_SIGNAL", "INSUFFICIENT_DATA"}:
                legs.append(
                    Leg(
                        match_id=match.id,
                        match_label=label,
                        market=market,
                        selection=selection,
                        odds=odds,
                        model_probability=probability,
                        edge=edge,
                        expected_value=ev,
                        confidence_score=float(scored["confidence_score"]),
                        data_quality=quality,
                        signal=signal,
                        score_matrix=matrix,
                    )
                )
                _queue_alert(session, settings, signal, float(scored["confidence_score"]), ev, match.id, market, selection)
        match.analysis_state = "ANALYZED" if sufficient else "INSUFFICIENT_DATA"
    engine = CombinationEngine(
        CombinationConfig(
            max_size=settings.max_combination_size,
            min_confidence=settings.min_confidence_score,
            min_edge=settings.min_edge,
            min_data_quality=settings.min_data_quality,
            experimental_correlation=settings.experimental_correlation,
        )
    )
    grouped = engine.build(legs)
    combos = 0
    for category, rows in grouped.items():
        for row in rows:
            session.add(
                CombinationAnalysis(
                    created_at=created,
                    category=category,
                    size=int(row["size"]),
                    combined_odds=row["combined_odds"],  # type: ignore[arg-type]
                    combined_probability=row["combined_probability"],  # type: ignore[arg-type]
                    combined_ev=row["combined_ev"],  # type: ignore[arg-type]
                    confidence_score=float(row["confidence_score"]),
                    correlation_risk=str(row["correlation_risk"]),
                    correlation_status=str(row["correlation_status"]),
                    combination_scope=str(row["combination_scope"]),
                    selections=row["selections"],  # type: ignore[arg-type]
                )
            )
            combos += 1
            _queue_alert(session, settings, "COMBINATION_UPDATED", float(row["confidence_score"]), row["combined_ev"], None, category, "")
    session.commit()
    return {"matches": len(matches), "analyses": stored, "combinations": combos}


def _store_gap(
    session: Session,
    match: Match,
    model_row: ModelVersion | None,
    created: datetime,
    quality: float,
    history: int,
    label: str,
) -> int:
    session.add(
        MarketAnalysis(
            match_id=match.id,
            created_at=created,
            model_version_id=None if model_row is None else model_row.id,
            model_version="" if model_row is None else model_row.version,
            market="indisponible",
            selection="indisponible",
            odds=None,
            model_probability=None,
            market_probability=None,
            edge=None,
            expected_value=None,
            confidence_score=0.0,
            confidence_level="VERY_LOW",
            signal="INSUFFICIENT_DATA",
            data_quality=quality,
            sample_size=history,
            calibration=None,
            model_agreement=None,
            explanation={
                "match": label,
                "favorable": [],
                "risks": ["équipes absentes du modèle entraîné ou historique trop court"],
                "signal_label": SIGNAL_LABELS["INSUFFICIENT_DATA"],
            },
            sufficient_data=False,
        )
    )
    match.analysis_state = "INSUFFICIENT_DATA"
    return 1


def _explanation(
    factors: list[dict[str, object]],
    odds_present: bool,
    sufficient: bool,
    history: int,
    injuries: float | None,
) -> dict[str, object]:
    favorable = [
        f"{item['name']}={float(item['value']):.3f}"
        for item in factors
        if item["name"] in {"home_advantage", "home_attack", "away_attack", "lambda_home", "lambda_away"}
    ]
    risks: list[str] = []
    if not sufficient:
        risks.append("historique insuffisant pour les deux équipes")
    if history < 15:
        risks.append("échantillon historique limité")
    if not odds_present:
        risks.append("cote absente : edge et EV non calculés")
    if injuries is None:
        risks.append("informations de blessure absentes")
    return {
        "favorable": favorable,
        "risks": risks,
        "signal_label": "",
    }


def _active_poisson(session: Session, settings: Settings) -> tuple[ModelVersion | None, DixonColesModel | None]:
    row = session.scalar(select(ModelVersion).where(ModelVersion.is_active.is_(True)).order_by(ModelVersion.id.desc()))
    if row is None:
        return None, None
    payload = load_artifact(settings.project_root / row.artifact_path, settings.models_dir)
    model = payload["model"]
    poisson = model.get("poisson") if isinstance(model, dict) else model
    if not isinstance(poisson, DixonColesModel):
        return row, None
    return row, poisson


def _history_count(session: Session, home_id: int, away_id: int) -> int:
    statement = select(func.count()).select_from(Match).where(
        func.lower(Match.status).in_(["finished", "ft"]),
        ((Match.home_team_id == home_id) | (Match.away_team_id == home_id) | (Match.home_team_id == away_id) | (Match.away_team_id == away_id)),
    )
    return int(session.scalar(statement) or 0)


def _injury_completeness(session: Session, match: Match) -> float | None:
    count = session.scalar(
        select(func.count()).select_from(Injury).where(
            Injury.team_id.in_([match.home_team_id, match.away_team_id])
        )
    )
    if not count:
        return None
    return 0.7


def _latest_prices(session: Session, match_id: int) -> dict[tuple[str, str], float]:
    rows = session.scalars(select(Odds).where(Odds.match_id == match_id, Odds.price.is_not(None)).order_by(Odds.captured_at.asc())).all()
    prices: dict[tuple[str, str], float] = {}
    for row in rows:
        if row.price is not None and row.price > 1:
            prices[(row.market, row.selection)] = float(row.price)
    return prices


def _market_probabilities(
    rows: list[dict[str, float | str]],
    prices: dict[tuple[str, str], float],
) -> dict[tuple[str, str], float]:
    output: dict[tuple[str, str], float] = {}
    one_x_two = {selection: prices.get(("1X2", selection)) for selection in ("home", "draw", "away")}
    if all(value is not None for value in one_x_two.values()):
        cleaned = devig({key: float(value) for key, value in one_x_two.items() if value is not None})
        for key, value in cleaned.items():
            output[("1X2", key)] = value
    grouped: dict[tuple[str, str], dict[str, float]] = defaultdict(dict)
    for row in rows:
        market = str(row["market"])
        selection = str(row["selection"])
        price = prices.get((market, selection))
        if price is None or market == "1X2":
            continue
        if market == "over_under":
            side, line = selection.split("_", 1)
            grouped[(market, line)][side] = price
        elif market in TWO_WAY:
            grouped[(market, "")][selection] = price
    for (market, line), quotes in grouped.items():
        if market == "over_under" and {"over", "under"} <= set(quotes):
            cleaned = devig({"over": quotes["over"], "under": quotes["under"]})
            output[(market, f"over_{line}")] = cleaned["over"]
            output[(market, f"under_{line}")] = cleaned["under"]
        elif market in TWO_WAY and set(TWO_WAY[market]) <= set(quotes):
            cleaned = devig({key: quotes[key] for key in TWO_WAY[market]})
            for key, value in cleaned.items():
                output[(market, key)] = value
    return output


def _previous_probability(session: Session, match_id: int, market: str, selection: str) -> float | None:
    row = session.scalar(
        select(MarketAnalysis)
        .where(
            MarketAnalysis.match_id == match_id,
            MarketAnalysis.market == market,
            MarketAnalysis.selection == selection,
            MarketAnalysis.model_probability.is_not(None),
        )
        .order_by(MarketAnalysis.created_at.desc())
    )
    if row is None or row.model_probability is None:
        return None
    return float(row.model_probability)


def _odds_volatility(session: Session, match_id: int, market: str, selection: str) -> float | None:
    prices = session.scalars(
        select(Odds.price).where(
            Odds.match_id == match_id,
            Odds.market == market,
            Odds.selection == selection,
            Odds.price.is_not(None),
        )
    ).all()
    values = [float(price) for price in prices if price is not None]
    if len(values) < 2:
        return None
    return float(np.std(values))


def _queue_alert(
    session: Session,
    settings: Settings,
    kind: str,
    confidence: float,
    ev: float | None,
    match_id: int | None,
    market: str,
    selection: str,
) -> None:
    channel_ready = bool(settings.discord_webhook_url or settings.telegram_bot_token or settings.smtp_url)
    interesting = kind in {"STRONG_SIGNAL", "COMBINATION_UPDATED"} or confidence >= 70
    if not interesting:
        return
    alert_type = kind
    if kind == "STRONG_SIGNAL" and ev is not None and ev > 0:
        alert_type = "STRONG_VALUE_SIGNAL"
    elif confidence >= 70 and kind != "COMBINATION_UPDATED":
        alert_type = "HIGH_CONFIDENCE_SIGNAL"
    session.add(
        Alert(
            message=alert_type,
            payload={"match_id": match_id, "market": market, "selection": selection, "type": alert_type},
            channel="disabled" if not channel_ready else "configured",
            delivered=False,
        )
    )


def latest_snapshot(session: Session) -> datetime | None:
    return session.scalar(select(func.max(MarketAnalysis.created_at)))


def latest_probability_snapshot(session: Session) -> datetime | None:
    return session.scalar(
        select(func.max(MarketAnalysis.created_at)).where(MarketAnalysis.model_probability.is_not(None))
    )
