import { useEffect, useState } from "react";
import { Empty, num, pct } from "../components/ui";
import { api } from "../services/api";
import type { MatchItem, Opportunity, Prediction } from "../types/api";

export function AnalyzerPage() {
  const [matches, setMatches] = useState<MatchItem[]>([]);
  const [selected, setSelected] = useState<number | null>(null);
  const [prediction, setPrediction] = useState<Prediction | null>(null);
  const [values, setValues] = useState<Opportunity[]>([]);
  const [error, setError] = useState("");

  useEffect(() => {
    api.matches().then((payload) => {
      setMatches(payload.items);
      if (payload.items[0]) setSelected(payload.items[0].id);
    }).catch((reason: Error) => setError(reason.message));
  }, []);

  useEffect(() => {
    if (!selected) return;
    setPrediction(null);
    api.prediction(selected).then(setPrediction).catch(() => setPrediction(null));
    api.value(selected).then((payload) => setValues(payload.items)).catch(() => setValues([]));
  }, [selected]);

  if (error) return <Empty text="Impossible de charger les matchs." />;
  const match = matches.find((item) => item.id === selected);
  return (
    <section className="space-y-4">
      <h1 className="text-3xl font-semibold text-white">Match Analyzer</h1>
      <select
        className="rounded-lg border border-slate-700 bg-slate-900 px-3 py-2"
        value={selected ?? ""}
        onChange={(event) => setSelected(Number(event.target.value))}
      >
        {matches.map((item) => (
          <option key={item.id} value={item.id}>
            {item.home_team} vs {item.away_team}
          </option>
        ))}
      </select>
      {!match && <Empty text="Aucun match importé." />}
      {match && (
        <div className="rounded-2xl border border-slate-800 bg-slate-900 p-5">
          <p className="text-sm text-slate-400">{match.kickoff} · source {match.source}</p>
          <h2 className="mt-2 text-2xl text-white">{match.home_team} vs {match.away_team}</h2>
          <p className="text-slate-300">Score enregistré : {match.home_goals ?? "—"} - {match.away_goals ?? "—"}</p>
        </div>
      )}
      {!prediction && match && <Empty text="Pas encore de prédiction pour ce match. Lancez sportwise prediction generate." />}
      {prediction && (
        <div className="grid gap-4 md:grid-cols-2">
          <div className="rounded-2xl border border-slate-800 bg-slate-900 p-4">
            <h3 className="font-medium text-white">Probabilités</h3>
            <p className="text-sm text-slate-400">État {prediction.state} · confiance {pct(prediction.confidence)} · qualité {num(prediction.signal_quality, 1)}</p>
            {prediction.probabilities_shrunk && <p className="text-amber-300">Historique insuffisant : probabilités rétractées vers un prior uniforme.</p>}
            <table className="mt-3 w-full text-sm">
              <thead><tr className="text-slate-400"><th className="text-left">Issue</th><th>Brute</th><th>Calibrée</th></tr></thead>
              <tbody>
                {prediction.probabilities.map((item) => (
                  <tr key={item.selection}><td>{item.selection}</td><td className="text-center">{pct(item.raw)}</td><td className="text-center">{pct(item.calibrated)}</td></tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="rounded-2xl border border-slate-800 bg-slate-900 p-4">
            <h3 className="font-medium text-white">Statistical edge</h3>
            {values.length === 0 && <p className="text-slate-400">Aucune cote pré-match exploitable.</p>}
            {values.map((item) => (
              <p key={item.id} className="mt-2 text-sm text-slate-300">
                {item.selection} @ {item.odds.toFixed(2)} · modèle {pct(item.model_probability)} · marché {pct(item.market_probability)} · edge {pct(item.edge)} · EV {pct(item.expected_value)} · {item.label}
              </p>
            ))}
          </div>
          <div className="rounded-2xl border border-slate-800 bg-slate-900 p-4 md:col-span-2">
            <h3 className="font-medium text-white">Facteurs ({prediction.explanation_method})</h3>
            <ul className="mt-2 space-y-1 text-sm text-slate-300">
              {(prediction.explanation.factors ?? []).map((factor) => (
                <li key={factor.name}>{factor.direction === "positive" ? "+" : "−"} {factor.name} ({factor.value.toFixed(3)})</li>
              ))}
              {(prediction.explanation.factors ?? []).length === 0 && <li>Aucune contribution calculée pour ce modèle.</li>}
            </ul>
            <p className="mt-3 text-xs text-slate-500">{prediction.explanation.disclaimer}</p>
          </div>
        </div>
      )}
    </section>
  );
}
