"""Recent-form reading from provider results, real odds, and published lineups only."""

from __future__ import annotations

from datetime import datetime, timezone

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.analysis.combinations import Leg, pack_disjoint, profile_for
from app.analysis.confidence import ConfidenceEngine, ConfidenceInputs
from app.analysis.recent_form import form_probabilities
from app.analysis.signals import SignalConfig, SignalEngine
from app.betting.odds_math import devig, expected_value, model_edge
from app.core.config import Settings, get_settings
from app.fixtures.providers.espn import parse_summary
from app.fixtures.service import upcoming_query
from app.fixtures.window import get_upcoming_window
from app.models import CombinationAnalysis, Competition, MarketAnalysis, Match, Odds, Team, TeamProviderLink

SELECTIONS = ("home", "draw", "away")


def analyze_recent_form(session: Session, settings: Settings | None = None, competition_code: str | None = None) -> dict[str, int]:
    settings = settings or get_settings()
    start, end = get_upcoming_window(days=14)
    matches = upcoming_query(session, start, end, None, None)
    if competition_code:
        code = competition_code.casefold()
        kept = []
        for match in matches:
            competition = session.get(Competition, match.competition_id)
            names = {
                (competition.code if competition else "").casefold(),
                (competition.provider_competition_id if competition and competition.provider_competition_id else "").casefold(),
                (competition.name if competition else "").casefold(),
            }
            if code in names:
                kept.append(match)
        matches = kept
    signal_engine = SignalEngine(
        SignalConfig(settings.min_edge, settings.min_ev, settings.min_confidence_score, settings.min_data_quality)
    )
    confidence_engine = ConfidenceEngine()
    created = datetime.now(timezone.utc)
    prudent_legs: list[Leg] = []
    value_legs: list[Leg] = []
    balanced_legs: list[Leg] = []
    stored = 0
    client = httpx.Client(timeout=25.0, follow_redirects=True)
    try:
        for match in matches:
            if not match.external_id or match.source != "espn":
                continue
            prices = _prices(session, match.id)
            if not prices and competition_code is None:
                continue
            context = _fetch_context(client, match, session)
            home = session.get(Team, match.home_team_id)
            away = session.get(Team, match.away_team_id)
            label = f"{home.name if home else '?'} vs {away.name if away else '?'}"
            probabilities = None
            sample = 0
            if context["home"] and context["away"]:
                probabilities = form_probabilities(
                    context["home"]["scored"],
                    context["home"]["conceded"],
                    context["away"]["scored"],
                    context["away"]["conceded"],
                )
                sample = min(len(context["home"]["scored"]), len(context["away"]["scored"]))
            market_probability = _market(prices)
            quality = min(1.0, sample / 15.0)
            sufficient = probabilities is not None and sample >= 3
            narrative = _narrative(label, context, probabilities, prices, sample, market_probability)
            if not probabilities:
                session.add(_gap(match, created, quality, sample, narrative, context))
                stored += 1
                continue
            match_legs: list[Leg] = []
            for selection in SELECTIONS:
                probability = float(probabilities[selection])
                odds = prices.get(selection)
                implied = market_probability.get(selection)
                edge = model_edge(probability, implied) if implied is not None else None
                ev = expected_value(probability, odds) if odds is not None else None
                scored = confidence_engine.score(
                    ConfidenceInputs(
                        data_quality=quality,
                        history_matches=sample,
                        calibration_score=None,
                        model_agreement=None,
                        prediction_stability=None,
                        odds_volatility=None,
                        information_completeness=1.0 if context["lineups_known"] else None,
                        market="1X2",
                        historical_market_performance=None,
                        edge=edge,
                        odds_present=odds is not None,
                    )
                )
                signal = signal_engine.classify(
                    odds=odds,
                    edge=edge,
                    expected_value=ev,
                    confidence_score=float(scored["confidence_score"]),
                    data_quality=quality,
                    sufficient_data=sufficient,
                )
                session.add(
                    MarketAnalysis(
                        match_id=match.id,
                        created_at=created,
                        model_version="recent-form-v1",
                        market="1X2",
                        selection=selection,
                        odds=odds,
                        model_probability=probability,
                        market_probability=implied,
                        edge=edge,
                        expected_value=ev,
                        confidence_score=float(scored["confidence_score"]),
                        confidence_level=str(scored["confidence_level"]),
                        signal=signal,
                        data_quality=quality,
                        sample_size=sample,
                        explanation=narrative,
                        sufficient_data=sufficient,
                    )
                )
                stored += 1
                if odds is not None and edge is not None:
                    match_legs.append(
                        Leg(
                            match_id=match.id,
                            match_label=label,
                            market="1X2",
                            selection=selection,
                            odds=odds,
                            model_probability=probability,
                            edge=edge,
                            expected_value=ev,
                            confidence_score=float(scored["confidence_score"]),
                            data_quality=quality,
                            signal=signal,
                        )
                    )
            usable = [leg for leg in match_legs if leg.odds >= 1.40]
            if usable:
                solid = [leg for leg in usable if leg.confidence_score >= 70 and leg.model_probability >= 0.55 and leg.odds <= 2.20]
                if solid:
                    prudent_legs.append(max(solid, key=lambda leg: leg.model_probability))
                interesting = [leg for leg in usable if leg.confidence_score >= 55 and leg.model_probability >= 0.52 and 1.45 <= leg.odds <= 2.40]
                if interesting:
                    balanced_legs.append(max(interesting, key=lambda leg: leg.model_probability))
                speculative = [
                    leg
                    for leg in usable
                    if leg.confidence_score >= 40
                    and leg.expected_value is not None
                    and leg.expected_value > 0
                    and leg.model_probability >= 0.50
                    and 1.50 <= leg.odds <= 2.60
                ]
                if speculative:
                    value_legs.append(max(speculative, key=lambda leg: leg.expected_value or 0))
    finally:
        client.close()
    combos = 0
    used_matches: set[int] = set()

    def _accept(rows: list[dict[str, object]], category: str) -> list[dict[str, object]]:
        kept = []
        for row in rows:
            if profile_for(
                confidence=float(row["confidence_score"]),
                expected_value=None if row["combined_ev"] is None else float(row["combined_ev"]),
                size=int(row["size"]),
            ) != category:
                continue
            if category == "VALUE" and (row["combined_odds"] is None or float(row["combined_odds"]) > 12):
                continue
            ids = {int(item["match_id"]) for item in row["selections"]}
            if ids & used_matches:
                continue
            used_matches.update(ids)
            kept.append(row)
        return kept

    grouped = {
        "PRUDENT": _accept(
            pack_disjoint(prudent_legs, size=3, min_size=2, count=1, rank_leg=lambda leg: -leg.model_probability),
            "PRUDENT",
        ),
        "BALANCED": _accept(
            pack_disjoint(balanced_legs, size=4, min_size=3, count=1, rank_leg=lambda leg: -leg.model_probability, exclude=used_matches),
            "BALANCED",
        ),
        "VALUE": _accept(
            pack_disjoint(
                value_legs,
                size=3,
                min_size=2,
                count=1,
                rank_leg=lambda leg: -(leg.expected_value or -9),
                exclude=used_matches,
                max_combined_odds=12,
            ),
            "VALUE",
        ),
    }
    for category, rows in grouped.items():
        for row in rows:
            session.add(
                CombinationAnalysis(
                    created_at=created,
                    category=category,
                    size=int(row["size"]),
                    combined_odds=row["combined_odds"],  # type: ignore[arg-type]
                    combined_probability=row["combined_probability"],  # type: ignore[arg-type]
                    combined_ev=row["combined_ev"],  # type: ignore[arg-type]
                    confidence_score=float(row["confidence_score"]),
                    correlation_risk=str(row["correlation_risk"]),
                    correlation_status=str(row["correlation_status"]),
                    combination_scope=str(row["combination_scope"]),
                    selections=row["selections"],  # type: ignore[arg-type]
                )
            )
            combos += 1
    session.commit()
    return {"matches": len(matches), "analyses": stored, "combinations": combos}


