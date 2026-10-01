"""Public headlines and lineup facts. Missing sources stay empty."""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[3]
BRIEF_PATH = ROOT / "data" / "amelioration_brief.json"
HEADERS = {"User-Agent": "SportwiseAI/1.0"}
ESPN_NEWS = "https://site.api.espn.com/apis/site/v2/sports/soccer/{league}/news"
NEWS_LEAGUES = ("uefa.nations", "eng.1", "fra.1", "esp.1", "ger.1", "ita.1")
STANDINGS = "https://site.api.espn.com/apis/v2/sports/soccer/{league}/standings"
MEDIA_FEEDS = (
    ("BBC Sport", "https://feeds.bbci.co.uk/sport/football/rss.xml"),
    ("The Guardian", "https://www.theguardian.com/football/rss"),
)
REDDIT = "https://old.reddit.com/r/soccerbetting/new.json"


def lineup_notes(readings: list[dict]) -> dict[str, object]:
    examples: list[str] = []
    published = 0
    for reading in readings:
        for lineup in reading.get("lineups") or []:
            starters = [player for player in lineup.get("players") or [] if player.get("starter") and player.get("name")]
            if not starters:
                continue
            published += 1
            if len(examples) < 6:
                names = ", ".join(str(player["name"]) for player in starters[:11])
                examples.append(f"{lineup.get('team') or 'Équipe'} : {len(starters)} titulaires publiés ({names})")
    return {
        "published": published,
        "without_lineup": max(len(readings) - published, 0),
        "examples": examples,
        "note": "Une compo n'est citée que si le fournisseur l'a publiée. Aucune composition n'est inventée.",
    }


def strategy_note(report: list[dict]) -> str:
    settled = [row for row in report if int(row.get("settled") or 0) >= 8]
    if not settled:
        return "Aucune stratégie n'est préférée : moins de 8 paris ont été pris avant le coup d'envoi."
    best = max(settled, key=lambda row: (float(row.get("paper_profit") or 0), int(row["settled"])))
    return (
        f"Sur les résultats réels déjà connus, la lecture « {best['strategy']} » a le profit fictif le plus élevé "
        f"({best.get('paper_profit')}, {best['won']}/{best['settled']}). Ce n'est pas une garantie."
    )


def headlines_from_espn(payload: dict) -> list[dict[str, str]]:
    items = []
    for article in payload.get("articles") or []:
        title = article.get("headline")
        if not title:
            continue
        link = ((article.get("links") or {}).get("web") or {}).get("href")
        items.append({"source": "ESPN", "title": str(title), "url": str(link or "")})
    return items


def headlines_from_rss(xml_text: str, source: str) -> list[dict[str, str]]:
    root = ET.fromstring(xml_text)
    items = []
    for node in root.findall(".//item")[:4]:
        title = node.findtext("title")
        link = node.findtext("link")
        if title:
            items.append({"source": source, "title": title.strip(), "url": (link or "").strip()})
    return items


def social_from_reddit(payload: object) -> dict[str, object]:
    children = (((payload or {}).get("data") or {}).get("children") or []) if isinstance(payload, dict) else []
    posts = []
    for child in children:
        data = child.get("data") or {}
        title = data.get("title")
        if not title:
            continue
        posts.append({"source": "Reddit r/soccerbetting", "title": str(title), "url": "https://www.reddit.com" + str(data.get("permalink") or "")})
        if len(posts) >= 5:
            break
    if not posts:
        return {"status": "indisponible", "detail": "Aucun post public retenu.", "posts": []}
    return {"status": "ok", "detail": "Posts publics. Ce ne sont pas des faits de match.", "posts": posts}


def collect_public(client: httpx.Client | None = None) -> dict[str, object]:
    from app.analysis.empire import standings_rows

    own = client is None
    client = client or httpx.Client(timeout=20.0, follow_redirects=True, headers=HEADERS)
    media: list[dict[str, str]] = []
    standings: list[dict[str, str]] = []
    try:
        for league in NEWS_LEAGUES:
            response = client.get(ESPN_NEWS.format(league=league), params={"limit": 4})
            if response.status_code == 200:
                media.extend(headlines_from_espn(response.json())[:3])
            table = client.get(STANDINGS.format(league=league))
            if table.status_code == 200:
                standings.extend(standings_rows(table.json(), league))
        for source, url in MEDIA_FEEDS:
            feed = client.get(url)
            if feed.status_code == 200 and feed.text.lstrip().startswith("<"):
                media.extend(headlines_from_rss(feed.text, source)[:2])
        social_response = client.get(REDDIT, params={"limit": 5})
        body = social_response.text.lstrip()
        if social_response.status_code == 200 and body.startswith("{"):
            social = social_from_reddit(social_response.json())
        else:
            social = {"status": "indisponible", "detail": "Le réseau a refusé l'accès. Aucun message n'est inventé.", "posts": []}
    finally:
        if own:
            client.close()
    return {"media": media[:24], "social": social, "standings": standings}


def write_brief(
    readings: list[dict],
    report: list[dict],
    public: dict[str, object] | None = None,
    empire: dict[str, int] | None = None,
) -> dict[str, object]:
    public = public if public is not None else collect_public()
    brief = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "lineups": lineup_notes(readings),
        "strategy": strategy_note(report),
        "media": (public.get("media") or [])[:8],
        "social": public.get("social") or {"status": "indisponible", "detail": "Donnée indisponible", "posts": []},
        "empire": empire or {"added": 0, "headlines": 0, "results": 0, "standings": 0, "lineups": 0, "paper": 0, "total": 0},
        "note": "Les titres et les classements viennent des sources publiques. Ils ne modifient pas les probabilités déjà enregistrées.",
    }
    BRIEF_PATH.parent.mkdir(parents=True, exist_ok=True)
    BRIEF_PATH.write_text(json.dumps(brief, ensure_ascii=False), encoding="utf-8")
    return brief


def load_brief() -> dict[str, object] | None:
    if not BRIEF_PATH.exists():
        return None
    payload = json.loads(BRIEF_PATH.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else None
