"""Probability calibration on a time-ordered holdout. Raw and calibrated values are both kept."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression


def multiclass_brier(probabilities: np.ndarray, labels: np.ndarray) -> float:
    one_hot = np.eye(probabilities.shape[1])[labels]
    return float(np.mean(np.sum((probabilities - one_hot) ** 2, axis=1)))


def multiclass_log_loss(probabilities: np.ndarray, labels: np.ndarray) -> float:
    clipped = np.clip(probabilities, 1e-12, 1.0)
    clipped = clipped / clipped.sum(axis=1, keepdims=True)
    return float(-np.mean(np.log(clipped[np.arange(len(labels)), labels])))


def expected_calibration_error(probabilities: np.ndarray, labels: np.ndarray, bins: int = 10) -> float:
    """ECE of the predicted class probability against whether that class occurred."""
    predicted = probabilities.argmax(axis=1)
    confidence = probabilities.max(axis=1)
    correct = (predicted == labels).astype(float)
    edges = np.linspace(0.0, 1.0, bins + 1)
    total = len(labels)
    if total == 0:
        return 0.0
    error = 0.0
    for low, high in zip(edges[:-1], edges[1:], strict=True):
        mask = (confidence >= low) & (confidence < high if high < 1 else confidence <= high)
        if not np.any(mask):
            continue
        error += abs(float(correct[mask].mean()) - float(confidence[mask].mean())) * (mask.sum() / total)
    return float(error)


@dataclass
class ProbabilityCalibrator:
    method: str
    models: list[object]

    def transform(self, probabilities: np.ndarray) -> np.ndarray:
        adjusted = np.column_stack(
            [np.clip(model.predict(probabilities[:, column]), 1e-6, 1 - 1e-6) for column, model in enumerate(self.models)]
        )
        adjusted = adjusted / adjusted.sum(axis=1, keepdims=True)
        return adjusted

    @classmethod
    def fit(cls, probabilities: np.ndarray, labels: np.ndarray, method: str = "platt") -> ProbabilityCalibrator:
        models: list[object] = []
        for column in range(probabilities.shape[1]):
            target = (labels == column).astype(int)
            raw = probabilities[:, column].reshape(-1, 1)
            if method == "isotonic":
                model = IsotonicRegression(out_of_bounds="clip")
                model.fit(raw.ravel(), target)
            elif method == "platt":
                model = LogisticRegression(C=1.0, max_iter=200)
                model.fit(raw, target)
            else:
                raise ValueError(f"Unknown calibration method: {method}")
            models.append(model)
        return cls(method=method, models=models)


class _PlattAdapter:
    def __init__(self, model: LogisticRegression) -> None:
        self.model = model

    def predict(self, values: np.ndarray) -> np.ndarray:
        return self.model.predict_proba(values.reshape(-1, 1))[:, 1]


def fit_calibrator(probabilities: np.ndarray, labels: np.ndarray, method: str) -> ProbabilityCalibrator:
    calibrator = ProbabilityCalibrator.fit(probabilities, labels, method)
    if method == "platt":
        calibrator.models = [_PlattAdapter(model) for model in calibrator.models]  # type: ignore[misc]
    return calibrator
