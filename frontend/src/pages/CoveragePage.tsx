import { useEffect, useState } from "react";
import { MetricCard } from "../components/metrics";
import { Empty } from "../components/ui";

type Item = {
  id: number;
  country: string;
  name: string;
  competition_type: string;
  season: string;
  fixtures_j14: number;
  odds_available: boolean;
  last_sync: string | null;
};

type Payload = {
  total_discovered: number;
  active: number;
  with_fixtures: number;
  with_odds: number;
  filtered: number;
  limit: number;
  offset: number;
  last_sync: string | null;
  sync_status: string | null;
  items: Item[];
};

export function CoveragePage() {
  const [query, setQuery] = useState("");
  const [sort, setSort] = useState("country");
  const [offset, setOffset] = useState(0);
  const [payload, setPayload] = useState<Payload | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    const params = new URLSearchParams({ sort, limit: "50", offset: String(offset) });
    if (query) params.set("q", query);
    fetch(`/competitions/coverage?${params}`)
      .then(async (response) => {
        if (!response.ok) throw new Error(await response.text());
        return response.json();
      })
      .then((body: Payload) => {
        setPayload(body);
        setError("");
      })
      .catch((reason: Error) => setError(reason.message));
  }, [query, sort, offset]);

  if (error) return <Empty text="La couverture des compétitions n'a pas pu être chargée." />;
  if (!payload) return <p className="text-slate-300">Chargement…</p>;
  const from = payload.filtered === 0 ? 0 : payload.offset + 1;
  const to = Math.min(payload.offset + payload.items.length, payload.filtered);
  const status = payload.sync_status === "running" ? "Synchronisation en cours" : payload.sync_status === "error" ? "Erreur de synchronisation" : payload.sync_status ? "À jour" : "Donnée indisponible";

  return (
    <section className="space-y-6">
      <header>
        <h1 className="text-3xl font-semibold text-white">Competition Coverage</h1>
        <p className="text-sm text-slate-300">Dernière synchronisation : {payload.last_sync ? new Date(payload.last_sync).toLocaleString("fr-FR") : "—"} · {status}</p>
      </header>
      <div className="grid gap-4 md:grid-cols-4">
        <MetricCard label="Compétitions disponibles" value={payload.total_discovered} />
        <MetricCard label="Compétitions actives" value={payload.active} />
        <MetricCard label="Avec fixtures" value={payload.with_fixtures} />
        <MetricCard label="Avec cotes" value={payload.with_odds} />
      </div>
      <div className="flex flex-wrap gap-2">
        <input
          className="rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm"
          placeholder="Rechercher une compétition..."
          value={query}
          onChange={(event) => {
            setOffset(0);
            setQuery(event.target.value);
          }}
        />
        <select className="rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm" value={sort} onChange={(event) => setSort(event.target.value)}>
          <option value="country">Pays</option>
          <option value="name">Nom</option>
          <option value="fixtures">Nombre de matchs</option>
          <option value="last_sync">Dernière synchronisation</option>
        </select>
      </div>
      <div className="overflow-x-auto rounded-2xl border border-slate-800">
        <table className="w-full text-left text-sm">
          <thead className="text-slate-400">
            <tr>
              <th className="p-3">Pays</th>
              <th>Compétition</th>
              <th>Type</th>
              <th>Saison</th>
              <th className="text-right">Matchs J+14</th>
              <th className="text-right">Cotes</th>
              <th className="text-right">Dernière synchro</th>
            </tr>
          </thead>
          <tbody>
            {payload.items.map((item) => (
              <tr key={item.id} className="border-t border-slate-800 text-slate-100">
                <td className="p-3">{item.country}</td>
                <td>{item.name}</td>
                <td>{item.competition_type}</td>
                <td>{item.season}</td>
                <td className="text-right tabular-nums">{item.fixtures_j14}</td>
                <td className="text-right">{item.odds_available ? "Oui" : "Non"}</td>
                <td className="text-right">{item.last_sync ? new Date(item.last_sync).toLocaleString("fr-FR") : "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {payload.items.length === 0 && <Empty text="Aucune compétition découverte pour ces filtres." />}
      <div className="flex items-center justify-between text-sm text-slate-300">
        <p>{from}–{to} sur {payload.filtered}</p>
        <div className="flex gap-2">
          <button className="rounded border border-slate-700 px-3 py-1" type="button" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - 50))}>Précédent</button>
          <button className="rounded border border-slate-700 px-3 py-1" type="button" disabled={to >= payload.filtered} onClick={() => setOffset(offset + 50)}>Suivant</button>
        </div>
      </div>
    </section>
  );
}
