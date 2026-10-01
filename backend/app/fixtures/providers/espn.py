"""ESPN public scoreboard. No API key. Competitions come from the provider catalog, not a fixed list."""

from __future__ import annotations

import math
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

import httpx

from app.fixtures.discovery import (
    age_category,
    competition_type,
    continent_for,
    parse_provider_datetime,
    season_label,
    tier_for,
)
from app.fixtures.http_client import RateLimiter, request_with_retry
from app.fixtures.providers.base import BaseFixtureProvider, NormalizedCompetition, NormalizedFixture
from app.fixtures.window import in_window, window_dates

LEAGUES_URL = "https://sports.core.api.espn.com/v2/sports/soccer/leagues"

STATUS_MAP = {
    "STATUS_SCHEDULED": "SCHEDULED",
    "STATUS_TIMED": "TIMED",
    "STATUS_IN_PROGRESS": "LIVE",
    "STATUS_HALFTIME": "LIVE",
    "STATUS_END_PERIOD": "LIVE",
    "STATUS_FULL_TIME": "FINISHED",
    "STATUS_FINAL": "FINISHED",
    "STATUS_FINAL_PEN": "FINISHED",
    "STATUS_FINAL_AET": "FINISHED",
    "STATUS_POSTPONED": "POSTPONED",
    "STATUS_CANCELED": "CANCELLED",
    "STATUS_CANCELLED": "CANCELLED",
    "STATUS_SUSPENDED": "SUSPENDED",
    "STATUS_DELAYED": "SUSPENDED",
}


class EspnFixtureProvider(BaseFixtureProvider):
    name = "espn"

    def __init__(self, client: httpx.Client | None = None, limiter: RateLimiter | None = None) -> None:
        self._client = client
        self.limiter = limiter or RateLimiter(0.15)

    def discover_competitions(self) -> list[NormalizedCompetition]:
        own = self._client is None
        client = self._client or httpx.Client(timeout=25.0, follow_redirects=True)
        found: list[NormalizedCompetition] = []
        try:
            for ref in self._league_refs(client):
                self.limiter.wait()
                response = request_with_retry(lambda ref=ref: client.get(ref))
                if response.status_code == 404:
                    continue
                response.raise_for_status()
                payload = response.json()
                if isinstance(payload, dict):
                    row = parse_league(payload)
                    if row is not None:
                        found.append(row)
        finally:
            if own:
                client.close()
        return found

    def get_upcoming_matches(
        self,
        start_date: datetime,
        end_date: datetime,
        competition: str | None = None,
        leagues: list[NormalizedCompetition] | None = None,
    ) -> list[NormalizedFixture]:
        selected = [row for row in (leagues or []) if _season_overlaps(row, start_date, end_date)]
        if competition:
            needle = competition.casefold()
            selected = [
                row
                for row in selected
                if needle in {row.provider_competition_id.casefold(), row.name.casefold(), row.normalized_name.casefold()}
            ]
        own = self._client is None
        client = self._client or httpx.Client(timeout=25.0, follow_redirects=True)
        found: dict[str, NormalizedFixture] = {}
        days = window_dates(start_date, end_date)
        try:
            jobs = [(row, day) for row in selected for day in days]
            workers = 1 if len(jobs) < 8 else 6
            with ThreadPoolExecutor(max_workers=workers) as pool:
                futures = [pool.submit(self._league_day, client, row, day) for row, day in jobs]
                for future in as_completed(futures):
                    for fixture in future.result():
                        if in_window(fixture.kickoff_utc, start_date, end_date):
                            found[fixture.provider_match_id] = fixture
        finally:
            if own:
                client.close()
        return list(found.values())

    def _league_refs(self, client: httpx.Client) -> list[str]:
        refs: list[str] = []
        page = 1
        while page <= 20:
            self.limiter.wait()
            response = request_with_retry(
                lambda page=page: client.get(LEAGUES_URL, params={"limit": 100, "page": page, "lang": "en"})
            )
            response.raise_for_status()
            payload = response.json()
            items = payload.get("items") or []
            refs.extend(str(item.get("$ref")) for item in items if item.get("$ref"))
            page_count = int(payload.get("pageCount") or 1)
            if page >= page_count or not items:
                break
            page += 1
        return refs

    def _league_day(self, client: httpx.Client, row: NormalizedCompetition, day: str) -> list[NormalizedFixture]:
        fixtures: list[NormalizedFixture] = []
        for page in range(1, 21):
            payload = self._page(client, row.provider_competition_id, day, page)
            events = payload.get("events") or []
            if not events:
                break
            for event in events:
                fixture = parse_event(event, row.name, row.country, row.season, row.provider_competition_id)
                if fixture is not None:
                    fixtures.append(fixture)
            if page >= int(payload.get("pageCount") or 1):
                break
        return fixtures

    def _page(self, client: httpx.Client, league: str, day: str, page: int) -> dict:
        self.limiter.wait()
        url = f"https://site.api.espn.com/apis/site/v2/sports/soccer/{league}/scoreboard"

        def send() -> httpx.Response:
            return client.get(url, params={"dates": day, "page": page, "limit": 100})

        response = request_with_retry(send)
        if response.status_code == 404:
            return {"events": []}
        response.raise_for_status()
        payload = response.json()
        return payload if isinstance(payload, dict) else {"events": []}


