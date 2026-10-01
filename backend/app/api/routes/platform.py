"""HTTP routes."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.analytics.performance import performance
from app.backtesting.engine import run_backtest
from app.core.config import get_settings
from app.core.security import ensure_under
from app.data.providers.registry import football_provider
from app.data.quality import validate_matches
from app.db.session import get_db
from app.ml.train import train_all
from app.models import (
    BacktestResult,
    BacktestRun,
    BankrollSnapshot,
    BetOpportunity,
    DataQualityReport,
    Match,
    ModelVersion,
    Odds,
    Prediction,
    PredictionProbability,
    Team,
)
from app.data.providers.football_data_uk import RemoteDataError
from app.schemas.api import (
    BacktestRequest,
    HealthResponse,
    ImportResponse,
    OddsUpdateRequest,
    PredictionRequest,
    SyncRequest,
)
from app.services.real_data import sync_real_matches
from app.services.import_service import import_frame
from app.services.odds_update import apply_odds_update
from app.services.prediction_service import generate_predictions

router = APIRouter()
DISCLAIMER = "Les probabilités sont des estimations statistiques et ne garantissent aucun résultat."


@router.get("/health", response_model=HealthResponse)
def health(db: Session = Depends(get_db)) -> HealthResponse:
    db.execute(select(1))
    return HealthResponse(status="ok", database="ok", disclaimer=DISCLAIMER)


@router.get("/matches")
def list_matches(db: Session = Depends(get_db), limit: int = Query(100, le=500), offset: int = 0) -> dict:
    rows = db.scalars(select(Match).order_by(Match.kickoff_at.desc()).offset(offset).limit(limit)).all()
    return {"disclaimer": DISCLAIMER, "items": [_match(db, row) for row in rows]}


@router.get("/matches/{match_id}")
def get_match(match_id: int, db: Session = Depends(get_db)) -> dict:
    row = db.get(Match, match_id)
    if row is None:
        raise HTTPException(404, "Match not found")
    return {"disclaimer": DISCLAIMER, **_match(db, row)}


@router.get("/matches/{match_id}/prediction")
def match_prediction(match_id: int, db: Session = Depends(get_db)) -> dict:
    prediction = db.scalar(
        select(Prediction).where(Prediction.match_id == match_id).order_by(Prediction.created_at.desc())
    )
    if prediction is None:
        raise HTTPException(404, "No prediction for this match")
    return {"disclaimer": DISCLAIMER, **_prediction(db, prediction)}


@router.get("/matches/{match_id}/value")
def match_value(match_id: int, db: Session = Depends(get_db)) -> dict:
    rows = db.scalars(select(BetOpportunity).where(BetOpportunity.match_id == match_id)).all()
    return {"disclaimer": DISCLAIMER, "items": [_opportunity(db, row) for row in rows]}


@router.get("/predictions")
def list_predictions(db: Session = Depends(get_db), limit: int = Query(100, le=500)) -> dict:
    rows = db.scalars(select(Prediction).order_by(Prediction.created_at.desc()).limit(limit)).all()
    return {"disclaimer": DISCLAIMER, "items": [_prediction(db, row) for row in rows]}


@router.get("/opportunities")
def list_opportunities(
    db: Session = Depends(get_db),
    state: str | None = None,
    min_edge: float | None = None,
    min_ev: float | None = None,
    min_quality: float | None = None,
) -> dict:
    statement = select(BetOpportunity)
    if state:
        statement = statement.where(BetOpportunity.state == state)
    if min_edge is not None:
        statement = statement.where(BetOpportunity.edge >= min_edge)
    if min_ev is not None:
        statement = statement.where(BetOpportunity.expected_value >= min_ev)
    if min_quality is not None:
        statement = statement.where(BetOpportunity.signal_quality >= min_quality)
    rows = db.scalars(statement.order_by(BetOpportunity.expected_value.desc())).all()
    return {"disclaimer": DISCLAIMER, "items": [_opportunity(db, row) for row in rows]}


@router.get("/odds")
def list_odds(db: Session = Depends(get_db), match_id: int | None = None) -> dict:
    statement = select(Odds).order_by(Odds.captured_at)
    if match_id is not None:
        statement = statement.where(Odds.match_id == match_id)
    rows = db.scalars(statement.limit(500)).all()
    return {
        "disclaimer": DISCLAIMER,
        "items": [
            {
                "id": row.id,
                "match_id": row.match_id,
                "market": row.market,
                "selection": row.selection,
                "price": row.price,
                "captured_at": row.captured_at.isoformat(),
                "status": row.status,
                "source": row.source,
            }
            for row in rows
        ],
    }


@router.post("/odds/updates")
def update_odds(body: OddsUpdateRequest, db: Session = Depends(get_db)) -> dict:
    row = apply_odds_update(
        db,
        match_id=body.match_id,
        bookmaker_code=body.bookmaker,
        market=body.market,
        selection=body.selection,
        price=body.price,
        captured_at=body.captured_at,
        action=body.action,
    )
    return {"disclaimer": DISCLAIMER, "id": row.id, "status": row.status, "price": row.price}


@router.get("/backtests")
def list_backtests(db: Session = Depends(get_db)) -> dict:
    rows = db.scalars(select(BacktestRun).order_by(BacktestRun.created_at.desc())).all()
    return {
        "disclaimer": DISCLAIMER,
        "items": [{"id": row.id, "name": row.name, "metrics": row.metrics, "staking": row.staking} for row in rows],
    }


@router.get("/backtests/{run_id}")
def get_backtest(run_id: int, db: Session = Depends(get_db)) -> dict:
    row = db.get(BacktestRun, run_id)
    if row is None:
        raise HTTPException(404, "Backtest not found")
    results = db.scalars(select(BacktestResult).where(BacktestResult.run_id == run_id)).all()
    snapshots = db.scalars(
        select(BankrollSnapshot).where(BankrollSnapshot.run_id == run_id).order_by(BankrollSnapshot.as_of)
    ).all()
    return {
        "disclaimer": DISCLAIMER,
        "id": row.id,
        "metrics": row.metrics,
        "results": [
            {"match_id": item.match_id, "pnl": item.pnl, "stake": item.stake, "odds": item.odds, "selection": item.selection}
            for item in results
        ],
        "bankroll": [{"as_of": item.as_of.isoformat(), "bankroll": item.bankroll, "drawdown": item.drawdown} for item in snapshots],
    }


@router.get("/models")
def list_models(db: Session = Depends(get_db)) -> dict:
    rows = db.scalars(select(ModelVersion).order_by(ModelVersion.training_date.desc())).all()
    return {"disclaimer": DISCLAIMER, "items": [_model(row) for row in rows]}


@router.get("/models/{model_id}")
def get_model(model_id: int, db: Session = Depends(get_db)) -> dict:
    row = db.get(ModelVersion, model_id)
    if row is None:
        raise HTTPException(404, "Model not found")
    return {"disclaimer": DISCLAIMER, **_model(row)}


@router.get("/analytics/performance")
def analytics(db: Session = Depends(get_db)) -> dict:
    return {"disclaimer": DISCLAIMER, **performance(db)}


@router.get("/quality")
def quality(db: Session = Depends(get_db)) -> dict:
    rows = db.scalars(select(DataQualityReport).order_by(DataQualityReport.created_at.desc()).limit(20)).all()
    return {
        "disclaimer": DISCLAIMER,
        "items": [
            {
                "id": row.id,
                "source": row.source,
                "records_total": row.records_total,
                "records_valid": row.records_valid,
                "records_invalid": row.records_invalid,
                "missing_values": row.missing_values,
                "duplicates": row.duplicates,
                "future_leakage": row.future_leakage,
                "warnings": row.warnings,
                "errors": row.errors,
                "created_at": row.created_at.isoformat(),
            }
            for row in rows
        ],
    }


@router.post("/data/import", response_model=ImportResponse)
def import_data(
    file: UploadFile | None = File(default=None),
    path: str | None = None,
    db: Session = Depends(get_db),
) -> ImportResponse:
    settings = get_settings()
    if file is not None:
        destination = ensure_under(settings.raw_dir / Path(file.filename or "upload.csv").name, settings.raw_dir)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(file.file.read())
        target = destination
    elif path:
        target = ensure_under(Path(path), settings.project_root)
    else:
        raise HTTPException(400, "Provide a file or a path inside the project.")
    if target.suffix.lower() not in {".csv", ".json"}:
        raise HTTPException(400, "Only CSV and JSON imports are accepted.")
    provider = football_provider(settings, target)
    report = import_frame(db, provider.load(), source=target.name)
    return ImportResponse(**report.as_dict())


@router.post("/data/sync")
def sync_real_data(body: SyncRequest, db: Session = Depends(get_db)) -> dict:
    """Download real results from football-data.co.uk and store them."""
    try:
        payload = sync_real_matches(db, body.competitions, body.season)
    except (ValueError, RemoteDataError) as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"disclaimer": DISCLAIMER, **payload}


@router.get("/data/sources")
def data_sources() -> dict:
    from app.data.providers.csv_provider import DIVISIONS

    return {
        "disclaimer": DISCLAIMER,
        "provider": "football-data.co.uk",
        "requires_api_key": False,
        "competitions": [{"code": code, "name": name} for code, name in sorted(DIVISIONS.items())],
        "note": "API_KEY remains optional for API-Football. This source is the public historical file feed.",
    }


@router.post("/data/validate")
def validate_data(path: str, db: Session = Depends(get_db)) -> dict:
    settings = get_settings()
    target = ensure_under(Path(path), settings.project_root)
    provider = football_provider(settings, target)
    _, report = validate_matches(provider.load())
    return {"disclaimer": DISCLAIMER, **report.as_dict()}


@router.post("/models/train", response_model=None)
def train_models(db: Session = Depends(get_db)) -> dict:
    try:
        versions = train_all(db)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"disclaimer": DISCLAIMER, "models": [_model(row) for row in versions]}


@router.post("/backtests/run")
def start_backtest(body: BacktestRequest, db: Session = Depends(get_db)) -> dict:
    if body.window_mode not in {"expanding", "rolling"}:
        raise HTTPException(400, "window_mode must be expanding or rolling.")
    if body.staking not in {"FIXED_STAKE", "PERCENT_BANKROLL", "KELLY", "FRACTIONAL_KELLY"}:
        raise HTTPException(400, "Unknown staking method.")
    payload = run_backtest(
        db,
        staking=body.staking,
        window_mode=body.window_mode,
        rolling_days=body.rolling_days,
        name=body.name,
        commission=body.commission,
        slippage=body.slippage,
    )
    return {
        "disclaimer": DISCLAIMER,
        "run_id": payload.get("run_id"),
        "metrics": payload["metrics"],
    }


@router.post("/predictions/generate")
def create_predictions(body: PredictionRequest, db: Session = Depends(get_db)) -> dict:
    try:
        rows = generate_predictions(db, body.match_ids)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"disclaimer": DISCLAIMER, "count": len(rows), "items": [_prediction(db, row) for row in rows]}


def _team(db: Session, team_id: int) -> str:
    team = db.get(Team, team_id)
    return "" if team is None else team.name


def _match(db: Session, row: Match) -> dict:
    return {
        "id": row.id,
        "kickoff": row.kickoff_at.isoformat(),
        "home_team": _team(db, row.home_team_id),
        "away_team": _team(db, row.away_team_id),
        "home_goals": row.home_goals,
        "away_goals": row.away_goals,
        "status": row.status,
        "source": row.source,
        "imported_at": row.imported_at.isoformat(),
    }


def _prediction(db: Session, row: Prediction) -> dict:
    probabilities = db.scalars(
        select(PredictionProbability).where(PredictionProbability.prediction_id == row.id)
    ).all()
    model = db.get(ModelVersion, row.model_version_id) if row.model_version_id else None
    return {
        "id": row.id,
        "match_id": row.match_id,
        "state": row.state,
        "confidence": row.confidence,
        "signal_quality": row.signal_quality,
        "data_quality": row.data_quality,
        "probabilities_shrunk": row.probabilities_shrunk,
        "explanation_method": row.explanation_method,
        "explanation": row.explanation,
        "features_version": row.features_version,
        "model_version": None if model is None else f"{model.model_key}:{model.version}",
        "created_at": row.created_at.isoformat(),
        "probabilities": [
            {
                "selection": item.selection,
                "raw": item.probability_raw,
                "calibrated": item.probability_calibrated,
            }
            for item in probabilities
        ],
    }


def _opportunity(db: Session, row: BetOpportunity) -> dict:
    match = _match(db, db.get(Match, row.match_id))
    return {
        "id": row.id,
        "match_id": row.match_id,
        "match": f"{match['home_team']} vs {match['away_team']}",
        "kickoff": match["kickoff"],
        "market": row.market,
        "selection": row.selection,
        "odds": row.odds,
        "model_probability": row.model_probability,
        "market_probability": row.market_probability,
        "edge": row.edge,
        "expected_value": row.expected_value,
        "signal_quality": row.signal_quality,
        "state": row.state,
        "label": "Model Signal" if row.state == "SIGNAL" else row.state,
    }


def _model(row: ModelVersion) -> dict:
    return {
        "id": row.id,
        "model_key": row.model_key,
        "version": row.version,
        "training_date": row.training_date.isoformat(),
        "dataset_hash": row.dataset_hash,
        "feature_version": row.feature_version,
        "hyperparameters": row.hyperparameters,
        "metrics": row.metrics,
        "is_active": row.is_active,
        "artifact_path": row.artifact_path,
        "training_period_start": _iso(row.training_period_start),
        "training_period_end": _iso(row.training_period_end),
        "validation_period_start": _iso(row.validation_period_start),
        "validation_period_end": _iso(row.validation_period_end),
        "test_period_start": _iso(row.test_period_start),
        "test_period_end": _iso(row.test_period_end),
    }


def _iso(value: object) -> str | None:
    if value is None:
        return None
    return value.isoformat()  # type: ignore[no-any-return]
