"""API smoke tests on an isolated database."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


def test_health(client) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert "garantissent" in response.json()["disclaimer"]


def test_matches_and_quality(client) -> None:
    matches = client.get("/matches")
    assert matches.status_code == 200
    assert matches.json()["items"]
    quality = client.get("/quality")
    assert quality.status_code == 200
    assert quality.json()["items"][0]["records_valid"] > 0


@pytest.mark.asyncio
async def test_health_async() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health")
    assert response.status_code == 200
