"""Sportwise command line."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import typer

from app.backtesting.engine import run_backtest
from app.core.config import get_settings
from app.data.providers.registry import football_provider
from app.data.quality import validate_matches
from app.db.session import SessionLocal
from app.features.football import build_feature_table
from app.ml.train import train_all
from app.services.import_service import import_frame
from app.services.match_frame import matches_frame
from app.services.prediction_service import generate_predictions

app = typer.Typer(no_args_is_help=True, help="Sportwise AI statistical analysis toolkit.")
data_app = typer.Typer(help="Import and validate historical files.")
feature_app = typer.Typer(help="Build causal features.")
model_app = typer.Typer(help="Train and evaluate models.")
backtest_app = typer.Typer(help="Run walk-forward backtests.")
prediction_app = typer.Typer(help="Generate probabilistic estimates.")
app.add_typer(data_app, name="data")
app.add_typer(feature_app, name="features")
app.add_typer(model_app, name="model")
app.add_typer(backtest_app, name="backtest")
app.add_typer(prediction_app, name="prediction")
fixtures_app = typer.Typer(help="Sync and list upcoming fixtures.")
app.add_typer(fixtures_app, name="fixtures")


@data_app.command("import")
def data_import(path: Path, source: str = "import") -> None:
    settings = get_settings()
    frame = football_provider(settings, path).load()
    with SessionLocal() as session:
        report = import_frame(session, frame, source=source or path.name)
    typer.echo(report.as_dict())


@data_app.command("sync")
def data_sync(competitions: str = "E0", season: str = "") -> None:
    """Download real results from football-data.co.uk. Example: E0,F1,SP1,I1,D1."""
    from app.services.real_data import sync_real_matches

    codes = [item.strip() for item in competitions.split(",") if item.strip()]
    with SessionLocal() as session:
        payload = sync_real_matches(session, codes, season or None)
    typer.echo(payload)


@data_app.command("validate")
def data_validate(path: Path) -> None:
    settings = get_settings()
    _, report = validate_matches(football_provider(settings, path).load())
    typer.echo(report.as_dict())


@feature_app.command("build")
def features_build() -> None:
    with SessionLocal() as session:
        frame = matches_frame(session)
        features = build_feature_table(frame)
        from app.ml.train import _store_features

        _store_features(session, features)
        session.commit()
    typer.echo({"rows": int(len(features))})


@model_app.command("train")
def model_train() -> None:
    with SessionLocal() as session:
        versions = train_all(session)
    typer.echo([{"id": row.id, "model": row.model_key, "version": row.version, "metrics": row.metrics} for row in versions])


@model_app.command("evaluate")
def model_evaluate() -> None:
    from sqlalchemy import select

    from app.models import ModelVersion

    with SessionLocal() as session:
        rows = session.scalars(select(ModelVersion).where(ModelVersion.is_active.is_(True))).all()
        typer.echo(
            [
                {"model": row.model_key, "version": row.version, "metrics": row.metrics}
                for row in rows
            ]
        )


@backtest_app.command("run")
def backtest_run(staking: str = "FRACTIONAL_KELLY", window_mode: str = "expanding") -> None:
    with SessionLocal() as session:
        payload = run_backtest(session, staking=staking, window_mode=window_mode)
    typer.echo(payload["metrics"])


@prediction_app.command("generate")
def prediction_generate() -> None:
    with SessionLocal() as session:
        rows = generate_predictions(session)
    typer.echo({"count": len(rows)})


@fixtures_app.command("sync")
def fixtures_sync(days: int = 60, competition: str = "", force: bool = False, verbose: bool = False) -> None:
    from app.fixtures.scheduler import build_provider
    from app.fixtures.service import UpcomingMatchesService

    provider = build_provider()
    with SessionLocal() as session:
        run = UpcomingMatchesService(session, provider).sync(days=days, competition=competition or None)
    typer.echo(run.report if verbose or force or True else run.matches_found)


@fixtures_app.command("list")
def fixtures_list(days: int = 14) -> None:
    from app.fixtures.service import upcoming_query
    from app.fixtures.window import get_upcoming_window

    start, end = get_upcoming_window(days=days)
    with SessionLocal() as session:
        rows = upcoming_query(session, start, end, None, None)
        typer.echo({"total": len(rows), "start": start.isoformat(), "end": end.isoformat()})
        for row in rows:
            typer.echo(f"{row.kickoff_at.isoformat()} {row.status} {row.external_id} source={row.source}")


analysis_app = typer.Typer(help="Analyze upcoming matches and combinations.")
app.add_typer(analysis_app, name="analysis")


@analysis_app.command("form")
def analysis_form(competition: str = "") -> None:
    from app.analysis.preview_service import analyze_recent_form

    with SessionLocal() as session:
        typer.echo(analyze_recent_form(session, competition_code=competition or None))


@analysis_app.command("run")
def analysis_run() -> None:
    from app.analysis.service import analyze_upcoming_matches

    with SessionLocal() as session:
        typer.echo(analyze_upcoming_matches(session))


@app.command("dashboard")
def dashboard() -> None:
    frontend = get_settings().project_root / "frontend"
    typer.echo("Starting the dashboard on http://localhost:5173")
    subprocess.run(["npm", "run", "dev"], cwd=frontend, check=False)


if __name__ == "__main__":
    app()