def _season_overlaps(row: NormalizedCompetition, start: datetime, end: datetime) -> bool:
    if row.season_start is None or row.season_end is None:
        return True
    season_start = row.season_start if row.season_start.tzinfo else row.season_start.replace(tzinfo=timezone.utc)
    season_end = row.season_end if row.season_end.tzinfo else row.season_end.replace(tzinfo=timezone.utc)
    return season_start <= end.astimezone(timezone.utc) and season_end >= start.astimezone(timezone.utc)


def parse_league(payload: dict) -> NormalizedCompetition | None:
    slug = str(payload.get("slug") or "")
    name = str(payload.get("displayName") or payload.get("name") or "")
    if not slug or not name:
        return None
    country = payload.get("country") or {}
    country_name = str(country.get("name") or "") if isinstance(country, dict) else ""
    country_slug = str(country.get("slug") or "") if isinstance(country, dict) else ""
    country_code = str(country.get("abbreviation") or "") if isinstance(country, dict) else ""
    season = payload.get("season") or {}
    start = parse_provider_datetime(season.get("startDate") if isinstance(season, dict) else None)
    end = parse_provider_datetime(season.get("endDate") if isinstance(season, dict) else None)
    year = season.get("year") if isinstance(season, dict) else None
    gender_raw = str(payload.get("gender") or "").upper()
    gender = "women" if gender_raw == "FEMALE" or ".w." in slug or slug.endswith(".w") else "men"
    return NormalizedCompetition(
        provider="espn",
        provider_competition_id=slug,
        name=name,
        normalized_name=" ".join(name.casefold().split()),
        country=country_name,
        country_code=country_code,
        continent=continent_for(country_slug, slug),
        gender=gender,
        age_category=age_category(slug),
        competition_type=competition_type(slug, name),
        tier=tier_for(slug),
        season=season_label(int(year) if year else None, start, end),
        season_start=start,
        season_end=end,
    )


def parse_event(event: dict, competition: str, country: str, season: str, code: str) -> NormalizedFixture | None:
    event_id = str(event.get("id") or "")
    if not event_id or not event.get("date"):
        return None
    kickoff = datetime.fromisoformat(str(event["date"]).replace("Z", "+00:00")).astimezone(timezone.utc)
    block = (event.get("competitions") or [{}])[0]
    home, away = _sides(block.get("competitors") or [])
    if home is None or away is None:
        return None
    status_name = ((block.get("status") or {}).get("type") or {}).get("name") or "STATUS_SCHEDULED"
    status = STATUS_MAP.get(str(status_name), "UNKNOWN")
    if status == "SCHEDULED" and block.get("timeValid") is True:
        status = "TIMED"
    venue = ((block.get("venue") or {}).get("fullName")) or None
    return NormalizedFixture(
        provider="espn",
        provider_match_id=event_id,
        competition_code=code,
        competition_name=competition,
        country=country,
        season=season,
        home_name=str(home["name"]),
        away_name=str(away["name"]),
        home_provider_id=str(home["id"]),
        away_provider_id=str(away["id"]),
        kickoff_utc=kickoff,
        status=status,
        home_goals=_score(home.get("score"), status),
        away_goals=_score(away.get("score"), status),
        venue=venue,
        round_name=str(event.get("season", {}).get("slug") or "") or None,
        matchday=_matchday(event),
        home_logo=home.get("logo"),
        away_logo=away.get("logo"),
        odds=extract_odds(block),
    )


def american_to_decimal(value: object) -> float | None:
    """Convert a provider American price to decimal. Returns None when the price is absent."""
    if value is None:
        return None
    text = str(value).strip().replace("+", "")
    if not text:
        return None
    try:
        moneyline = float(text)
    except ValueError:
        return None
    if not math.isfinite(moneyline) or moneyline == 0:
        return None
    decimal = 1.0 + moneyline / 100.0 if moneyline > 0 else 1.0 + 100.0 / abs(moneyline)
    if decimal <= 1.0:
        return None
    return round(decimal, 4)


def _american_node(node: object) -> float | None:
    if not isinstance(node, dict):
        return american_to_decimal(node)
    close = node.get("close") if isinstance(node.get("close"), dict) else None
    open_price = node.get("open") if isinstance(node.get("open"), dict) else None
    chosen = close or open_price or node
    if isinstance(chosen, dict):
        return american_to_decimal(chosen.get("odds") or chosen.get("moneyLine"))
    return None


