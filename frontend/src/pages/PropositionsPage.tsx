import { useEffect, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { CombinationCard, MetricCard, OddsDisplay, ProbabilityDisplay, SignalCard } from "../components/metrics";
import { confidence, outcomeLabel, signedPercent, teamsFromMatch } from "../format";
import { Empty } from "../components/ui";
import { useSlip } from "../slip";

type SignalItem = {
  id: number;
  match_id: number;
  match: string;
  competition: string;
  date: string;
  kickoff_local: string | null;
  market: string;
  selection: string;
  odds: number | null;
  model_probability: number | null;
  market_probability: number | null;
  edge: number | null;
  ev: number | null;
  confidence_score: number;
  data_quality: number;
  signal_label: string;
  model_agreement?: number | null;
};

type Combo = {
  id: number;
  selections: { match: string; market: string; selection: string; odds: number | null }[];
  combined_odds: number | null;
  combined_probability: number | null;
  combined_ev: number | null;
  confidence_score: number;
  correlation_label: string;
  stance?: string;
  size: number;
};

type Payload = {
  analyzed_matches: number;
  signals: number;
  strong_signals: number;
  mean_confidence: number | null;
  mean_edge: number | null;
  mean_ev: number | null;
  upcoming_matches: number;
  matches_with_odds: number;
  missing: string[];
  generated_at: string | null;
  items: SignalItem[];
  combinations: Record<string, Combo[]>;
  pronostics?: Pronostic[];
  tracked?: {
    open: number;
    won: number;
    lost: number;
    hit_rate: number | null;
    excluded?: number;
    calibration_weight: number;
    created?: number;
    settled?: number;
    items: { id: number; match_id: number; match: string; selection_label: string; strategy?: string; odds: number | null; raw_probability: number; calibrated_probability: number; status: string; home_goals: number | null; away_goals: number | null }[];
  };
  brief?: {
    strategy: string;
    note: string;
    lineups: { published: number; without_lineup: number; examples: string[]; note: string };
    media: { source: string; title: string; url: string }[];
    social: { status: string; detail: string; posts: { source: string; title: string; url: string }[] };
    empire?: { total: number; added: number; headlines: number; results: number; standings: number; lineups: number; paper: number };
  };
  readings?: {
    match_id: number;
    match: string;
    home_team?: string;
    away_team?: string;
    competition: string;
    narrative: string[];
    date?: string;
    kickoff_local?: string | null;
    markets: { selection: string; odds: number | null; model_probability: number | null; market_probability?: number | null; edge: number | null; ev: number | null; confidence_score: number; data_quality?: number; signal_label: string }[];
  }[];
};

type Pronostic = {
  match_id: number;
  match: string;
  competition: string;
  date?: string;
  kickoff_local?: string | null;
  selection_label: string;
  odds: number | null;
  model_probability: number | null;
  market_probability?: number | null;
  edge: number | null;
  ev: number | null;
  confidence_score: number | null;
  data_quality?: number | null;
  reason: string;
};

const PROFILES = [
  ["PRUDENT", "COMBINÉ PRUDENT"],
  ["BALANCED", "COMBINÉ ÉQUILIBRÉ"],
  ["VALUE", "COMBINÉ VALUE"],
] as const;

export function PropositionsPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const slip = useSlip();
  const [showAllReadings, setShowAllReadings] = useState(false);
  const [payload, setPayload] = useState<Payload | null>(null);
  const [sync, setSync] = useState<string | null>(null);
  const [error, setError] = useState("");

  function load() {
    fetch("/analysis/propositions")
      .then(async (response) => {
        if (!response.ok) throw new Error(await response.text());
        return response.json();
      })
      .then(setPayload)
      .catch((reason: Error) => setError(reason.message));
    fetch("/fixtures/sync/status").then((response) => response.json()).then((body) => setSync(body.last_sync?.finished_at ?? body.last_sync?.last_sync ?? null)).catch(() => setSync(null));
  }

  useEffect(() => { load(); }, []);
  useEffect(() => {
    const id = location.pathname === "/signals" ? "signaux" : location.pathname === "/combinations" ? "combines" : "";
    if (id) document.getElementById(id)?.scrollIntoView({ behavior: "smooth" });
  }, [location.pathname, payload]);

  if (error) return <Empty text="Les propositions n'ont pas pu être chargées." />;
  if (!payload) return <p className="text-slate-300">Chargement…</p>;
  const missingOdds = payload.missing.includes("cotes");
  const missingHistory = payload.missing.includes("historique_equipes");

  return (
    <section className="space-y-8">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="text-sm uppercase tracking-wide text-amber-300">SPORTWISE AI</p>
          <h1 className="text-4xl font-semibold text-white">Propositions du jour</h1>
          <p className="text-slate-300">{new Date().toLocaleDateString("fr-FR", { dateStyle: "full" })}</p>
          <p className="text-sm text-slate-400">Dernière synchronisation : {sync ? new Date(sync).toLocaleString("fr-FR") : "—"}</p>
        </div>
        <button className="rounded-lg bg-white px-4 py-2 text-sm font-semibold text-ink" type="button" onClick={() => fetch("/analysis/run", { method: "POST" }).then(load)}>
          Actualiser
        </button>
      </header>
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        <MetricCard label="Matchs analysés" value={payload.analyzed_matches} />
        <MetricCard label="Signaux" value={payload.signals} />
        <MetricCard label="Signaux forts" value={payload.strong_signals} />
        <MetricCard label="Confiance moyenne" value={confidence(payload.mean_confidence)} />
        <MetricCard label="Edge moyen" value={signedPercent(payload.mean_edge)} />
        <MetricCard label="EV moyen" value={signedPercent(payload.mean_ev)} />
      </div>
      {payload.brief && (
        <section>
          <h2 className="text-2xl text-white">Veille</h2>
          {payload.brief.empire && (
            <p className="mt-1 text-sm text-white">{payload.brief.empire.total} faits conservés · {payload.brief.empire.results} scores · {payload.brief.empire.headlines} articles · {payload.brief.empire.standings} lignes de classement · {payload.brief.empire.lineups} compos · {payload.brief.empire.paper} paris fictifs réglés</p>
          )}
          <p className="mt-1 text-sm text-slate-300">{payload.brief.strategy}</p>
          <p className="mt-1 text-sm text-slate-400">{payload.brief.lineups.note} {payload.brief.lineups.published} compos publiées, {payload.brief.lineups.without_lineup} lectures sans compo.</p>
          <ul className="mt-2 space-y-1 text-sm text-slate-200">
            {payload.brief.lineups.examples.map((line) => <li key={line}>{line}</li>)}
          </ul>
          <ul className="mt-3 space-y-1 text-sm">
            {payload.brief.media.map((item) => (
              <li key={item.url || item.title}><span className="text-slate-400">{item.source} · </span>{item.url ? <a className="text-white underline" href={item.url} target="_blank" rel="noreferrer">{item.title}</a> : item.title}</li>
            ))}
            {payload.brief.social.posts.map((item) => (
              <li key={item.url || item.title}><span className="text-slate-400">{item.source} · </span><a className="text-white underline" href={item.url} target="_blank" rel="noreferrer">{item.title}</a></li>
            ))}
          </ul>
          {payload.brief.social.status !== "ok" && <p className="mt-2 text-sm text-slate-400">Réseaux de paris : {payload.brief.social.detail}</p>}
          <p className="mt-2 text-xs text-slate-500">{payload.brief.note}</p>
        </section>
      )}
      <section>
        <h2 className="text-2xl text-white">Pronostics de l'agent</h2>
        <p className="mt-1 text-sm text-slate-400">L'agent retient l'issue la plus probable du modèle de forme quand une cote réelle existe. Il n'invente ni cote ni probabilité.</p>
        {(payload.pronostics ?? []).length === 0 && <div className="mt-3"><Empty text="L'agent n'a aucun pronostic : il manque une cote réelle ou une probabilité calculée." /></div>}
        <div className="mt-4 grid gap-4 xl:grid-cols-2">
          {(payload.pronostics ?? []).map((pick) => (
            <div key={pick.match_id}>
              <SignalCard
                title={pick.selection_label}
                competition={`${pick.match} · ${pick.competition}`}
                when={(pick.kickoff_local || pick.date || "").replace("T", " ").slice(0, 16)}
                probabilityValue={pick.model_probability}
                oddsValue={pick.odds}
                marketProbability={pick.market_probability ?? null}
                edge={pick.edge}
                ev={pick.ev}
                confidenceValue={pick.confidence_score}
                qualityValue={pick.data_quality ?? null}
                agreement={null}
                signalLabel="Pronostic agent"
                onOpen={() => navigate(`/matches/${pick.match_id}`)}
                added={slip.has(pick.match_id, pick.selection_label)}
                onAdd={() => slip.add({ matchId: pick.match_id, match: pick.match, selection: pick.selection_label, odds: pick.odds, probability: pick.model_probability })}
              />
              <p className="mt-2 text-sm text-slate-400">{pick.reason}</p>
            </div>
          ))}
        </div>
      </section>
      <section>
        <h2 className="text-2xl text-white">Propositions suivies</h2>
        <p className="mt-1 text-sm text-slate-300">
          {payload.tracked ? `${payload.tracked.open} en cours · ${payload.tracked.won} gagnées · ${payload.tracked.lost} perdues` : "Aucune proposition enregistrée."}
          {payload.tracked?.hit_rate != null ? ` · réussite ${signedPercent(payload.tracked.hit_rate).replace("+", "")}` : " · aucun pari d'avant-match réglé pour l'instant"}
          {payload.tracked?.excluded ? ` · ${payload.tracked.excluded} paris pris après le coup d'envoi, exclus` : ""}
        </p>
        <p className="mt-1 text-sm text-slate-400">Seuls les paris enregistrés avant le coup d'envoi font apprendre. Moins de 8 résultats dans une même lecture ne changent pas la probabilité. Les probabilités déjà enregistrées ne sont pas réécrites.</p>
        <div className="mt-4 grid gap-3 md:grid-cols-2">
          {(payload.tracked?.items ?? []).slice(0, 12).map((item) => (
            <article key={item.id} className="rounded-2xl border border-white/15 bg-panel p-4">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <p className="text-xs text-slate-400">{item.match}</p>
                  <p className="text-2xl font-semibold text-white">{item.selection_label}</p>
                  {item.strategy && <p className="text-xs text-slate-400">Lecture {item.strategy}</p>}
                </div>
                <p className="rounded-full bg-white px-3 py-1 text-sm font-semibold text-ink">{item.status === "WON" ? "Gagnée" : item.status === "LOST" ? "Perdue" : "En cours"}</p>
              </div>
              <p className="mt-2 text-sm text-slate-200">Cote <OddsDisplay value={item.odds} /> · brute <ProbabilityDisplay value={item.raw_probability} /> · calibrée <ProbabilityDisplay value={item.calibrated_probability} /></p>
              {item.home_goals != null && <p className="text-sm text-slate-400">Score {item.home_goals}-{item.away_goals}</p>}
            </article>
          ))}
        </div>
      </section>
      <section id="signaux">
        <h2 className="text-2xl text-white">Signaux principaux</h2>
        {payload.items.length === 0 && (
          <div className="mt-3">
            <Empty text="Aucune proposition actuellement. Le moteur n'a identifié aucun signal répondant aux critères configurés." />
            {missingOdds && <p className="mt-2 text-sm text-amber-200">Cotes indisponibles. Aucun prix réel n'est encore stocké pour les matchs de la fenêtre.</p>}
            {missingHistory && <p className="mt-2 text-sm text-amber-200">Données insuffisantes. Les équipes de ces matchs ne sont pas couvertes par l'historique du modèle.</p>}
          </div>
        )}
        <div className="mt-4 grid gap-4 xl:grid-cols-2">
          {payload.items.map((item) => (
            <SignalCard
              key={item.id}
              title={`${item.match} — ${outcomeLabel(item.selection, teamsFromMatch(item.match).home, teamsFromMatch(item.match).away)}`}
              competition={item.competition}
              when={(item.kickoff_local || item.date).replace("T", " ").slice(0, 16)}
              probabilityValue={item.model_probability}
              oddsValue={item.odds}
              marketProbability={item.market_probability}
              edge={item.edge}
              ev={item.ev}
              confidenceValue={item.confidence_score}
              qualityValue={item.data_quality}
              agreement={item.model_agreement ?? null}
              signalLabel={item.signal_label}
              onOpen={() => navigate(`/matches/${item.match_id}`)}
            />
          ))}
        </div>
      </section>
      <section id="combines" className="space-y-4">
        <h2 className="text-2xl text-white">Combinés suggérés</h2>
        <div className="mt-4 grid gap-4 lg:grid-cols-3">
          {PROFILES.map(([key, title]) => {
            const rows = payload.combinations[key] ?? [];
            if (rows.length === 0) {
              const reason = key === "PRUDENT"
                ? "Aucun combiné prudent : aucune sélection n'atteint 70/100 de confiance."
                : key === "BALANCED"
                  ? "Aucun combiné équilibré. Un EV élevé avec une confiance sous 55/100 n'est pas présenté comme équilibré."
                  : "Aucun combiné value : pas assez de sélections à EV positif avec une probabilité d'au moins 50 %.";
              return <article key={key} className="rounded-2xl border border-dashed border-white/30 p-4 text-slate-200">{reason}</article>;
            }
            return rows.map((combo) => (
              <CombinationCard
                key={combo.id}
                title={title}
                legs={combo.selections.map((leg) => {
                  const teams = teamsFromMatch(leg.match);
                  return { label: `${leg.match} — ${outcomeLabel(leg.selection, teams.home, teams.away)}`, odds: leg.odds };
                })}
                combinedOdds={combo.combined_odds}
                probabilityValue={combo.combined_probability}
                ev={combo.combined_ev}
                confidenceValue={combo.confidence_score}
                correlation={combo.correlation_label}
                stance={combo.stance}
              />
            ));
          })}
        </div>
      </section>
      <section>
        <h2 className="text-2xl text-white">Lectures de forme</h2>
        <p className="mt-1 text-sm text-slate-400">Derniers résultats publiés et cotes réelles. Ce n'est pas un signal : l'échantillon est court.</p>
        {(payload.readings ?? []).length === 0 && <p className="mt-3 text-sm text-slate-400">Aucune lecture disponible.</p>}
        <div className="mt-4 grid gap-4 xl:grid-cols-2">
          {(showAllReadings ? payload.readings ?? [] : (payload.readings ?? []).slice(0, 6)).map((reading) => {
            const teams = { home: reading.home_team ?? teamsFromMatch(reading.match).home, away: reading.away_team ?? teamsFromMatch(reading.match).away };
            const market = [...reading.markets].filter((item) => item.selection !== "none" && item.odds != null).sort((left, right) => (right.model_probability ?? 0) - (left.model_probability ?? 0))[0];
            if (!market) return null;
            const name = outcomeLabel(market.selection, teams.home, teams.away);
            return (
              <SignalCard
                key={reading.match_id}
                title={name}
                competition={`${reading.match} · ${reading.competition}`}
                when={(reading.kickoff_local || reading.date || "").replace("T", " ").slice(0, 16)}
                probabilityValue={market.model_probability}
                oddsValue={market.odds}
                marketProbability={market.market_probability ?? null}
                edge={market.edge}
                ev={market.ev}
                confidenceValue={market.confidence_score}
                qualityValue={market.data_quality ?? null}
                agreement={null}
                signalLabel="Lecture de forme"
                onOpen={() => navigate(`/matches/${reading.match_id}`)}
                added={slip.has(reading.match_id, name)}
                onAdd={() => slip.add({ matchId: reading.match_id, match: reading.match, selection: name, odds: market.odds, probability: market.model_probability })}
              />
            );
          })}
        </div>
        {(payload.readings ?? []).length > 6 && (
          <button className="mt-4 text-sm text-amber-300" type="button" onClick={() => setShowAllReadings((value) => !value)}>
            {showAllReadings ? "Réduire" : `Voir les ${(payload.readings ?? []).length} lectures`}
          </button>
        )}
      </section>
      <section>
        <h2 className="text-xl text-white">Résumé des matchs</h2>
        <p className="mt-2 text-slate-300">{payload.upcoming_matches} matchs sur 14 jours · {payload.matches_with_odds} avec une cote réelle.</p>
      </section>
    </section>
  );
}
