import { useEffect, useState } from "react";
import { Empty, num, pct } from "../components/ui";
import { api } from "../services/api";
import type { Opportunity } from "../types/api";

export function OpportunitiesPage() {
  const [items, setItems] = useState<Opportunity[]>([]);
  const [state, setState] = useState("");
  const [minEdge, setMinEdge] = useState("");
  const [error, setError] = useState("");

  function load(nextState = state, edge = minEdge) {
    const params = new URLSearchParams();
    if (nextState) params.set("state", nextState);
    if (edge) params.set("min_edge", edge);
    const query = params.toString() ? `?${params}` : "";
    api.opportunities(query).then((payload) => setItems(payload.items)).catch((reason: Error) => setError(reason.message));
  }

  useEffect(() => {
    load();
  }, []);

  if (error) return <Empty text="Impossible de charger les opportunités." />;
  return (
    <section className="space-y-4">
      <h1 className="text-3xl font-semibold text-white">Opportunities</h1>
      <p className="text-slate-400">Model Signal désigne un écart statistique filtré. Ce n'est pas un pari sûr.</p>
      <div className="flex gap-3">
        <select className="rounded-lg bg-slate-900 px-3 py-2" value={state} onChange={(event) => { setState(event.target.value); load(event.target.value, minEdge); }}>
          <option value="">Tous les états</option>
          <option value="SIGNAL">SIGNAL</option>
          <option value="NO_SIGNAL">NO_SIGNAL</option>
          <option value="LOW_CONFIDENCE">LOW_CONFIDENCE</option>
          <option value="INSUFFICIENT_DATA">INSUFFICIENT_DATA</option>
        </select>
        <input className="rounded-lg bg-slate-900 px-3 py-2" placeholder="edge minimum" value={minEdge} onChange={(event) => setMinEdge(event.target.value)} onBlur={() => load()} />
      </div>
      {!items.length && <Empty text="Aucune opportunité enregistrée." />}
      {!!items.length && (
        <div className="overflow-x-auto rounded-2xl border border-slate-800">
          <table className="w-full text-left text-sm">
            <thead className="bg-slate-900 text-slate-400">
              <tr>
                {["Match", "Date", "Marché", "Sélection", "Cote", "Modèle", "Marché", "Edge", "EV", "Qualité", "État"].map((header) => (
                  <th key={header} className="px-3 py-2">{header}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {items.map((item) => (
                <tr key={item.id} className="border-t border-slate-800">
                  <td className="px-3 py-2">{item.match}</td>
                  <td>{item.kickoff.slice(0, 10)}</td>
                  <td>{item.market}</td>
                  <td>{item.selection}</td>
                  <td>{item.odds.toFixed(2)}</td>
                  <td>{pct(item.model_probability)}</td>
                  <td>{pct(item.market_probability)}</td>
                  <td>{pct(item.edge)}</td>
                  <td>{pct(item.expected_value)}</td>
                  <td>{num(item.signal_quality, 1)}</td>
                  <td>{item.label}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
