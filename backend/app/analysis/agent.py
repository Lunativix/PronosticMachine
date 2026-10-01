"""Pick one real outcome per match. Probabilities come from stored analyses only."""

from __future__ import annotations

LABELS = {"home": "domicile", "draw": "nul", "away": "extérieur"}


def build_pronostics(readings: list[dict], *, limit: int = 12) -> list[dict]:
    picks: list[dict] = []
    for reading in readings:
        markets = [
            market
            for market in reading.get("markets") or []
            if market.get("selection") in LABELS
            and market.get("model_probability") is not None
            and market.get("odds") is not None
            and 1.40 <= float(market["odds"]) <= 3.50
        ]
        if not markets:
            continue
        chosen = max(markets, key=lambda market: float(market["model_probability"]))
        home = reading.get("home_team") or _side(reading.get("match") or "", 0)
        away = reading.get("away_team") or _side(reading.get("match") or "", 1)
        name = {"home": home, "draw": "Nul", "away": away}[str(chosen["selection"])]
        narrative = [line for line in (reading.get("narrative") or []) if isinstance(line, str)]
        picks.append(
            {
                "match_id": reading.get("match_id"),
                "match": reading.get("match"),
                "competition": reading.get("competition"),
                "date": reading.get("date"),
                "kickoff_local": reading.get("kickoff_local"),
                "selection": chosen["selection"],
                "selection_label": name,
                "odds": chosen.get("odds"),
                "model_probability": chosen.get("model_probability"),
                "market_probability": chosen.get("market_probability"),
                "edge": chosen.get("edge"),
                "ev": chosen.get("ev"),
                "confidence_score": chosen.get("confidence_score"),
                "data_quality": chosen.get("data_quality"),
                "reason": _reason(name, chosen, narrative),
            }
        )
    picks.sort(key=lambda row: float(row["model_probability"] or 0), reverse=True)
    return picks[:limit]


def _side(match: str, index: int) -> str:
    parts = match.split(" vs ")
    return parts[index] if len(parts) > index else "Donnée indisponible"


def _reason(name: str, market: dict, narrative: list[str]) -> str:
    probability = float(market["model_probability"]) * 100
    odds = float(market["odds"])
    facts = [line for line in narrative if "forme" in line.casefold() or "buts" in line.casefold()][:2]
    body = " ".join(facts) if facts else "Les derniers résultats publiés servent de base."
    return (
        f"L'agent retient {name}. Le modèle de forme lui donne {probability:.1f} % "
        f"pour une cote réelle de {odds:.2f}. {body} Ce n'est pas un pari sûr."
    )
