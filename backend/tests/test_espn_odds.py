"""ESPN prices are converted only when the provider sends them."""

from app.fixtures.providers.espn import american_to_decimal, extract_odds


def test_american_moneyline_to_decimal() -> None:
    assert american_to_decimal(-200) == 1.5
    assert american_to_decimal(150) == 2.5
    assert american_to_decimal(None) is None
    assert american_to_decimal("") is None


def test_extract_odds_skips_missing_prices() -> None:
    quotes = extract_odds(
        {
            "odds": [
                {
                    "provider": {"name": "DraftKings"},
                    "overUnder": 2.5,
                    "moneyline": {
                        "home": {"close": {"odds": "-150"}},
                        "away": {"close": {"odds": "+240"}},
                        "draw": {"close": {"odds": "+220"}},
                    },
                    "total": {"over": {"close": {"odds": "-110"}}, "under": {}},
                }
            ]
        }
    )
    stored = {(row["market"], row["selection"]): row["price"] for row in quotes}
    assert stored[("1X2", "home")] == 1.6667
    assert ("over_under", "under_2.5") not in stored
    assert ("over_under", "over_2.5") in stored


def test_no_odds_block_creates_no_quotes() -> None:
    assert extract_odds({}) == []
