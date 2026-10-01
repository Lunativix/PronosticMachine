"""Runtime settings loaded from the environment and an optional .env file."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[3]
BACKEND_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(PROJECT_ROOT / ".env", BACKEND_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = Field(
        default=f"sqlite:///{(PROJECT_ROOT / 'data' / 'sportwise.db').as_posix()}"
    )
    api_key: str = ""
    odds_api_key: str = ""
    data_provider: str = "csv"
    odds_provider: str = "csv"
    discord_webhook_url: str = ""
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    smtp_url: str = ""
    min_edge: float = 0.04
    min_ev: float = 0.03
    min_model_confidence: float = 0.55
    min_history_matches: int = 5
    initial_bankroll: float = 1000.0
    max_stake_percent: float = 0.02
    kelly_fraction: float = 0.25
    fixed_stake: float = 10.0
    model_retrain_days: int = 7
    use_market_features_in_model: bool = False
    fixture_provider: str = "espn"
    fixture_sync_interval_minutes: int = 60
    fixture_window_days: int = 60
    min_confidence_score: float = 55.0
    min_data_quality: float = 0.45
    max_combination_size: int = 5
    experimental_correlation: bool = False
    log_level: str = "INFO"
    backend_cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    @field_validator("database_url")
    @classmethod
    def absolute_sqlite(cls, value: str) -> str:
        prefix = "sqlite:///"
        if value.startswith(prefix) and "://" not in value[len(prefix) :]:
            raw = value[len(prefix) :]
            if raw.startswith("./") or raw.startswith(".\\"):
                path = (PROJECT_ROOT / raw[2:]).resolve()
                return prefix + path.as_posix()
        return value
    feature_version: str = "football-v1"
    api_football_base_url: str = "https://v3.football.api-sports.io"
    odds_api_base_url: str = "https://api.the-odds-api.com/v4"

    @property
    def project_root(self) -> Path:
        return PROJECT_ROOT

    @property
    def data_dir(self) -> Path:
        return PROJECT_ROOT / "data"

    @property
    def models_dir(self) -> Path:
        return self.data_dir / "models"

    @property
    def raw_dir(self) -> Path:
        return self.data_dir / "raw"

    @property
    def cors_origins(self) -> list[str]:
        return [item.strip() for item in self.backend_cors_origins.split(",") if item.strip()]

    def redacted(self) -> dict[str, str]:
        secret_keys = {
            "api_key",
            "odds_api_key",
            "discord_webhook_url",
            "telegram_bot_token",
            "smtp_url",
        }
        payload: dict[str, str] = {}
        for key, value in self.model_dump().items():
            payload[key] = "***" if key in secret_keys and value else str(value)
        return payload


@lru_cache
def get_settings() -> Settings:
    return Settings()
