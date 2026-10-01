"""Point-in-time predictions and value signals."""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.betting.odds_math import distribution_confidence
from app.betting.signal_quality import classify_state, signal_quality_score
from app.betting.value_engine import analyze_market
from app.core.config import Settings, get_settings
from app.core.logging import log_context
from app.core.security import load_artifact
from app.features.football import FEATURE_VERSION, build_feature_table
from app.ml.logistic_model import CLASSES
from app.ml.train import predict_bundle
from app.models import BetOpportunity, ModelVersion, Prediction, PredictionProbability
from app.services.alerts import record_signal
from app.services.match_frame import matches_frame

LOGGER = logging.getLogger(__name__)
UNIFORM = {"home": 1 / 3, "draw": 1 / 3, "away": 1 / 3}


def generate_predictions(session: Session, match_ids: list[int] | None = None, settings: Settings | None = None) -> list[Prediction]:
    settings = settings or get_settings()
    model_row = session.scalar(
        select(ModelVersion).where(ModelVersion.model_key == "ensemble", ModelVersion.is_active.is_(True))
    )
    if model_row is None:
        raise ValueError("No active ensemble model. Train before generating predictions.")
    artifact = load_artifact(Path(model_row.artifact_path), settings.models_dir)
    bundle = artifact["model"]
    frame = matches_frame(session)
    if match_ids is not None:
        frame = frame[frame["match_id"].isin(match_ids)]
    if frame.empty:
        return []
    features = build_feature_table(matches_frame(session))
    selected = features[features["match_id"].isin(frame["match_id"])]
    merged = frame.merge(selected, on="match_id", suffixes=("", "_feature"))
    raw, calibrated = predict_bundle(bundle, merged)
    ece = model_row.metrics.get("ece") or model_row.metrics.get("validation_ece")
    created: list[Prediction] = []
    for position, record in enumerate(merged.itertuples(index=False)):
        history = int(min(record.home_history_n or 0, record.away_history_n or 0))
        probabilities = {name: float(calibrated[position, index]) for index, name in enumerate(CLASSES)}
        raw_probabilities = {name: float(raw[position, index]) for index, name in enumerate(CLASSES)}
        shrunk = False
        if history < settings.min_history_matches:
            weight = history / settings.min_history_matches
            probabilities = {
                name: weight * probabilities[name] + (1.0 - weight) * UNIFORM[name] for name in CLASSES
            }
            shrunk = True
        confidence = distribution_confidence(probabilities)
        odds = {
            "home": _float_or_none(getattr(record, "odds_home", None)),
            "draw": _float_or_none(getattr(record, "odds_draw", None)),
            "away": _float_or_none(getattr(record, "odds_away", None)),
        }
        has_odds = all(value is not None and value > 1 for value in odds.values())
        values = []
        if has_odds:
            values = analyze_market(
                probabilities,
                {key: float(value) for key, value in odds.items() if value is not None},
                data_quality=float(record.completeness or 0),
                history_matches=history,
                expected_calibration_error=None if ece is None else float(ece),
                model_agreement=_agreement(bundle, merged.iloc[[position]]),
                bookmaker_count=int(getattr(record, "bookmaker_count", 1) or 1),
                odds_dispersion=_float_or_none(getattr(record, "odds_dispersion", None)),
                min_edge=settings.min_edge,
                min_ev=settings.min_ev,
                min_model_confidence=settings.min_model_confidence,
                min_history_matches=settings.min_history_matches,
            )
            best = max(values, key=lambda item: item.expected_value)
            state = best.state
            quality = best.signal_quality
        else:
            quality, _ = signal_quality_score(
                data_quality=float(record.completeness or 0),
                history_matches=history,
                expected_calibration_error=None if ece is None else float(ece),
                model_agreement=None,
                edge=None,
                expected_value=None,
                bookmaker_count=0,
                odds_dispersion=None,
                confidence=confidence,
            )
            state = classify_state(
                history_matches=history,
                min_history_matches=settings.min_history_matches,
                confidence=confidence,
                min_model_confidence=settings.min_model_confidence,
                edge=None,
                expected_value=None,
                min_edge=settings.min_edge,
                min_ev=settings.min_ev,
                has_odds=False,
            )
        explanation = _explain(bundle, merged.iloc[[position]])
        prediction = Prediction(
            match_id=int(record.match_id),
            model_version_id=model_row.id,
            features_version=FEATURE_VERSION,
            data_quality=float(record.completeness or 0),
            confidence=confidence,
            state=state,
            signal_quality=quality,
            explanation=explanation,
            explanation_method=str(explanation.get("method")),
            probabilities_shrunk=shrunk,
        )
        session.add(prediction)
        session.flush()
        for name in CLASSES:
            session.add(
                PredictionProbability(
                    prediction_id=prediction.id,
                    selection=name,
                    probability_raw=raw_probabilities[name],
                    probability_calibrated=probabilities[name],
                )
            )
        for item in values:
            opportunity = BetOpportunity(
                prediction_id=prediction.id,
                match_id=int(record.match_id),
                market="1X2",
                selection=item.selection,
                odds=item.odds,
                model_probability=item.model_probability,
                market_probability=item.market_probability,
                edge=item.edge,
                expected_value=item.expected_value,
                signal_quality=item.signal_quality,
                state=item.state,
                model_version_id=model_row.id,
                market_margin=item.market_margin,
            )
            session.add(opportunity)
            session.flush()
            if item.state == "SIGNAL":
                record_signal(session, opportunity, settings)
        log_context(
            LOGGER,
            logging.INFO,
            "prediction stored",
            prediction_id=prediction.id,
            match_id=int(record.match_id),
            model_version=f"{model_row.model_key}:{model_row.version}",
            state=state,
        )
        created.append(prediction)
    session.commit()
    return created


def _agreement(bundle: dict, frame: pd.DataFrame) -> float:
    from app.ml.train import _calibrated_components

    components = list(_calibrated_components(bundle, frame).values())
    gaps = [np.mean(np.abs(components[0] - other)) for other in components[1:]]
    if not gaps:
        return 0.5
    return float(max(0.0, 1.0 - float(np.mean(gaps))))


def _explain(bundle: dict, frame: pd.DataFrame) -> dict[str, object]:
    poisson_factors = bundle["poisson"].explain(str(frame.iloc[0]["home_team"]), str(frame.iloc[0]["away_team"]))
    method, shap_factors = bundle["xgboost"].explain(frame, 0)
    logistic_factors = bundle["logistic"].explain(frame, 0)
    return {
        "method": method if shap_factors else "native_poisson",
        "ensemble_weights": bundle["ensemble"].weights,
        "ensemble_method": bundle["ensemble"].method,
        "factors": shap_factors or logistic_factors,
        "poisson_contributions": poisson_factors,
        "disclaimer": "Estimates describe model inputs. They are not a promise of an outcome.",
    }


def _float_or_none(value: object) -> float | None:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except TypeError:
        pass
    return float(value)
