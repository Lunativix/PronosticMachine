"""Append an odds snapshot and refresh the value signal. History is never overwritten."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.base import utcnow
from app.models import Bookmaker, Match, Odds


def apply_odds_update(
    session: Session,
    *,
    match_id: int,
    bookmaker_code: str,
    market: str,
    selection: str,
    price: float | None,
    captured_at: datetime,
    action: str = "upsert",
    source: str = "live",
) -> Odds:
    match = session.get(Match, match_id)
    if match is None:
        raise ValueError("Unknown match.")
    if action not in {"upsert", "remove"}:
        raise ValueError("Action must be upsert or remove.")
    if action == "upsert" and (price is None or price <= 1):
        raise ValueError("A new price must be greater than 1.")
    bookmaker = session.scalar(select(Bookmaker).where(Bookmaker.code == bookmaker_code))
    if bookmaker is None:
        bookmaker = Bookmaker(code=bookmaker_code, name=bookmaker_code)
        session.add(bookmaker)
        session.flush()
    status = "removed" if action == "remove" else "active"
    existing = session.scalar(
        select(Odds).where(
            Odds.match_id == match_id,
            Odds.bookmaker_id == bookmaker.id,
            Odds.market == market,
            Odds.selection == selection,
            Odds.captured_at == captured_at,
            Odds.status == status,
        )
    )
    if existing is not None:
        return existing
    row = Odds(
        match_id=match_id,
        bookmaker_id=bookmaker.id,
        market=market,
        selection=selection,
        price=price,
        captured_at=captured_at,
        status=status,
        source=source,
        quality="valid",
        imported_at=utcnow(),
    )
    session.add(row)
    session.commit()
    return row