def extract_odds(block: dict) -> list[dict[str, object]]:
    """Keep only prices present on the event. Missing markets are omitted."""
    quotes: list[dict[str, object]] = []
    for offer in block.get("odds") or []:
        if not isinstance(offer, dict):
            continue
        bookmaker = str(((offer.get("provider") or {}).get("name")) or "espn")
        moneyline = offer.get("moneyline") if isinstance(offer.get("moneyline"), dict) else {}
        for selection in ("home", "draw", "away"):
            price = _american_node(moneyline.get(selection))
            if price is None and selection == "draw":
                price = _american_node(offer.get("drawOdds"))
            if price is not None:
                quotes.append({"market": "1X2", "selection": selection, "price": price, "bookmaker": bookmaker})
        total = offer.get("total") if isinstance(offer.get("total"), dict) else {}
        line = offer.get("overUnder")
        try:
            line_value = float(line) if line is not None else None
        except (TypeError, ValueError):
            line_value = None
        if line_value in {0.5, 1.5, 2.5, 3.5}:
            label = str(line_value)
            over = _american_node(total.get("over"))
            under = _american_node(total.get("under"))
            if over is not None:
                quotes.append({"market": "over_under", "selection": f"over_{label}", "price": over, "bookmaker": bookmaker})
            if under is not None:
                quotes.append({"market": "over_under", "selection": f"under_{label}", "price": under, "bookmaker": bookmaker})
    return quotes


def team_goals(events: list[dict], team_id: str) -> tuple[list[float], list[float]]:
    scored: list[float] = []
    conceded: list[float] = []
    for event in events:
        if not isinstance(event, dict):
            continue
        try:
            home_score = float(event.get("homeTeamScore"))
            away_score = float(event.get("awayTeamScore"))
        except (TypeError, ValueError):
            continue
        if str(event.get("homeTeamId")) == team_id:
            scored.append(home_score)
            conceded.append(away_score)
        elif str(event.get("awayTeamId")) == team_id:
            scored.append(away_score)
            conceded.append(home_score)
    return scored, conceded


def parse_summary(payload: dict) -> dict[str, object]:
    """Keep only facts present in the ESPN summary. Missing lineups stay empty."""
    teams: list[dict[str, object]] = []
    for block in payload.get("lastFiveGames") or []:
        if not isinstance(block, dict):
            continue
        team = block.get("team") or {}
        team_id = str(team.get("id") or "")
        scored, conceded = team_goals(block.get("events") or [], team_id)
        results = []
        for event in block.get("events") or []:
            if not isinstance(event, dict) or event.get("score") in (None, ""):
                continue
            opponent = (event.get("opponent") or {}).get("displayName")
            results.append(
                {
                    "date": event.get("gameDate"),
                    "opponent": opponent,
                    "score": event.get("score"),
                    "result": event.get("gameResult"),
                    "competition": event.get("competitionName"),
                }
            )
        teams.append(
            {
                "id": team_id,
                "name": team.get("displayName"),
                "scored": scored,
                "conceded": conceded,
                "results": results,
            }
        )
    forms: dict[str, str] = {}
    header_comps = ((payload.get("header") or {}).get("competitions") or [])
    for competition in header_comps:
        for competitor in competition.get("competitors") or []:
            team = competitor.get("team") or {}
            if competitor.get("form") and team.get("id"):
                forms[str(team["id"])] = str(competitor["form"])
    for team in teams:
        team["form"] = forms.get(str(team["id"]))
    lineups: list[dict[str, object]] = []
    for roster in payload.get("rosters") or []:
        if not isinstance(roster, dict):
            continue
        players = roster.get("roster") or roster.get("players") or []
        names = []
        for player in players:
            if not isinstance(player, dict):
                continue
            athlete = player.get("athlete") or player
            name = athlete.get("displayName") or athlete.get("name")
            if name:
                names.append(
                    {
                        "name": name,
                        "position": ((player.get("position") or {}).get("abbreviation")) if isinstance(player.get("position"), dict) else None,
                        "starter": bool(player.get("starter")),
                    }
                )
        lineups.append({"team": ((roster.get("team") or {}).get("displayName")), "players": names})
    return {"teams": teams, "lineups": lineups}


def _sides(competitors: list[dict]) -> tuple[dict | None, dict | None]:
    home = away = None
    for item in competitors:
        team = item.get("team") or {}
        side = {
            "name": team.get("displayName") or team.get("name"),
            "id": team.get("id"),
            "logo": team.get("logo"),
            "score": item.get("score"),
        }
        if item.get("homeAway") == "home":
            home = side
        elif item.get("homeAway") == "away":
            away = side
    return home, away


def _score(value: object, status: str) -> int | None:
    if status not in {"FINISHED", "LIVE"} or value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _matchday(event: dict) -> int | None:
    week = (event.get("week") or {}).get("number")
    try:
        return int(week) if week is not None else None
    except (TypeError, ValueError):
        return None
