"""API schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str
    database: str
    disclaimer: str


class ImportResponse(BaseModel):
    records_total: int
    records_valid: int
    records_invalid: int
    missing_values: int
    duplicates: int
    future_leakage: int
    warnings: list[dict[str, object]]
    errors: list[dict[str, object]]


class TrainResponse(BaseModel):
    models: list[dict[str, object]]


class BacktestRequest(BaseModel):
    name: str = "walk-forward"
    staking: str = "FRACTIONAL_KELLY"
    window_mode: str = "expanding"
    rolling_days: int = 365
    commission: float = 0.0
    slippage: float = 0.0


class PredictionRequest(BaseModel):
    match_ids: list[int] | None = None


class SyncRequest(BaseModel):
    competitions: list[str] = Field(default_factory=lambda: ["E0"])
    season: str | None = None


class OddsUpdateRequest(BaseModel):
    match_id: int
    bookmaker: str
    market: str = "1X2"
    selection: str
    price: float | None = None
    captured_at: datetime
    action: str = "upsert"


class Message(BaseModel):
    disclaimer: str = Field(
        default="Les probabilités sont des estimations statistiques et ne garantissent aucun résultat."
    )
