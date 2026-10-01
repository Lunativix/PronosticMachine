import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { outcomeLabel } from "../format";
import { useSlip } from "../slip";
import { ConfidenceGauge, DataQualityBadge, EVDisplay, EdgeDisplay, OddsDisplay, ProbabilityDisplay, SignalBadge } from "../components/metrics";
import { Empty } from "../components/ui";

type Market = {
  id: number;
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
  favorable: string[];
  risks: string[];
  narrative?: string[];
  lineups?: { team: string; players: { name: string }[] }[];
  results?: { home?: ResultRow[]; away?: ResultRow[] };
};

type ResultRow = { result?: string; score?: string; opponent?: string; competition?: string; date?: string };

type Payload = {
  match: string;
  home_team: string;
  away_team: string;
  competition: string;
  date: string;
  kickoff_local: string | null;
  venue: string;
  status: string;
  model_agreement: number | null;
  markets: Market[];
};

export function MatchAnalysisPage() {
  const { matchId } = useParams();
  const slip = useSlip();
  const [payload, setPayload] = useState<Payload | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    fetch(`/analysis/matches/${matchId}`)
      .then(async (response) => {
        if (!response.ok) throw new Error(await response.text());
        return response.json();
      })
      .then(setPayload)
      .catch((reason: Error) => setError(reason.message));
  }, [matchId]);
  if (error) return <Empty text="Cette analyse n'est pas disponible." />;
  if (!payload) return <p className="text-slate-300">Chargement…</p>;
  const one = payload.markets.filter((row) => row.market === "1X2");
  const primary = payload.markets.find((row) => row.signal_label && !row.signal_label.toLowerCase().includes("aucun") && !row.signal_label.toLowerCase().includes("insuff")) ?? payload.markets[0];
  const label = (selection: string) => one.find((row) => row.selection === selection);
  return (
    <section className="space-y-6">
      <header>
        <p className="text-sm text-slate-400">{payload.competition}</p>
        <h1 className="text-3xl text-white">{payload.home_team} — {payload.away_team}</h1>
        <p className="text-slate-300">{(payload.kickoff_local || payload.date).replace("T", " ").slice(0, 16)} · {payload.venue} · {payload.status}</p>
      </header>
      <div className="grid gap-4 md:grid-cols-3">
        {(["home", "draw", "away"] as const).map((selection) => {
          const row = label(selection);
          return (
            <article key={selection} className="rounded-2xl border border-slate-800 bg-slate-900 p-4">
              <p className="text-slate-400">{outcomeLabel(selection, payload.home_team, payload.away_team)}</p>
              <p className="text-3xl font-semibold text-white"><ProbabilityDisplay value={row?.model_probability ?? null} /></p>
              <p className="mt-2 text-sm">Cote <OddsDisplay value={row?.odds ?? null} /></p>
              <p className="text-sm">Marché <ProbabilityDisplay value={row?.market_probability ?? null} /></p>
              <p className="text-sm">Edge <EdgeDisplay value={row?.edge ?? null} /></p>
              <p className="text-sm">EV <EVDisplay value={row?.ev ?? null} /></p>
              {row?.odds != null && (
                <button
                  className="mt-3 rounded-xl bg-white px-4 py-2 text-sm font-semibold text-ink"
                  type="button"
                  onClick={() => slip.add({
                    matchId: Number(matchId),
                    match: payload.match,
                    selection: outcomeLabel(selection, payload.home_team, payload.away_team),
                    odds: row.odds,
                    probability: row.model_probability,
                  })}
                >
                  {slip.has(Number(matchId), outcomeLabel(selection, payload.home_team, payload.away_team)) ? "Dans le combiné" : "Ajouter au combiné"}
                </button>
              )}
            </article>
          );
        })}
      </div>
      {primary && (
        <div className="grid gap-4 md:grid-cols-3">
          <article className="rounded-2xl border border-slate-800 bg-slate-900 p-4">
            <p className="text-slate-400">Cote</p>
            <p className="text-3xl"><OddsDisplay value={primary.odds} /></p>
            <p className="mt-2 text-slate-400">Probabilité marché</p>
            <ProbabilityDisplay value={primary.market_probability} />
            <p className="mt-2">Edge <EdgeDisplay value={primary.edge} /></p>
            <p>EV <EVDisplay value={primary.ev} /></p>
            {primary.odds === null && <p className="mt-2 text-amber-200">Cotes indisponibles</p>}
          </article>
          <article className="rounded-2xl border border-slate-800 bg-slate-900 p-4">
            <p className="text-slate-400">Confiance</p>
            <ConfidenceGauge value={primary.confidence_score} />
          </article>
          <article className="rounded-2xl border border-slate-800 bg-slate-900 p-4">
            <p className="text-slate-400">Qualité des données</p>
            <p className="text-3xl"><DataQualityBadge value={primary.data_quality} /></p>
            <p className="mt-3 text-slate-400">Accord des modèles</p>
            <p>Poisson : {label("home") ? <ProbabilityDisplay value={label("home")?.model_probability ?? null} /> : "Donnée indisponible"}</p>
            <p>Logistic : Donnée indisponible</p>
            <p>XGBoost : Donnée indisponible</p>
            <p>Ensemble : Donnée indisponible</p>
            <p className="mt-2"><SignalBadge label={primary.signal_label} /></p>
          </article>
        </div>
      )}
      <article className="rounded-2xl border border-slate-800 bg-slate-900 p-4">
        <h2 className="text-white">Résultats récents</h2>
        {(["home", "away"] as const).map((side) => {
          const rows = primary?.results?.[side] ?? [];
          const name = side === "home" ? payload.home_team : payload.away_team;
          return (
            <div key={side} className="mt-3">
              <p className="text-slate-400">{name}</p>
              {rows.length === 0 && <p className="text-sm text-slate-400">Donnée indisponible</p>}
              <ul className="mt-1 space-y-1 text-sm text-slate-300">
                {rows.map((row, index) => (
                  <li key={`${side}-${index}`}>
                    {row.result || "—"} {row.score || "—"} contre {row.opponent || "adversaire inconnu"}
                    {row.competition ? ` (${row.competition})` : ""}
                    {row.date ? ` · ${String(row.date).slice(0, 10)}` : ""}
                  </li>
                ))}
              </ul>
            </div>
          );
        })}
      </article>
      {primary?.narrative?.length ? (
        <article className="rounded-2xl border border-slate-800 bg-slate-900 p-4">
          <h2 className="text-white">Lecture</h2>
          <ul className="mt-2 space-y-1 text-sm text-slate-300">{primary.narrative.map((line) => <li key={line}>{line}</li>)}</ul>
        </article>
      ) : null}
      <article className="rounded-2xl border border-slate-800 bg-slate-900 p-4">
        <h2 className="text-white">Compositions</h2>
        {(primary?.lineups ?? []).length === 0 && <p className="mt-2 text-sm text-slate-400">Composition non publiée par le fournisseur.</p>}
        {(primary?.lineups ?? []).map((lineup) => (
          <div key={lineup.team} className="mt-3 text-sm text-slate-200">
            <p className="text-slate-400">{lineup.team}</p>
            <p>{lineup.players.map((player) => player.name).join(", ") || "Donnée indisponible"}</p>
          </div>
        ))}
      </article>
      {!payload.markets.length && <Empty text="Données insuffisantes. Aucune analyse n'est enregistrée pour ce match." />}
      <div className="grid gap-4 md:grid-cols-2">
        <article className="rounded-2xl border border-slate-800 bg-slate-900 p-4">
          <h2 className="text-white">Facteurs favorables</h2>
          <ul className="mt-2 text-sm text-slate-300">{(primary?.favorable ?? []).map((item) => <li key={item}>{item}</li>)}</ul>
          {(primary?.favorable ?? []).length === 0 && <p className="text-sm text-slate-400">Donnée indisponible</p>}
        </article>
        <article className="rounded-2xl border border-slate-800 bg-slate-900 p-4">
          <h2 className="text-white">Facteurs de risque</h2>
          <ul className="mt-2 text-sm text-slate-300">{(primary?.risks ?? []).map((item) => <li key={item}>{item}</li>)}</ul>
          {(primary?.risks ?? []).length === 0 && <p className="text-sm text-slate-400">Donnée indisponible</p>}
        </article>
      </div>
    </section>
  );
}
