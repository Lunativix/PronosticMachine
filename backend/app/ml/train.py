"""Train Poisson, logistic, XGBoost, and a validation-weighted ensemble."""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime

import numpy as np
import pandas as pd
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import save_artifact
from app.features.football import FEATURE_VERSION, MODEL_FEATURE_COLUMNS, build_feature_table
from app.ml.calibration import (
    expected_calibration_error,
    fit_calibrator,
    multiclass_brier,
    multiclass_log_loss,
)
from app.ml.ensemble import EnsembleModel
from app.ml.logistic_model import CLASSES, LogisticMatchModel
from app.ml.poisson import DixonColesModel
from app.ml.xgboost_model import GradientBoostMatchModel
from app.models import FeatureSnapshot, ModelVersion
from app.services.match_frame import matches_frame

LOGGER = logging.getLogger(__name__)
CLASS_INDEX = {name: index for index, name in enumerate(CLASSES)}


def result_label(home_goals: float, away_goals: float) -> str:
    if home_goals > away_goals:
        return "home"
    if home_goals == away_goals:
        return "draw"
    return "away"


def train_all(session: Session, *, max_iter: int = 60) -> list[ModelVersion]:
    settings = get_settings()
    frame = matches_frame(session)
    finished = frame[frame["status"].astype(str).str.lower().eq("finished")].copy()
    if len(finished) < 15:
        raise ValueError("At least 15 finished matches are required before training.")
    features = build_feature_table(finished)
    _store_features(session, features)
    merged = finished.merge(features, on="match_id", suffixes=("", "_feature"))
    merged["label"] = [
        result_label(home, away) for home, away in zip(merged["home_goals"], merged["away_goals"], strict=True)
    ]
    merged = merged.sort_values("kickoff").reset_index(drop=True)
    n = len(merged)
    train_end = max(int(n * 0.70), 10)
    val_end = max(int(n * 0.85), train_end + 1)
    train = merged.iloc[:train_end]
    valid = merged.iloc[train_end:val_end]
    test = merged.iloc[val_end:]
    if valid.empty:
        valid = train.iloc[-max(3, len(train) // 5) :]
        train = train.iloc[: len(train) - len(valid)]
    poisson = DixonColesModel.fit(train, max_iter=max_iter)
    logistic = LogisticMatchModel.fit(train, train["label"])
    boosting = GradientBoostMatchModel.fit(train, train["label"])
    component_valid = {
        "poisson": _poisson_matrix(poisson, valid),
        "logistic": logistic.predict_proba(valid),
        "xgboost": boosting.predict_proba(valid),
    }
    labels_valid = valid["label"].map(CLASS_INDEX).to_numpy()
    calibrators = {
        name: fit_calibrator(probabilities, labels_valid, "platt" if len(valid) < 40 else "isotonic")
        for name, probabilities in component_valid.items()
    }
    calibrated_valid = {name: calibrators[name].transform(probabilities) for name, probabilities in component_valid.items()}
    ensemble = EnsembleModel.fit(calibrated_valid, labels_valid, min_rows=12)
    ensemble_valid = ensemble.combine(calibrated_valid)
    ensemble_calibrator = fit_calibrator(ensemble_valid, labels_valid, "platt")
    test_labels = test["label"].map(CLASS_INDEX).to_numpy() if not test.empty else np.array([], dtype=int)
    versions: list[ModelVersion] = []
    dataset_hash = _hash_frame(train)
    periods = _periods(train, valid, test)
    artifacts = {
        "poisson": poisson,
        "logistic": logistic,
        "xgboost": boosting,
        "ensemble": {
            "ensemble": ensemble,
            "calibrators": calibrators,
            "ensemble_calibrator": ensemble_calibrator,
            "poisson": poisson,
            "logistic": logistic,
            "xgboost": boosting,
        },
    }
    matrices = {
        "poisson": (_poisson_matrix(poisson, test), component_valid["poisson"]),
        "logistic": (logistic.predict_proba(test) if not test.empty else np.empty((0, 3)), component_valid["logistic"]),
        "xgboost": (boosting.predict_proba(test) if not test.empty else np.empty((0, 3)), component_valid["xgboost"]),
        "ensemble": (
            ensemble_calibrator.transform(ensemble.combine(_calibrated_components(artifacts["ensemble"], test)))
            if not test.empty
            else np.empty((0, 3)),
            ensemble_valid,
        ),
    }
    for key, artifact in artifacts.items():
        raw_test, raw_valid = matrices[key]
        calibrated_test = raw_test if key == "ensemble" or test.empty else calibrators[key].transform(raw_test)
        metrics = _metrics(calibrated_test, test_labels, raw_valid, labels_valid)
        metrics["calibration_method"] = "platt" if key == "ensemble" or len(valid) < 40 else "isotonic"
        if key == "ensemble":
            metrics["ensemble_method"] = ensemble.method
            metrics["weights"] = ensemble.weights
        version = _next_version(session, key)
        path = settings.models_dir / key / version / "model.joblib"
        save_artifact(path, artifact, {"model_key": key, "version": version, "feature_version": FEATURE_VERSION})
        session.execute(update(ModelVersion).where(ModelVersion.model_key == key).values(is_active=False))
        row = ModelVersion(
            model_key=key,
            version=version,
            dataset_hash=dataset_hash,
            feature_version=FEATURE_VERSION,
            hyperparameters=_hyperparameters(key, poisson, ensemble),
            metrics=metrics,
            artifact_path=str(path),
            is_active=True,
            **periods,
        )
        session.add(row)
        versions.append(row)
    session.commit()
    for row in versions:
        session.refresh(row)
        LOGGER.info(
            "model trained",
            extra={"context": {"model_version": f"{row.model_key}:{row.version}", "metrics": row.metrics}},
        )
    return versions


def _calibrated_components(bundle: dict, frame: pd.DataFrame) -> dict[str, np.ndarray]:
    raw = {
        "poisson": _poisson_matrix(bundle["poisson"], frame),
        "logistic": bundle["logistic"].predict_proba(frame),
        "xgboost": bundle["xgboost"].predict_proba(frame),
    }
    return {name: bundle["calibrators"][name].transform(probabilities) for name, probabilities in raw.items()}


def predict_bundle(bundle: dict, frame: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    components = _calibrated_components(bundle, frame)
    calibrated = bundle["ensemble_calibrator"].transform(bundle["ensemble"].combine(components))
    raw = bundle["ensemble"].combine(
        {
            "poisson": _poisson_matrix(bundle["poisson"], frame),
            "logistic": bundle["logistic"].predict_proba(frame),
            "xgboost": bundle["xgboost"].predict_proba(frame),
        }
    )
    return raw, calibrated


def _poisson_matrix(model: DixonColesModel, frame: pd.DataFrame) -> np.ndarray:
    if frame.empty:
        return np.empty((0, 3))
    rows = []
    for record in frame.itertuples(index=False):
        probabilities = model.predict_proba(str(record.home_team), str(record.away_team))
        rows.append([probabilities[name] for name in CLASSES])
    return np.asarray(rows)


def _metrics(test_probabilities: np.ndarray, test_labels: np.ndarray, valid_probabilities: np.ndarray, valid_labels: np.ndarray) -> dict[str, float]:
    metrics = {
        "validation_brier": multiclass_brier(valid_probabilities, valid_labels),
        "validation_log_loss": multiclass_log_loss(valid_probabilities, valid_labels),
        "validation_ece": expected_calibration_error(valid_probabilities, valid_labels),
    }
    if len(test_labels):
        metrics["brier"] = multiclass_brier(test_probabilities, test_labels)
        metrics["log_loss"] = multiclass_log_loss(test_probabilities, test_labels)
        metrics["ece"] = expected_calibration_error(test_probabilities, test_labels)
        metrics["test_rows"] = float(len(test_labels))
    return metrics


def _store_features(session: Session, features: pd.DataFrame) -> None:
    for record in features.itertuples(index=False):
        payload = record._asdict() if hasattr(record, "_asdict") else {}
        existing = session.scalar(
            select(FeatureSnapshot).where(
                FeatureSnapshot.match_id == int(record.match_id),
                FeatureSnapshot.feature_version == FEATURE_VERSION,
            )
        )
        body = {column: _jsonable(getattr(record, column, None)) for column in features.columns}
        if existing is None:
            session.add(
                FeatureSnapshot(
                    match_id=int(record.match_id),
                    feature_version=FEATURE_VERSION,
                    as_of=pd.Timestamp(record.kickoff).to_pydatetime(),
                    payload=body,
                    completeness=float(getattr(record, "completeness", 0.0) or 0.0),
                )
            )
        else:
            existing.payload = body
            existing.completeness = float(getattr(record, "completeness", 0.0) or 0.0)
    session.flush()


def _jsonable(value: object) -> object:
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return None
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, np.floating):
        return float(value)
    if isinstance(value, np.integer):
        return int(value)
    return value


def _hash_frame(frame: pd.DataFrame) -> str:
    blob = frame[["match_id", "home_goals", "away_goals"]].to_csv(index=False).encode()
    return hashlib.sha256(blob).hexdigest()


def _periods(train: pd.DataFrame, valid: pd.DataFrame, test: pd.DataFrame) -> dict[str, datetime | None]:
    def bounds(frame: pd.DataFrame, prefix: str) -> dict[str, datetime | None]:
        if frame.empty:
            return {f"{prefix}_period_start": None, f"{prefix}_period_end": None}
        return {
            f"{prefix}_period_start": pd.Timestamp(frame["kickoff"].min()).to_pydatetime(),
            f"{prefix}_period_end": pd.Timestamp(frame["kickoff"].max()).to_pydatetime(),
        }

    payload: dict[str, datetime | None] = {}
    payload.update(bounds(train, "training"))
    payload.update(bounds(valid, "validation"))
    payload.update(bounds(test, "test"))
    return payload


def _hyperparameters(key: str, poisson: DixonColesModel, ensemble: EnsembleModel) -> dict[str, object]:
    if key == "poisson":
        return {"xi": poisson.xi, "max_goals": 8, "family": "dixon-coles"}
    if key == "logistic":
        return {"C": 1.0, "imputation": "median"}
    if key == "xgboost":
        return {"n_estimators": 80, "max_depth": 3, "learning_rate": 0.08}
    return {"method": ensemble.method, "weights": ensemble.weights, "features": MODEL_FEATURE_COLUMNS}


def _next_version(session: Session, key: str) -> str:
    count = session.query(ModelVersion).filter(ModelVersion.model_key == key).count()
    return f"v{count + 1}"
