"""Shared fixtures. The database is an isolated SQLite file."""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ["DISABLE_FIXTURE_SCHEDULER"] = "1"

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "scripts"))

from app.core.config import get_settings  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.db.session import make_engine, make_session_factory  # noqa: E402
from app.main import app  # noqa: E402
from app.services.import_service import import_frame  # noqa: E402
from generate_test_data import generate  # noqa: E402


@pytest.fixture()
def session(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Session:
    url = f"sqlite:///{(tmp_path / 'test.db').as_posix()}"
    monkeypatch.setenv("DATABASE_URL", url)
    get_settings.cache_clear()
    engine = make_engine(url)
    Base.metadata.create_all(engine)
    factory = make_session_factory(url)
    db = factory()
    try:
        yield db
    finally:
        db.close()
        engine.dispose()
        get_settings.cache_clear()


@pytest.fixture()
def seeded_session(session: Session) -> Session:
    frame = generate(rounds=8)
    import_frame(session, frame, source="synthetic")
    return session


@pytest.fixture()
def client(seeded_session: Session, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    from app.db import session as session_module
    from app.main import app as application

    url = str(seeded_session.get_bind().url)
    get_settings.cache_clear()
    monkeypatch.setattr(session_module, "SessionLocal", make_session_factory(url))
    monkeypatch.setattr(session_module, "engine", seeded_session.get_bind())

    def override():
        db = session_module.SessionLocal()
        try:
            yield db
        finally:
            db.close()

    application.dependency_overrides[session_module.get_db] = override
    with TestClient(application) as test_client:
        yield test_client
    application.dependency_overrides.clear()
