"""Ensemble weights are fit on a validation window. Equal weights are not the default."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.optimize import minimize

from app.ml._ensemble_weights import _inverse_log_loss_weights
from app.ml.calibration import multiclass_log_loss


@dataclass
class EnsembleModel:
    weights: dict[str, float]
    method: str

    def combine(self, components: dict[str, np.ndarray]) -> np.ndarray:
        names = [name for name in self.weights if name in components]
        stacked = sum(self.weights[name] * components[name] for name in names)
        total = stacked.sum(axis=1, keepdims=True)
        return stacked / np.clip(total, 1e-12, None)

    @classmethod
    def fit(cls, components: dict[str, np.ndarray], labels: np.ndarray, min_rows: int = 30) -> EnsembleModel:
        names = list(components)
        if len(labels) < min_rows:
            return cls(weights=_inverse_log_loss_weights(components, labels), method="inverse_log_loss")
        start = np.full(len(names), 1.0 / len(names))

        def loss(raw: np.ndarray) -> float:
            weights = np.clip(raw, 0.0, None)
            weights = weights / max(weights.sum(), 1e-12)
            mixed = sum(weight * components[name] for weight, name in zip(weights, names, strict=True))
            mixed = mixed / mixed.sum(axis=1, keepdims=True)
            return multiclass_log_loss(mixed, labels)

        result = minimize(
            loss,
            start,
            method="SLSQP",
            bounds=[(0.0, 1.0)] * len(names),
            constraints={"type": "eq", "fun": lambda raw: np.clip(raw, 0, None).sum() - 1.0},
        )
        solved = np.clip(result.x, 0.0, None)
        solved = solved / solved.sum()
        return cls(weights={name: float(weight) for name, weight in zip(names, solved, strict=True)}, method="log_loss_simplex")
