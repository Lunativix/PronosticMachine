"""FastAPI application."""

from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes.analysis import router as analysis_router
from app.api.routes.fixtures import router as fixtures_router
from app.api.routes.platform import router
from app.fixtures.scheduler import start_scheduler
from app.core.config import get_settings
from app.core.logging import configure_logging

settings = get_settings()
configure_logging(settings.log_level)

app = FastAPI(
    title="Sportwise AI",
    version="1.0.0",
    description=(
        "Statistical football analysis. Probabilities are estimates and do not guarantee any result."
    ),
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router)
app.include_router(fixtures_router)
app.include_router(analysis_router)


@app.on_event("startup")
def _start_fixture_sync() -> None:
    if os.environ.get("DISABLE_FIXTURE_SCHEDULER") == "1":
        return
    start_scheduler()