def _fetch_context(client: httpx.Client, match: Match, session: Session) -> dict[str, object]:
    home_ids = _provider_team_ids(session, match.home_team_id)
    away_ids = _provider_team_ids(session, match.away_team_id)
    home_name = (session.get(Team, match.home_team_id).name if session.get(Team, match.home_team_id) else "").casefold()
    away_name = (session.get(Team, match.away_team_id).name if session.get(Team, match.away_team_id) else "").casefold()
    competition = session.get(Competition, match.competition_id)
    slug = (competition.provider_competition_id if competition else None) or "uefa.nations"
    response = client.get(
        f"https://site.api.espn.com/apis/site/v2/sports/soccer/{slug}/summary",
        params={"event": match.external_id},
    )
    parsed = {"teams": [], "lineups": []}
    if response.status_code == 200:
        body = response.json()
        if isinstance(body, dict):
            parsed = parse_summary(body)
    def pick(ids: set[str], name: str) -> dict | None:
        for team in parsed["teams"]:
            if str(team.get("id")) in ids or str(team.get("name") or "").casefold() == name:
                return team
        return None

    lineups = [item for item in parsed["lineups"] if item.get("players")]
    return {
        "home": pick(home_ids, home_name),
        "away": pick(away_ids, away_name),
        "lineups": lineups,
        "lineups_known": bool(lineups),
    }


