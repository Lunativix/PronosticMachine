"""Inverse validation log loss weights. Used when the stacking sample is small."""

from __future__ import annotations

import numpy as np

from app.ml.calibration import multiclass_log_loss


def _inverse_log_loss_weights(components: dict[str, np.ndarray], labels: np.ndarray) -> dict[str, float]:
    scores = {}
    for name, probabilities in components.items():
        scores[name] = 1.0 / max(multiclass_log_loss(probabilities, labels), 1e-6)
    total = sum(scores.values())
    return {name: value / total for name, value in scores.items()}
