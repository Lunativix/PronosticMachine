"""Calibration metrics and a fitted calibrator."""

from __future__ import annotations

import numpy as np

from app.ml.calibration import expected_calibration_error, fit_calibrator, multiclass_brier, multiclass_log_loss


def test_calibration_metrics_and_transform() -> None:
    rng = np.random.default_rng(1)
    labels = rng.integers(0, 3, size=80)
    raw = np.full((80, 3), 1 / 3)
    raw[np.arange(80), labels] += 0.2
    raw = raw / raw.sum(axis=1, keepdims=True)
    calibrator = fit_calibrator(raw[:60], labels[:60], "platt")
    adjusted = calibrator.transform(raw[60:])
    assert adjusted.shape == (20, 3)
    assert np.allclose(adjusted.sum(axis=1), 1)
    assert multiclass_brier(raw, labels) >= 0
    assert multiclass_log_loss(raw, labels) >= 0
    assert 0 <= expected_calibration_error(raw, labels) <= 1