def _provider_team_ids(session: Session, team_id: int) -> set[str]:
    links = session.scalars(
        select(TeamProviderLink).where(TeamProviderLink.team_id == team_id, TeamProviderLink.provider == "espn")
    ).all()
    return {link.provider_team_id for link in links}


def _prices(session: Session, match_id: int) -> dict[str, float]:
    rows = session.scalars(
        select(Odds).where(Odds.match_id == match_id, Odds.market == "1X2", Odds.price.is_not(None)).order_by(Odds.captured_at.asc())
    ).all()
    prices: dict[str, float] = {}
    for row in rows:
        if row.price and row.price > 1 and row.selection in SELECTIONS:
            prices[row.selection] = float(row.price)
    return prices


def _market(prices: dict[str, float]) -> dict[str, float]:
    if not all(selection in prices for selection in SELECTIONS):
        return {}
    return devig({selection: prices[selection] for selection in SELECTIONS})


def _narrative(
    label: str,
    context: dict[str, object],
    probabilities: dict[str, float] | None,
    prices: dict[str, float],
    sample: int,
    market_probability: dict[str, float],
) -> dict[str, object]:
    home = context.get("home") or {}
    away = context.get("away") or {}
    lines = [f"{label}."]
    favorable: list[str] = []
    risks = ["échantillon récent court : environ cinq matchs, confiance limitée"]
    for side, title in ((home, "Domicile"), (away, "Extérieur")):
        if not side:
            lines.append(f"{title} : données de forme indisponibles.")
            risks.append(f"forme {title.lower()} indisponible")
            continue
        form = side.get("form") or "".join(str(item.get("result") or "")[:1] for item in (side.get("results") or [])[:5]) or "donnée indisponible"
        lines.append(
            f"{title} {side.get('name')} : forme {form}. "
            f"Sur {len(side.get('scored') or [])} matchs renseignés, "
            f"buts marqués {_mean(side.get('scored') or [])}, encaissés {_mean(side.get('conceded') or [])}."
        )
        for result in (side.get("results") or [])[:5]:
            lines.append(
                f"{side.get('name')} : {result.get('result') or '—'} {result.get('score')} "
                f"contre {result.get('opponent') or 'adversaire inconnu'}"
                + (f" ({result.get('competition')})" if result.get("competition") else "")
                + "."
            )
    if prices:
        lines.append(
            "Cotes réelles 1X2 : "
            + ", ".join(f"{selection} {prices[selection]:.2f}" for selection in SELECTIONS if selection in prices)
            + "."
        )
    else:
        lines.append("Cotes indisponibles.")
        risks.append("cote absente")
    if probabilities:
        lines.append(
            "Modèle de forme récente : "
            f"domicile {probabilities['home'] * 100:.1f} %, "
            f"nul {probabilities['draw'] * 100:.1f} %, "
            f"extérieur {probabilities['away'] * 100:.1f} %. "
            f"Échantillon {sample} matchs. Ce n'est pas une probabilité de gain."
        )
        for selection, french in (("home", "domicile"), ("draw", "nul"), ("away", "extérieur")):
            implied = market_probability.get(selection)
            if implied is None:
                continue
            gap = probabilities[selection] - implied
            sentence = (
                f"Écart modèle/marché sur {french} : {gap * 100:+.1f} points "
                f"(modèle {probabilities[selection] * 100:.1f} %, marché {implied * 100:.1f} %)."
            )
            lines.append(sentence)
            if abs(gap) >= 0.12:
                risks.append("Écart supérieur à 12 points : l'échantillon court ne suffit pas pour suivre ce chiffre.")
            elif gap >= 0.04:
                favorable.append(sentence)
            elif gap <= -0.04:
                risks.append(sentence)
    else:
        lines.append("Probabilité non calculée : historique récent insuffisant.")
    if context.get("lineups_known"):
        lines.append("Composition publiée par le fournisseur.")
        favorable.append("composition publiée")
    else:
        lines.append("Composition non publiée par le fournisseur.")
        risks.append("composition non publiée")
    return {
        "narrative": lines,
        "results": {"home": (home or {}).get("results") or [], "away": (away or {}).get("results") or []},
        "lineups": context.get("lineups") or [],
        "favorable": favorable,
        "risks": risks,
    }


def _mean(values: list[float]) -> str:
    if not values:
        return "donnée indisponible"
    return f"{sum(values) / len(values):.2f}"


def _gap(match: Match, created: datetime, quality: float, sample: int, narrative: dict[str, object], context: dict[str, object]) -> MarketAnalysis:
    return MarketAnalysis(
        match_id=match.id,
        created_at=created,
        model_version="recent-form-v1",
        market="1X2",
        selection="none",
        confidence_score=0.0,
        confidence_level="VERY_LOW",
        signal="INSUFFICIENT_DATA",
        data_quality=quality,
        sample_size=sample,
        explanation=narrative,
        sufficient_data=False,
    )
