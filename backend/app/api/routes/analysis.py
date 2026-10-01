"""Bet analyzer endpoints. Probabilities and confidence are reported separately."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.analysis.confidence import LEVEL_LABELS
from app.analysis.performance import combination_performance, selection_performance
from app.analysis.combinations import stance_label
from app.analysis.agent import build_pronostics
from app.analysis.briefing import load_brief
from app.analysis.tracking import proposition_board, sync_propositions
from app.analysis.service import analyze_upcoming_matches, latest_probability_snapshot, latest_snapshot
from app.analysis.signals import SIGNAL_LABELS
from app.core.config import get_settings
from app.db.session import get_db
from app.fixtures.service import upcoming_query
from app.fixtures.window import get_upcoming_window
from app.models import CombinationAnalysis, Competition, MarketAnalysis, Match, Odds, Team

router = APIRouter()
DISCLAIMER = (
    "Probabilité modèle et confiance du signal sont deux informations distinctes. "
    "Aucune sélection n'est un pari sûr, un gain garanti ou un résultat infaillible."
)


@router.get("/analysis/propositions")
def propositions(db: Session = Depends(get_db)) -> dict:
    stamp = latest_snapshot(db)
    reading_stamp = latest_probability_snapshot(db)
    rows = []
    if stamp is not None:
        rows = db.scalars(select(MarketAnalysis).where(MarketAnalysis.created_at == stamp)).all()
    reading_rows = rows
    if reading_stamp is not None and reading_stamp != stamp:
        reading_rows = db.scalars(select(MarketAnalysis).where(MarketAnalysis.created_at == reading_stamp)).all()
    signals = [row for row in rows if row.signal not in {"NO_SIGNAL", "INSUFFICIENT_DATA"} and row.model_probability is not None]
    strong = [row for row in signals if row.signal == "STRONG_SIGNAL"]
    analyzed_ids = {row.match_id for row in rows}
    edges = [row.edge for row in signals if row.edge is not None]
    evs = [row.expected_value for row in signals if row.expected_value is not None]
    confidences = [row.confidence_score for row in signals]
    combo_stamp = reading_stamp or stamp
    combos = {"PRUDENT": [], "BALANCED": [], "VALUE": []}
    if combo_stamp is not None:
        for row in db.scalars(select(CombinationAnalysis).where(CombinationAnalysis.created_at == combo_stamp)).all():
            combos.setdefault(row.category, []).append(_combo_payload(row))
    start, end = get_upcoming_window(days=14)
    upcoming = upcoming_query(db, start, end, None, None)
    upcoming_ids = [match.id for match in upcoming]
    with_odds = 0
    if upcoming_ids:
        with_odds = int(
            db.scalar(select(func.count(func.distinct(Odds.match_id))).where(Odds.match_id.in_(upcoming_ids), Odds.price.is_not(None)))
            or 0
        )
    missing = []
    if with_odds == 0:
        missing.append("cotes")
    if rows and not signals and any(row.signal == "INSUFFICIENT_DATA" for row in rows):
        missing.append("historique_equipes")
    return {
        "disclaimer": DISCLAIMER,
        "generated_at": None if stamp is None else stamp.isoformat(),
        "analyzed_matches": len(analyzed_ids),
        "signals": len({row.match_id for row in signals}),
        "strong_signals": len({row.match_id for row in strong}),
        "mean_confidence": None if not confidences else round(sum(confidences) / len(confidences), 1),
        "mean_edge": None if not edges else round(sum(edges) / len(edges), 4),
        "mean_ev": None if not evs else round(sum(evs) / len(evs), 4),
        "upcoming_matches": len(upcoming),
        "matches_with_odds": with_odds,
        "missing": missing,
        "items": [_selection_payload(row) | _match_bits(db, row.match_id) for row in signals],
        "combinations": combos,
        "readings": (study := _readings(db, reading_rows)),
        "pronostics": build_pronostics(study),
        "tracked": {**proposition_board(db), **sync_propositions(db, study), **proposition_board(db)},
        "brief": load_brief(),
    }


@router.get("/analysis/matches/{match_id}")
def match_analysis(match_id: int, db: Session = Depends(get_db)) -> dict:
    match = db.get(Match, match_id)
    if match is None:
        raise HTTPException(404, "Match introuvable")
    stamp = latest_probability_snapshot(db) or latest_snapshot(db)
    rows = []
    if stamp is not None:
        rows = db.scalars(
            select(MarketAnalysis).where(
                MarketAnalysis.match_id == match_id,
                MarketAnalysis.created_at == select(func.max(MarketAnalysis.created_at)).where(MarketAnalysis.match_id == match_id).scalar_subquery(),
            )
        ).all()
        if rows and all(row.model_probability is None for row in rows):
            richer = db.scalars(
                select(MarketAnalysis).where(MarketAnalysis.created_at == stamp, MarketAnalysis.match_id == match_id)
            ).all()
            if richer:
                rows = richer
    return {"disclaimer": DISCLAIMER, **_match_payload(db, match), "markets": [_selection_payload(row) for row in rows]}


@router.get("/analysis/upcoming")
def upcoming_analysis(db: Session = Depends(get_db)) -> dict:
    stamp = latest_snapshot(db)
    rows = []
    if stamp is not None:
        rows = db.scalars(select(MarketAnalysis).where(MarketAnalysis.created_at == stamp)).all()
    grouped: dict[int, dict] = {}
    for row in rows:
        match = db.get(Match, row.match_id)
        if match is None:
            continue
        bucket = grouped.setdefault(match.id, _match_payload(db, match))
        bucket["markets"].append(_selection_payload(row))
    return {"disclaimer": DISCLAIMER, "generated_at": None if stamp is None else stamp.isoformat(), "matches": list(grouped.values())}


@router.get("/analysis/combinations")
def combinations(db: Session = Depends(get_db)) -> dict:
    stamp = latest_snapshot(db)
    payload = {"PRUDENT": [], "VALUE": [], "BALANCED": []}
    if stamp is None:
        return {"disclaimer": DISCLAIMER, "categories": payload}
    rows = db.scalars(select(CombinationAnalysis).where(CombinationAnalysis.created_at == stamp)).all()
    for row in rows:
        payload.setdefault(row.category, []).append(
            {
                "id": row.id,
                "category": row.category,
                "selections": row.selections,
                "combined_odds": row.combined_odds,
                "combined_probability": row.combined_probability,
                "combined_ev": row.combined_ev,
                "confidence_score": row.confidence_score,
                "correlation_risk": row.correlation_risk,
                "correlation_status": row.correlation_status,
                "combination_scope": row.combination_scope,
                "size": row.size,
            }
        )
    return {"disclaimer": DISCLAIMER, "categories": payload}


@router.get("/analysis/performance")
def performance(db: Session = Depends(get_db)) -> dict:
    return {
        "disclaimer": DISCLAIMER,
        "selections": selection_performance(db),
        "combinations": combination_performance(db),
    }


@router.get("/config/thresholds")
def thresholds() -> dict:
    settings = get_settings()
    return {
        "min_edge": settings.min_edge,
        "min_ev": settings.min_ev,
        "min_model_confidence": settings.min_model_confidence,
        "min_confidence_score": settings.min_confidence_score,
        "min_data_quality": settings.min_data_quality,
        "max_combination_size": settings.max_combination_size,
        "odds_provider_configured": bool(settings.odds_api_key),
        "fixture_provider": settings.fixture_provider,
    }


@router.post("/analysis/run")
def run_analysis(db: Session = Depends(get_db)) -> dict:
    return analyze_upcoming_matches(db)


def _match_payload(db: Session, match: Match) -> dict:
    home = db.get(Team, match.home_team_id)
    away = db.get(Team, match.away_team_id)
    competition = db.get(Competition, match.competition_id)
    return {
        "match_id": match.id,
        "match": f"{home.name if home else '?'} vs {away.name if away else '?'}",
        "home_team": home.name if home else "Donnée indisponible",
        "away_team": away.name if away else "Donnée indisponible",
        "date": match.kickoff_at.isoformat(),
        "kickoff_local": match.scheduled_at_local,
        "competition": competition.name if competition else "Donnée indisponible",
        "country": competition.country if competition and competition.country else "Donnée indisponible",
        "venue": match.venue or "Donnée indisponible",
        "status": match.status,
        "model_agreement": None,
        "markets": [],
    }


def _readings(db: Session, rows: list[MarketAnalysis]) -> list[dict]:
    grouped: dict[int, dict] = {}
    for row in rows:
        if row.model_probability is None:
            continue
        bucket = grouped.setdefault(row.match_id, {**_match_bits(db, row.match_id), "markets": [], "narrative": []})
        bucket["markets"].append(_selection_payload(row))
        if not bucket["narrative"]:
            bucket["narrative"] = (row.explanation or {}).get("narrative") or []
            bucket["lineups"] = (row.explanation or {}).get("lineups") or []
    return list(grouped.values())


def _match_bits(db: Session, match_id: int) -> dict:
    match = db.get(Match, match_id)
    if match is None:
        return {}
    payload = _match_payload(db, match)
    payload.pop("markets", None)
    return payload


CORRELATION_LABELS = {"LOW": "FAIBLE", "MEDIUM": "MOYENNE", "HIGH": "ÉLEVÉE", "UNKNOWN": "INCONNUE"}


def _combo_payload(row: CombinationAnalysis) -> dict:
    return {
        "id": row.id,
        "category": row.category,
        "selections": row.selections,
        "combined_odds": row.combined_odds,
        "combined_probability": row.combined_probability,
        "combined_ev": row.combined_ev,
        "confidence_score": row.confidence_score,
        "stance": stance_label(float(row.confidence_score)),
        "correlation_risk": row.correlation_risk,
        "correlation_label": CORRELATION_LABELS.get(row.correlation_risk, "INCONNUE"),
        "correlation_status": row.correlation_status,
        "combination_scope": row.combination_scope,
        "size": row.size,
    }


def _selection_payload(row: MarketAnalysis) -> dict:
    return {
        "id": row.id,
        "market": row.market,
        "selection": row.selection,
        "odds": row.odds,
        "model_probability": row.model_probability,
        "market_probability": row.market_probability,
        "edge": row.edge,
        "ev": row.expected_value,
        "confidence_score": row.confidence_score,
        "confidence_level": row.confidence_level,
        "confidence_label": LEVEL_LABELS.get(row.confidence_level, row.confidence_level),
        "signal": row.signal,
        "signal_label": SIGNAL_LABELS.get(row.signal, row.signal),
        "data_quality": row.data_quality,
        "sample_size": row.sample_size,
        "favorable": (row.explanation or {}).get("favorable", []),
        "risks": (row.explanation or {}).get("risks", []),
        "narrative": (row.explanation or {}).get("narrative", []),
        "lineups": (row.explanation or {}).get("lineups", []),
        "results": (row.explanation or {}).get("results", {}),
    }
