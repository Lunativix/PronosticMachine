"""End-to-end train, prediction, and value flow on synthetic matches."""

from __future__ import annotations

from app.core.config import get_settings
from app.ml.train import train_all
from app.services.prediction_service import generate_predictions


def test_train_and_predict(seeded_session, monkeypatch) -> None:
    monkeypatch.setenv("MIN_HISTORY_MATCHES", "3")
    monkeypatch.setenv("MIN_MODEL_CONFIDENCE", "0.0")
    get_settings.cache_clear()
    versions = train_all(seeded_session, max_iter=20)
    keys = {row.model_key for row in versions}
    assert keys == {"poisson", "logistic", "xgboost", "ensemble"}
    predictions = generate_predictions(seeded_session, settings=get_settings())
    get_settings.cache_clear()
    assert predictions
    assert predictions[-1].state in {"INSUFFICIENT_DATA", "LOW_CONFIDENCE", "NO_SIGNAL", "SIGNAL"}
    assert predictions[-1].explanation["disclaimer"]
