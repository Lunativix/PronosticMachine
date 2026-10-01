"""Relational model. Odds rows are append-only snapshots."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, SourceMixin, utcnow


class Sport(Base):
    __tablename__ = "sports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True)
    name: Mapped[str] = mapped_column(String(80))
    competitions: Mapped[list[Competition]] = relationship(back_populates="sport")


class Competition(Base):
    __tablename__ = "competitions"
    __table_args__ = (UniqueConstraint("sport_id", "code"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    sport_id: Mapped[int] = mapped_column(ForeignKey("sports.id"))
    code: Mapped[str] = mapped_column(String(40))
    name: Mapped[str] = mapped_column(String(160))
    country: Mapped[str | None] = mapped_column(String(80))
    provider: Mapped[str] = mapped_column(String(40), default="")
    provider_competition_id: Mapped[str | None] = mapped_column(String(80))
    normalized_name: Mapped[str | None] = mapped_column(String(160))
    country_code: Mapped[str | None] = mapped_column(String(8))
    continent: Mapped[str | None] = mapped_column(String(40))
    gender: Mapped[str | None] = mapped_column(String(16))
    age_category: Mapped[str | None] = mapped_column(String(16))
    competition_type: Mapped[str | None] = mapped_column(String(32))
    tier: Mapped[int | None] = mapped_column(Integer)
    current_season: Mapped[str | None] = mapped_column(String(32))
    season_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    season_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    fixtures_available: Mapped[bool] = mapped_column(Boolean, default=False)
    odds_available: Mapped[bool] = mapped_column(Boolean, default=False)
    last_sync: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    source: Mapped[str | None] = mapped_column(String(64))
    sport: Mapped[Sport] = relationship(back_populates="competitions")
    seasons: Mapped[list[Season]] = relationship(back_populates="competition")


class Season(Base):
    __tablename__ = "seasons"
    __table_args__ = (UniqueConstraint("competition_id", "name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    competition_id: Mapped[int] = mapped_column(ForeignKey("competitions.id"))
    name: Mapped[str] = mapped_column(String(32))
    start_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    end_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    competition: Mapped[Competition] = relationship(back_populates="seasons")


class Team(Base):
    __tablename__ = "teams"
    __table_args__ = (UniqueConstraint("sport_id", "canonical_name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    sport_id: Mapped[int] = mapped_column(ForeignKey("sports.id"))
    name: Mapped[str] = mapped_column(String(120))
    canonical_name: Mapped[str] = mapped_column(String(120))
    country: Mapped[str | None] = mapped_column(String(80))
    logo_url: Mapped[str | None] = mapped_column(String(300))


class TeamAlias(Base):
    __tablename__ = "team_aliases"
    __table_args__ = (UniqueConstraint("alias"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"))
    alias: Mapped[str] = mapped_column(String(120))
    source: Mapped[str] = mapped_column(String(64), default="user")


class Player(Base):
    __tablename__ = "players"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    team_id: Mapped[int | None] = mapped_column(ForeignKey("teams.id"))
    name: Mapped[str] = mapped_column(String(120))
    position: Mapped[str | None] = mapped_column(String(40))
    external_id: Mapped[str | None] = mapped_column(String(64))


class Match(Base, SourceMixin):
    __tablename__ = "matches"
    __table_args__ = (
        UniqueConstraint(
            "competition_id",
            "kickoff_at",
            "home_team_id",
            "away_team_id",
            "source",
            name="uq_match_identity",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    competition_id: Mapped[int] = mapped_column(ForeignKey("competitions.id"))
    season_id: Mapped[int] = mapped_column(ForeignKey("seasons.id"))
    kickoff_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    home_team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"))
    away_team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"))
    home_goals: Mapped[int | None] = mapped_column(Integer)
    away_goals: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(24), default="scheduled")
    external_id: Mapped[str | None] = mapped_column(String(64))
    scheduled_at_local: Mapped[str | None] = mapped_column(String(40))
    venue: Mapped[str | None] = mapped_column(String(160))
    referee: Mapped[str | None] = mapped_column(String(120))
    round_name: Mapped[str | None] = mapped_column(String(80))
    matchday: Mapped[int | None] = mapped_column(Integer)
    first_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    source_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    analysis_state: Mapped[str | None] = mapped_column(String(32))


class MatchEvent(Base, SourceMixin):
    __tablename__ = "match_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id"), index=True)
    minute: Mapped[int | None] = mapped_column(Integer)
    event_type: Mapped[str] = mapped_column(String(40))
    team_id: Mapped[int | None] = mapped_column(ForeignKey("teams.id"))
    player_id: Mapped[int | None] = mapped_column(ForeignKey("players.id"))
    detail: Mapped[str | None] = mapped_column(Text)


class TeamStatistic(Base, SourceMixin):
    __tablename__ = "team_statistics"
    __table_args__ = (UniqueConstraint("match_id", "team_id", "source"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id"), index=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"))
    shots: Mapped[float | None] = mapped_column(Float)
    shots_on_target: Mapped[float | None] = mapped_column(Float)
    possession: Mapped[float | None] = mapped_column(Float)
    corners: Mapped[float | None] = mapped_column(Float)
    yellow_cards: Mapped[float | None] = mapped_column(Float)
    red_cards: Mapped[float | None] = mapped_column(Float)
    xg: Mapped[float | None] = mapped_column(Float)
    xga: Mapped[float | None] = mapped_column(Float)


class PlayerStatistic(Base, SourceMixin):
    __tablename__ = "player_statistics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id"), index=True)
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id"))
    team_id: Mapped[int | None] = mapped_column(ForeignKey("teams.id"))
    minutes: Mapped[float | None] = mapped_column(Float)
    goals: Mapped[float | None] = mapped_column(Float)
    assists: Mapped[float | None] = mapped_column(Float)
    shots: Mapped[float | None] = mapped_column(Float)
    xg: Mapped[float | None] = mapped_column(Float)


class Injury(Base, SourceMixin):
    __tablename__ = "injuries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    player_id: Mapped[int | None] = mapped_column(ForeignKey("players.id"))
    team_id: Mapped[int | None] = mapped_column(ForeignKey("teams.id"))
    match_id: Mapped[int | None] = mapped_column(ForeignKey("matches.id"))
    player_name: Mapped[str | None] = mapped_column(String(120))
    reason: Mapped[str | None] = mapped_column(String(160))
    status: Mapped[str] = mapped_column(String(40), default="unknown")
    start_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    end_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Bookmaker(Base):
    __tablename__ = "bookmakers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(String(120))


class Odds(Base, SourceMixin):
    """One row per quote. A later price inserts a new row."""

    __tablename__ = "odds"
    __table_args__ = (
        UniqueConstraint(
            "match_id",
            "bookmaker_id",
            "market",
            "selection",
            "captured_at",
            "status",
            name="uq_odds_snapshot",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id"), index=True)
    bookmaker_id: Mapped[int] = mapped_column(ForeignKey("bookmakers.id"))
    market: Mapped[str] = mapped_column(String(32))
    selection: Mapped[str] = mapped_column(String(32))
    price: Mapped[float | None] = mapped_column(Float)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    status: Mapped[str] = mapped_column(String(16), default="active")


class FeatureSnapshot(Base):
    __tablename__ = "features"
    __table_args__ = (UniqueConstraint("match_id", "feature_version"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id"), index=True)
    feature_version: Mapped[str] = mapped_column(String(40))
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    payload: Mapped[dict] = mapped_column(JSON)
    completeness: Mapped[float] = mapped_column(Float, default=0.0)


class ModelVersion(Base):
    __tablename__ = "model_versions"
    __table_args__ = (UniqueConstraint("model_key", "version"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    model_key: Mapped[str] = mapped_column(String(40))
    version: Mapped[str] = mapped_column(String(64))
    training_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    dataset_hash: Mapped[str] = mapped_column(String(64))
    feature_version: Mapped[str] = mapped_column(String(40))
    hyperparameters: Mapped[dict] = mapped_column(JSON)
    metrics: Mapped[dict] = mapped_column(JSON)
    training_period_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    training_period_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    validation_period_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    validation_period_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    test_period_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    test_period_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    artifact_path: Mapped[str] = mapped_column(String(300))
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)


class Prediction(Base):
    __tablename__ = "predictions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id"), index=True)
    model_version_id: Mapped[int | None] = mapped_column(ForeignKey("model_versions.id"))
    features_version: Mapped[str] = mapped_column(String(40))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    data_quality: Mapped[float] = mapped_column(Float, default=0.0)
    confidence: Mapped[float | None] = mapped_column(Float)
    state: Mapped[str] = mapped_column(String(32))
    signal_quality: Mapped[float | None] = mapped_column(Float)
    explanation: Mapped[dict] = mapped_column(JSON)
    explanation_method: Mapped[str] = mapped_column(String(40))
    probabilities_shrunk: Mapped[bool] = mapped_column(Boolean, default=False)


class PredictionProbability(Base):
    __tablename__ = "prediction_probabilities"
    __table_args__ = (UniqueConstraint("prediction_id", "selection"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    prediction_id: Mapped[int] = mapped_column(ForeignKey("predictions.id"), index=True)
    selection: Mapped[str] = mapped_column(String(16))
    probability_raw: Mapped[float] = mapped_column(Float)
    probability_calibrated: Mapped[float] = mapped_column(Float)


class BetOpportunity(Base):
    __tablename__ = "bet_opportunities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    prediction_id: Mapped[int | None] = mapped_column(ForeignKey("predictions.id"))
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id"), index=True)
    bookmaker_id: Mapped[int | None] = mapped_column(ForeignKey("bookmakers.id"))
    market: Mapped[str] = mapped_column(String(32))
    selection: Mapped[str] = mapped_column(String(32))
    odds: Mapped[float] = mapped_column(Float)
    model_probability: Mapped[float] = mapped_column(Float)
    market_probability: Mapped[float] = mapped_column(Float)
    edge: Mapped[float] = mapped_column(Float)
    expected_value: Mapped[float] = mapped_column(Float)
    signal_quality: Mapped[float] = mapped_column(Float)
    state: Mapped[str] = mapped_column(String(32))
    model_version_id: Mapped[int | None] = mapped_column(ForeignKey("model_versions.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    market_margin: Mapped[float | None] = mapped_column(Float)


class Alert(Base):
    __tablename__ = "alerts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    opportunity_id: Mapped[int | None] = mapped_column(ForeignKey("bet_opportunities.id"))
    message: Mapped[str] = mapped_column(String(200))
    payload: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    channel: Mapped[str] = mapped_column(String(32), default="internal")
    delivered: Mapped[bool] = mapped_column(Boolean, default=False)


class BacktestRun(Base):
    __tablename__ = "backtest_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    model_key: Mapped[str] = mapped_column(String(40))
    staking: Mapped[str] = mapped_column(String(40))
    window_mode: Mapped[str] = mapped_column(String(32))
    parameters: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    metrics: Mapped[dict] = mapped_column(JSON)


class BacktestResult(Base):
    __tablename__ = "backtest_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("backtest_runs.id"), index=True)
    match_id: Mapped[int | None] = mapped_column(ForeignKey("matches.id"))
    kickoff_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    market: Mapped[str] = mapped_column(String(32))
    selection: Mapped[str] = mapped_column(String(32))
    odds: Mapped[float] = mapped_column(Float)
    stake: Mapped[float] = mapped_column(Float)
    pnl: Mapped[float] = mapped_column(Float)
    bankroll_after: Mapped[float] = mapped_column(Float)
    edge: Mapped[float] = mapped_column(Float)
    expected_value: Mapped[float] = mapped_column(Float)
    outcome: Mapped[str] = mapped_column(String(16))
    state: Mapped[str] = mapped_column(String(32))
    trained_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    competition: Mapped[str | None] = mapped_column(String(120))
    season: Mapped[str | None] = mapped_column(String(32))
    bookmaker: Mapped[str | None] = mapped_column(String(64))
    model_key: Mapped[str | None] = mapped_column(String(40))
    confidence: Mapped[float | None] = mapped_column(Float)


class BankrollSnapshot(Base):
    __tablename__ = "bankroll_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[int | None] = mapped_column(ForeignKey("backtest_runs.id"))
    as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    bankroll: Mapped[float] = mapped_column(Float)
    drawdown: Mapped[float] = mapped_column(Float)
    peak: Mapped[float] = mapped_column(Float)


class DataQualityReport(Base):
    __tablename__ = "data_quality_reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    records_total: Mapped[int] = mapped_column(Integer)
    records_valid: Mapped[int] = mapped_column(Integer)
    records_invalid: Mapped[int] = mapped_column(Integer)
    missing_values: Mapped[int] = mapped_column(Integer, default=0)
    duplicates: Mapped[int] = mapped_column(Integer, default=0)
    future_leakage: Mapped[int] = mapped_column(Integer, default=0)
    warnings: Mapped[list] = mapped_column(JSON)
    errors: Mapped[list] = mapped_column(JSON)


class TeamProviderLink(Base):
    __tablename__ = "team_provider_links"
    __table_args__ = (UniqueConstraint("provider", "provider_team_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"))
    provider: Mapped[str] = mapped_column(String(40))
    provider_team_id: Mapped[str] = mapped_column(String(80))
    provider_name: Mapped[str] = mapped_column(String(120))
    review_status: Mapped[str] = mapped_column(String(24), default="confirmed")


class FixtureChange(Base):
    __tablename__ = "fixture_changes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id"), index=True)
    old_datetime: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    new_datetime: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    old_status: Mapped[str | None] = mapped_column(String(24))
    new_status: Mapped[str | None] = mapped_column(String(24))
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    source: Mapped[str] = mapped_column(String(64))


class FixtureSyncRun(Base):
    __tablename__ = "fixture_sync_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(24), default="running")
    window_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    window_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    provider: Mapped[str] = mapped_column(String(40), default="")
    matches_found: Mapped[int] = mapped_column(Integer, default=0)
    matches_inserted: Mapped[int] = mapped_column(Integer, default=0)
    matches_updated: Mapped[int] = mapped_column(Integer, default=0)
    matches_unchanged: Mapped[int] = mapped_column(Integer, default=0)
    rescheduled: Mapped[int] = mapped_column(Integer, default=0)
    cancelled: Mapped[int] = mapped_column(Integer, default=0)
    errors: Mapped[list] = mapped_column(JSON, default=list)
    report: Mapped[str] = mapped_column(Text, default="")


class MarketAnalysis(Base):
    """Append-only selection analysis. Older rows are never deleted or rewritten."""

    __tablename__ = "market_analyses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    model_version_id: Mapped[int | None] = mapped_column(ForeignKey("model_versions.id"))
    model_version: Mapped[str] = mapped_column(String(64), default="")
    market: Mapped[str] = mapped_column(String(32))
    selection: Mapped[str] = mapped_column(String(32))
    odds: Mapped[float | None] = mapped_column(Float)
    model_probability: Mapped[float | None] = mapped_column(Float)
    market_probability: Mapped[float | None] = mapped_column(Float)
    edge: Mapped[float | None] = mapped_column(Float)
    expected_value: Mapped[float | None] = mapped_column(Float)
    confidence_score: Mapped[float] = mapped_column(Float, default=0.0)
    confidence_level: Mapped[str] = mapped_column(String(16), default="VERY_LOW")
    signal: Mapped[str] = mapped_column(String(32))
    data_quality: Mapped[float] = mapped_column(Float, default=0.0)
    sample_size: Mapped[int] = mapped_column(Integer, default=0)
    calibration: Mapped[float | None] = mapped_column(Float)
    model_agreement: Mapped[float | None] = mapped_column(Float)
    explanation: Mapped[dict] = mapped_column(JSON)
    sufficient_data: Mapped[bool] = mapped_column(Boolean, default=False)


class CombinationAnalysis(Base):
    """Append-only combination snapshot."""

    __tablename__ = "combination_analyses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    category: Mapped[str] = mapped_column(String(16))
    size: Mapped[int] = mapped_column(Integer)
    combined_odds: Mapped[float | None] = mapped_column(Float)
    combined_probability: Mapped[float | None] = mapped_column(Float)
    combined_ev: Mapped[float | None] = mapped_column(Float)
    confidence_score: Mapped[float] = mapped_column(Float, default=0.0)
    correlation_risk: Mapped[str] = mapped_column(String(16))
    correlation_status: Mapped[str] = mapped_column(String(32))
    combination_scope: Mapped[str] = mapped_column(String(32))
    selections: Mapped[list] = mapped_column(JSON)


class InformationItem(Base):
    """One public fact. The same key is updated, never duplicated."""

    __tablename__ = "information_items"
    __table_args__ = (UniqueConstraint("external_key"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    kind: Mapped[str] = mapped_column(String(24))
    source: Mapped[str] = mapped_column(String(80))
    external_key: Mapped[str] = mapped_column(String(240))
    title: Mapped[str] = mapped_column(String(300))
    url: Mapped[str | None] = mapped_column(String(400))
    body: Mapped[str | None] = mapped_column(Text)


class TrackedProposition(Base):
    """One recorded pick per match. The probability is frozen; only the result status changes."""

    __tablename__ = "tracked_propositions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    selection: Mapped[str] = mapped_column(String(16))
    selection_label: Mapped[str] = mapped_column(String(120))
    odds: Mapped[float | None] = mapped_column(Float)
    raw_probability: Mapped[float] = mapped_column(Float)
    calibrated_probability: Mapped[float] = mapped_column(Float)
    confidence_score: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[str] = mapped_column(String(16), default="OPEN")
    strategy: Mapped[str] = mapped_column(String(24), default="agent")
    paper_profit: Mapped[float | None] = mapped_column(Float)
    settled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    home_goals: Mapped[int | None] = mapped_column(Integer)
    away_goals: Mapped[int | None] = mapped_column(Integer)
