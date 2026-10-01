"""Public football-data.co.uk feed."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.data.providers.football_data_uk import current_season_code, file_url, previous_season_code


def test_season_code_uses_august_as_start() -> None:
    august = datetime(2026, 8, 1, tzinfo=timezone.utc)
    june = datetime(2026, 6, 1, tzinfo=timezone.utc)
    assert current_season_code(august) == "2627"
    assert current_season_code(june) == "2526"
    assert previous_season_code("2627") == "2526"


def test_file_url_rejects_unknown_competition() -> None:
    assert file_url("E0", "2526").endswith("/2526/E0.csv")
    with pytest.raises(ValueError):
        file_url("ZZ", "2526")
