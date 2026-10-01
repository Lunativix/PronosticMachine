"""Input and artifact guards. External pickle files are never loaded."""

from __future__ import annotations

from pathlib import Path

import joblib

ARTIFACT_MARKER = "sportwise_artifact"


class UntrustedArtifactError(ValueError):
    """Raised when a model file was not produced by Sportwise."""


def ensure_under(path: Path, root: Path) -> Path:
    resolved = path.resolve()
    root_resolved = root.resolve()
    if root_resolved != resolved and root_resolved not in resolved.parents:
        raise ValueError(f"Path escapes allowed directory: {path}")
    return resolved


def save_artifact(path: Path, model: object, metadata: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(
        {ARTIFACT_MARKER: True, "metadata": metadata, "model": model},
        path,
    )


def load_artifact(path: Path, models_root: Path) -> dict[str, object]:
    resolved = ensure_under(path, models_root)
    payload = joblib.load(resolved)
    if not isinstance(payload, dict) or payload.get(ARTIFACT_MARKER) is not True:
        raise UntrustedArtifactError("Refusing to load an artifact not created by Sportwise.")
    return payload
