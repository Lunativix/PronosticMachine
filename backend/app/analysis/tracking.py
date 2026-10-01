"""Record one proposition per match and learn from later results. Past probabilities stay frozen."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.analysis.agent import build_pronostics
from app.db.base import utcnow
from app.models import Match, TrackedProposition

PRIOR_STRENGTH = 30
BIN_PRIOR = 12
MIN_LEARNING_SAMPLE = 8


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def counts_for_learning(created: datetime | None, kickoff: datetime | None) -> bool:
    """A pick recorded after kickoff already knows the match has started."""
    if created is None or kickoff is None:
        return False
    return _utc(created) < _utc(kickoff)


def kickoff_still_ahead(kickoff: datetime | None, now: datetime | None = None) -> bool:
    if kickoff is None:
        return False
    moment = now or datetime.now(timezone.utc)
    return _utc(kickoff) > _utc(moment)


def probability_bin(probability: float) -> str:
    if probability < 0.45:
        return "basse"
    if probability < 0.55:
        return "moyenne"
    if probability < 0.65:
        return "haute"
    return "favorite"


def calibrate_new(probability: float, strategy: str, samples: list[tuple[str, float, bool]]) -> float:
    """Shrink toward the observed rate of the same reading and the same probability band."""
    band = probability_bin(probability)
    same_band = [won for name, raw, won in samples if name == strategy and probability_bin(raw) == band]
    same_strategy = [won for name, _raw, won in samples if name == strategy]
    pool = same_band if len(same_band) >= MIN_LEARNING_SAMPLE else same_strategy
    if len(pool) < MIN_LEARNING_SAMPLE:
        return probability
    hit_rate = sum(pool) / len(pool)
    weight = len(pool) / (len(pool) + BIN_PRIOR)
    return (1 - weight) * probability + weight * hit_rate


def _kickoffs(session: Session, match_ids: set[int]) -> dict[int, datetime | None]:
    if not match_ids:
        return {}
    rows = session.execute(select(Match.id, Match.kickoff_at).where(Match.id.in_(match_ids))).all()
    return {match_id: kickoff for match_id, kickoff in rows}


def honest_samples(session: Session) -> list[tuple[str, float, bool]]:
    rows = session.scalars(select(TrackedProposition).where(TrackedProposition.status.in_(("WON", "LOST")))).all()
    kickoffs = _kickoffs(session, {row.match_id for row in rows})
    return [
        (row.strategy or "agent", row.raw_probability, row.status == "WON")
        for row in rows
        if counts_for_learning(row.created_at, kickoffs.get(row.match_id))
    ]


def calibration(session: Session) -> dict[str, float | int | None]:
    samples = honest_samples(session)
    if len(samples) < MIN_LEARNING_SAMPLE:
        return {"settled": len(samples), "weight": 0.0, "hit_rate": None if not samples else sum(won for _name, _raw, won in samples) / len(samples), "mean_raw": None}
    hits = sum(won for _name, _raw, won in samples)
    hit_rate = hits / len(samples)
    weight = len(samples) / (len(samples) + PRIOR_STRENGTH)
    return {"settled": len(samples), "weight": weight, "hit_rate": hit_rate, "mean_raw": None}


def apply_calibration(probability: float, learned: dict[str, float | int | None]) -> float:
    weight = float(learned["weight"] or 0)
    hit_rate = learned["hit_rate"]
    if weight <= 0 or hit_rate is None:
        return probability
    return (1 - weight) * probability + weight * float(hit_rate)


def sync_propositions(session: Session, readings: list[dict]) -> dict[str, int]:
    samples = honest_samples(session)
    existing = {
        row.match_id: row
        for row in session.scalars(select(TrackedProposition).where(TrackedProposition.status == "OPEN", TrackedProposition.strategy == "agent")).all()
    }
    created = 0
    for pick in build_pronostics(readings, limit=500):
        match_id = int(pick["match_id"])
        match = session.get(Match, match_id)
        if match is None or not kickoff_still_ahead(match.kickoff_at):
            continue
        current = existing.get(match_id)
        if current is not None and current.selection == pick["selection"]:
            continue
        if current is not None:
            current.status = "VOID"
        raw = float(pick["model_probability"])
        session.add(
            TrackedProposition(
                match_id=match_id,
                created_at=utcnow(),
                selection=str(pick["selection"]),
                selection_label=str(pick["selection_label"]),
                odds=pick.get("odds"),
                raw_probability=raw,
                calibrated_probability=calibrate_new(raw, "agent", samples),
                confidence_score=float(pick.get("confidence_score") or 0),
                status="OPEN",
            )
        )
        created += 1
    settled = _settle(session)
    session.commit()
    return {"created": created, "settled": settled}


def _settle(session: Session) -> int:
    count = 0
    rows = session.scalars(select(TrackedProposition).where(TrackedProposition.status == "OPEN")).all()
    for row in rows:
        match = session.get(Match, row.match_id)
        if match is None or match.home_goals is None or match.away_goals is None:
            continue
        if str(match.status).lower() != "finished":
            continue
        won = _won(match.home_goals, match.away_goals, row.selection)
        row.status = "WON" if won else "LOST"
        row.home_goals = match.home_goals
        row.away_goals = match.away_goals
        row.paper_profit = _paper_profit(won, row.odds)
        row.settled_at = utcnow()
        count += 1
    return count


def _paper_profit(won: bool, odds: float | None) -> float | None:
    """Unit stake with no money. A missing price cannot be scored as a win or a loss of cash."""
    if odds is None:
        return None
    return round(float(odds) - 1, 4) if won else -1.0


def experiment_report(session: Session) -> list[dict[str, object]]:
    rows = session.scalars(select(TrackedProposition).where(TrackedProposition.status.in_(("WON", "LOST")))).all()
    kickoffs = _kickoffs(session, {row.match_id for row in rows})
    grouped: dict[str, list[TrackedProposition]] = {}
    for row in rows:
        if not counts_for_learning(row.created_at, kickoffs.get(row.match_id)):
            continue
        grouped.setdefault(row.strategy or "agent", []).append(row)
    report = []
    for strategy, items in sorted(grouped.items()):
        hits = sum(1 for item in items if item.status == "WON")
        profits = [item.paper_profit for item in items if item.paper_profit is not None]
        report.append(
            {
                "strategy": strategy,
                "settled": len(items),
                "won": hits,
                "lost": len(items) - hits,
                "hit_rate": hits / len(items),
                "paper_profit": round(sum(profits), 4) if profits else None,
            }
        )
    return report


def record_experiments(session: Session, readings: list[dict]) -> dict[str, int]:
    """Paper picks. One open row per match and strategy. Results stay unknown until the score exists."""
    open_rows = session.scalars(select(TrackedProposition).where(TrackedProposition.status == "OPEN")).all()
    open_keys = {(row.match_id, row.strategy or "agent") for row in open_rows}
    samples = honest_samples(session)
    created = 0
    for reading in readings:
        match_id = reading.get("match_id")
        if match_id is None:
            continue
        match = session.get(Match, int(match_id))
        if match is None or not kickoff_still_ahead(match.kickoff_at):
            continue
        for strategy, market in _experiment_markets(reading).items():
            key = (int(match_id), strategy)
            if key in open_keys:
                continue
            raw = float(market["model_probability"])
            session.add(
                TrackedProposition(
                    match_id=int(match_id),
                    created_at=utcnow(),
                    selection=str(market["selection"]),
                    selection_label=str(market["label"]),
                    odds=market.get("odds"),
                    raw_probability=raw,
                    calibrated_probability=calibrate_new(raw, strategy, samples),
                    confidence_score=float(market.get("confidence_score") or 0),
                    status="OPEN",
                    strategy=strategy,
                )
            )
            open_keys.add(key)
            created += 1
    settled = _settle(session)
    session.commit()
    return {"created": created, "settled": settled}


def _experiment_markets(reading: dict) -> dict[str, dict]:
    markets = [
        market
        for market in reading.get("markets") or []
        if market.get("selection") in {"home", "draw", "away"}
        and market.get("model_probability") is not None
        and market.get("odds") is not None
        and 1.40 <= float(market["odds"]) <= 3.50
    ]
    if not markets:
        return {}
    home = reading.get("home_team") or "Domicile"
    away = reading.get("away_team") or "Extérieur"

    def labeled(market: dict) -> dict:
        name = {"home": home, "draw": "Nul", "away": away}[str(market["selection"])]
        return {**market, "label": name}

    chosen = {"probabilite": labeled(max(markets, key=lambda market: float(market["model_probability"])))}
    valued = [market for market in markets if market.get("ev") is not None and float(market["ev"]) > 0 and float(market["model_probability"]) >= 0.45]
    if valued:
        chosen["value"] = labeled(max(valued, key=lambda market: float(market["ev"])))
    short = [market for market in markets if float(market["odds"]) <= 1.80 and float(market["model_probability"]) >= 0.55]
    if short:
        chosen["favorite"] = labeled(max(short, key=lambda market: float(market["model_probability"])))
    return chosen


def _won(home_goals: int, away_goals: int, selection: str) -> bool:
    if selection == "home":
        return home_goals > away_goals
    if selection == "away":
        return away_goals > home_goals
    return home_goals == away_goals


def proposition_board(session: Session) -> dict[str, object]:
    rows = session.scalars(select(TrackedProposition).order_by(TrackedProposition.created_at.desc())).all()
    learned = calibration(session)
    kickoffs = _kickoffs(session, {row.match_id for row in rows})
    items = []
    excluded = 0
    for row in rows:
        if row.status == "VOID":
            continue
        match = session.get(Match, row.match_id)
        learned_row = counts_for_learning(row.created_at, kickoffs.get(row.match_id))
        if row.status in {"WON", "LOST"} and not learned_row:
            excluded += 1
        items.append(
            {
                "id": row.id,
                "match_id": row.match_id,
                "selection": row.selection,
                "selection_label": row.selection_label,
                "strategy": row.strategy or "agent",
                "odds": row.odds,
                "raw_probability": row.raw_probability,
                "calibrated_probability": row.calibrated_probability,
                "confidence_score": row.confidence_score,
                "status": row.status,
                "home_goals": row.home_goals,
                "away_goals": row.away_goals,
                "match": _label(session, match) if match else "Donnée indisponible",
                "learned": learned_row,
            }
        )
    settled = [item for item in items if item["status"] in {"WON", "LOST"} and item["learned"]]
    hits = sum(1 for item in settled if item["status"] == "WON")
    return {
        "open": sum(1 for item in items if item["status"] == "OPEN"),
        "won": hits,
        "lost": len(settled) - hits,
        "hit_rate": None if not settled else hits / len(settled),
        "excluded": excluded,
        "calibration_weight": learned["weight"],
        "observed_hit_rate": learned["hit_rate"],
        "items": items[:40],
    }


def _label(session: Session, match: Match) -> str:
    from app.models import Team

    home = session.get(Team, match.home_team_id)
    away = session.get(Team, match.away_team_id)
    return f"{home.name if home else '?'} vs {away.name if away else '?'}"
