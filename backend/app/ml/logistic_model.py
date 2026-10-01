"""Multinomial logistic regression on fundamental features."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from app.features.football import MODEL_FEATURE_COLUMNS

CLASSES = ("home", "draw", "away")


@dataclass
class LogisticMatchModel:
    pipeline: Pipeline
    columns: list[str] = field(default_factory=lambda: list(MODEL_FEATURE_COLUMNS))

    def predict_proba(self, frame: pd.DataFrame) -> np.ndarray:
        probabilities = self.pipeline.predict_proba(_prepare(frame))
        return _align(probabilities, self.pipeline.named_steps["model"].classes_)

    def explain(self, frame: pd.DataFrame, row: int = 0) -> list[dict[str, float | str]]:
        model: LogisticRegression = self.pipeline.named_steps["model"]
        matrix = _prepare(frame)
        transformed = self.pipeline.named_steps["imputer"].transform(matrix)
        transformed = self.pipeline.named_steps["scaler"].transform(transformed)
        predicted = int(np.argmax(self.predict_proba(frame)[row]))
        coefficients = model.coef_[predicted]
        contributions = transformed[row] * coefficients
        order = np.argsort(np.abs(contributions))[::-1][:8]
        factors = []
        for position in order:
            value = float(contributions[position])
            if value == 0:
                continue
            factors.append(
                {
                    "name": self.columns[position],
                    "value": value,
                    "direction": "positive" if value > 0 else "negative",
                }
            )
        return factors

    @classmethod
    def fit(cls, frame: pd.DataFrame, labels: pd.Series) -> LogisticMatchModel:
        pipeline = Pipeline(
            [
                ("imputer", SimpleImputer(strategy="median")),
                ("scaler", StandardScaler()),
                (
                    "model",
                    LogisticRegression(
                        max_iter=400,
                        C=1.0,
                    ),
                ),
            ]
        )
        pipeline.fit(_prepare(frame), labels)
        return cls(pipeline=pipeline)


def _prepare(frame: pd.DataFrame) -> pd.DataFrame:
    work = frame.reindex(columns=list(MODEL_FEATURE_COLUMNS)).copy()
    for column in work.columns:
        if work[column].isna().all():
            work[column] = 0.0
    return work


def _align(probabilities: np.ndarray, classes: np.ndarray) -> np.ndarray:
    ordered = np.zeros((len(probabilities), 3))
    for column, label in enumerate(classes):
        ordered[:, CLASSES.index(str(label))] = probabilities[:, column]
    return ordered
