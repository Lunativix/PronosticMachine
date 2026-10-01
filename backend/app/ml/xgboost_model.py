"""Gradient boosting match model. Explanations come from SHAP when the library can run."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from xgboost import XGBClassifier

from app.features.football import MODEL_FEATURE_COLUMNS

CLASSES = ("home", "draw", "away")


@dataclass
class GradientBoostMatchModel:
    imputer: SimpleImputer
    model: XGBClassifier
    columns: list[str] = field(default_factory=lambda: list(MODEL_FEATURE_COLUMNS))
    class_labels: list[str] = field(default_factory=lambda: list(CLASSES))

    def _matrix(self, frame: pd.DataFrame) -> np.ndarray:
        return self.imputer.transform(_prepare(frame))

    def predict_proba(self, frame: pd.DataFrame) -> np.ndarray:
        probabilities = self.model.predict_proba(self._matrix(frame))
        ordered = np.zeros((len(frame), 3))
        for column, label in enumerate(self.class_labels):
            ordered[:, CLASSES.index(str(label))] = probabilities[:, column]
        return ordered

    def explain(self, frame: pd.DataFrame, row: int = 0) -> tuple[str, list[dict[str, float | str]]]:
        matrix = self._matrix(frame)
        try:
            import shap

            explainer = shap.TreeExplainer(self.model)
            values = explainer.shap_values(matrix[row : row + 1])
            predicted = int(np.argmax(self.predict_proba(frame)[row]))
            vector = values[predicted][0] if isinstance(values, list) else np.asarray(values)[0, :, predicted]
            order = np.argsort(np.abs(vector))[::-1][:8]
            factors = []
            for position in order:
                value = float(vector[position])
                factors.append(
                    {
                        "name": self.columns[position],
                        "value": value,
                        "direction": "positive" if value > 0 else "negative",
                    }
                )
            return "shap", factors
        except Exception:
            return "unavailable", []

    @classmethod
    def fit(cls, frame: pd.DataFrame, labels: pd.Series) -> GradientBoostMatchModel:
        imputer = SimpleImputer(strategy="median")
        model = XGBClassifier(
            objective="multi:softprob",
            num_class=3,
            n_estimators=80,
            max_depth=3,
            learning_rate=0.08,
            subsample=0.9,
            colsample_bytree=0.9,
            eval_metric="mlogloss",
            random_state=7,
        )
        matrix = imputer.fit_transform(_prepare(frame))
        encoded = labels.map({name: index for index, name in enumerate(CLASSES)}).to_numpy()
        model.fit(matrix, encoded)
        return cls(imputer=imputer, model=model, class_labels=list(CLASSES))


def _prepare(frame: pd.DataFrame) -> pd.DataFrame:
    work = frame.reindex(columns=list(MODEL_FEATURE_COLUMNS)).copy()
    for column in work.columns:
        if work[column].isna().all():
            work[column] = 0.0
    return work

