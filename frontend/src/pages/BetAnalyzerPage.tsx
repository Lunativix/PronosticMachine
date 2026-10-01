import { useEffect, useState } from "react";
import { CombinationCard, ConfidenceBadge, DataQualityBadge, EVDisplay, EdgeDisplay, OddsDisplay, ProbabilityDisplay, SignalBadge } from "../components/metrics";
import { Empty } from "../components/ui";

type MarketRow = {
  id: number;
  market: string;
  selection: string;
  odds: number | null;
  model_probability: number | null;
  edge: number | null;
  ev: number | null;
  confidence_score: number;
  confidence_level: string;
  confidence_label: string;
  signal: string;
  signal_label: string;
  data_quality: number;
  favorable: string[];
  risks: string[];
};

type MatchBlock = {
  match_id: number;
  match: string;
  date: string;
  competition: string;
  markets: MarketRow[];
};

type Combo = {
  id: number;
  selections: { match: string; market: string; selection: string; odds: number | null }[];
  combined_odds: number | null;
  combined_probability: number | null;
  combined_ev: number | null;
  confidence_score: number;
  correlation_risk: string;
  correlation_status: string;
  combination_scope: string;
  size: number;
};

const TITLES: Record<string, string> = {
  PRUDENT: "COMBINÉ PRUDENT",
  VALUE: "COMBINÉ VALUE",
  BALANCED: "COMBINÉ ÉQUILIBRÉ",
};

export function BetAnalyzerPage() {
  const [matches, setMatches] = useState<MatchBlock[]>([]);
  const [categories, setCategories] = useState<Record<string, Combo[]>>({});
  const [performance, setPerformance] = useState<Record<string, unknown> | null>(null);
  const [disclaimer, setDisclaimer] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    Promise.all([
      fetch("/analysis/upcoming").then((response) => response.json()),
      fetch("/analysis/combinations").then((response) => response.json()),
      fetch("/analysis/performance").then((response) => response.json()),
    ])
      .then(([analysis, combos, perf]) => {
        setDisclaimer(analysis.disclaimer ?? "");
        setMatches(analysis.matches ?? []);
        setCategories(combos.categories ?? {});
        setPerformance(perf);
      })
      .catch((reason: Error) => setError(reason.message));
  }, []);

  if (error) return <Empty text="L'analyseur n'a pas pu charger les données." />;

  return (
    <section className="space-y-8">
      <div>
        <h1 className="text-3xl font-semibold text-white">Bet Analyzer</h1>
        <p className="mt-2 max-w-3xl text-sm text-slate-300">{disclaimer}</p>
      </div>
      <div>
        <h2 className="text-xl text-white">MATCHES</h2>
        {matches.length === 0 && (
          <Empty text="Aucune analyse enregistrée. Lancez sportwise analysis run lorsque des matchs, un modèle et, pour l'edge, des cotes sont disponibles." />
        )}
        <div className="mt-4 space-y-4">
          {matches.map((match) => (
            <article key={match.match_id} className="rounded-2xl border border-slate-800 bg-slate-900 p-4">
              <h3 className="text-lg text-white">{match.match}</h3>
              <p className="text-sm text-slate-400">{match.date} · {match.competition}</p>
              <div className="mt-3 overflow-x-auto">
                <table className="w-full text-left text-sm">
                  <thead className="text-slate-400">
                    <tr>
                      <th>Marché</th><th>Sélection</th><th>Cote</th><th>Probabilité modèle</th><th>Edge</th><th>EV</th><th>Confiance</th><th>Qualité</th><th>Signal</th>
                    </tr>
                  </thead>
                  <tbody>
                    {match.markets.map((row) => (
                      <tr key={row.id} className="border-t border-slate-800 text-slate-200">
                        <td>{row.market}</td>
                        <td>{row.selection}</td>
                        <td className="text-right"><OddsDisplay value={row.odds} /></td>
                        <td className="text-right"><ProbabilityDisplay value={row.model_probability} /></td>
                        <td className="text-right"><EdgeDisplay value={row.edge} /></td>
                        <td className="text-right"><EVDisplay value={row.ev} /></td>
                        <td className="text-right"><ConfidenceBadge value={row.confidence_score} /></td>
                        <td className="text-right"><DataQualityBadge value={row.data_quality} /></td>
                        <td><SignalBadge label={row.signal_label} /></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {match.markets[0] && (
                <div className="mt-3 grid gap-3 text-sm text-slate-300 md:grid-cols-2">
                  <div>
                    <p className="text-slate-400">Facteurs favorables</p>
                    <ul>{(match.markets.find((row) => row.favorable.length) ?? match.markets[0]).favorable.map((item) => <li key={item}>{item}</li>)}</ul>
                  </div>
                  <div>
                    <p className="text-slate-400">Facteurs de risque</p>
                    <ul>{(match.markets.find((row) => row.risks.length) ?? match.markets[0]).risks.map((item) => <li key={item}>{item}</li>)}</ul>
                  </div>
                </div>
              )}
            </article>
          ))}
        </div>
      </div>
      <div>
        <h2 className="text-xl text-white">COMBINATIONS</h2>
        {Object.entries(TITLES).map(([key, title]) => (
          <section key={key} className="mt-4 rounded-2xl border border-slate-800 bg-slate-900 p-4">
            <h3 className="text-white">{title}</h3>
            {(categories[key] ?? []).length === 0 && <p className="mt-2 text-sm text-slate-400">Aucune combinaison ne passe les seuils sur ce passage.</p>}
            {(categories[key] ?? []).map((combo) => (
              <div key={combo.id} className="mt-3">
                <CombinationCard
                  title={title}
                  legs={combo.selections.map((leg) => ({ label: `${leg.match} — ${leg.market} ${leg.selection}`, odds: leg.odds }))}
                  combinedOdds={combo.combined_odds}
                  probabilityValue={combo.combined_probability}
                  ev={combo.combined_ev}
                  confidenceValue={combo.confidence_score}
                  correlation={combo.correlation_risk}
                />
              </div>
            ))}
          </section>
        ))}
      </div>
      <div className="rounded-2xl border border-slate-800 bg-slate-900 p-4 text-sm text-slate-300">
        <h2 className="text-white">Performances historiques</h2>
        <pre className="mt-2 overflow-x-auto whitespace-pre-wrap">{JSON.stringify(performance, null, 2)}</pre>
      </div>
    </section>
  );
}
