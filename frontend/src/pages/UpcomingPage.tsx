import { useEffect, useMemo, useState } from "react";
import { CompetitionFilter } from "../components/CompetitionFilter";
import { Empty } from "../components/ui";

type Fixture = {
  id: number;
  competition: string;
  home_team: string;
  away_team: string;
  scheduled_at_utc: string;
  scheduled_at_local: string | null;
  status: string;
  source: string;
  last_seen_at: string | null;
};

function chip(active: boolean) {
  return `rounded-xl px-3 py-2 text-sm font-semibold disabled:opacity-40 ${active ? "bg-white text-ink" : "border border-white/40 bg-transparent text-white hover:bg-white/10"}`;
}

export function UpcomingPage() {
  const [days, setDays] = useState(60);
  const [query, setQuery] = useState("");
  const [competitionIds, setCompetitionIds] = useState<number[]>([]);
  const [mode, setMode] = useState<"all" | "signals" | "no_signals">("all");
  const [view, setView] = useState<"table" | "calendar">("table");
  const [offset, setOffset] = useState(0);
  const [total, setTotal] = useState(0);
  const [matches, setMatches] = useState<Fixture[]>([]);
  const [windowLabel, setWindowLabel] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    const params = new URLSearchParams({ days: String(days), view: mode, limit: "50", offset: String(offset) });
    if (query) params.set("q", query);
    for (const id of competitionIds) params.append("competition_id", String(id));
    fetch(`/fixtures/upcoming?${params}`)
      .then(async (response) => {
        if (!response.ok) throw new Error(await response.text());
        return response.json();
      })
      .then((payload) => {
        setMatches(payload.matches);
        setTotal(payload.total);
        setWindowLabel(`${payload.window.start} → ${payload.window.end}`);
        setLoading(false);
      })
      .catch((reason: Error) => { setError(reason.message); setLoading(false); });
  }, [days, query, mode, offset, competitionIds]);

  const visible = matches;
  const byDay = useMemo(() => {
    const groups = new Map<string, Fixture[]>();
    for (const item of visible) {
      const key = (item.scheduled_at_local || item.scheduled_at_utc).slice(0, 10);
      groups.set(key, [...(groups.get(key) ?? []), item]);
    }
    return [...groups.entries()];
  }, [visible]);
  if (error) return <Empty text={error} />;
  return (
    <section className="space-y-4">
      <h1 className="text-3xl font-semibold text-white">Tous les matchs</h1>
      <p className="text-slate-400">Fenêtre glissante Europe/Paris. {windowLabel}</p>
      <p className="text-white">Total : {total}</p>
      <div className="space-y-3 rounded-2xl border border-slate-800 bg-slate-900 p-4">
        <div className="flex flex-wrap gap-2" role="group" aria-label="Signal">
          {([
            ["all", "Tous"],
            ["signals", "Avec signal"],
            ["no_signals", "Sans signal"],
          ] as const).map(([value, label]) => (
            <button key={value} type="button" aria-pressed={mode === value} className={chip(mode === value)} onClick={() => { setOffset(0); setMode(value); }}>{label}</button>
          ))}
        </div>
        <div className="flex flex-wrap gap-2" role="group" aria-label="Période">
          {[1, 7, 14, 30, 60].map((value) => (
            <button key={value} type="button" aria-pressed={days === value} className={chip(days === value)} onClick={() => { setOffset(0); setDays(value); }}>
              {value === 1 ? "Aujourd'hui" : `${value} jours`}
            </button>
          ))}
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <button type="button" className={chip(false)} onClick={() => setView(view === "table" ? "calendar" : "table")}>
            {view === "table" ? "Vue calendrier" : "Vue tableau"}
          </button>
          <input className="min-w-56 flex-1 rounded-xl border border-slate-700 bg-slate-950 px-3 py-2 text-sm" placeholder="Équipe, compétition, pays" value={query} onChange={(event) => { setOffset(0); setQuery(event.target.value); }} />
        </div>
      </div>
      <CompetitionFilter days={days} selected={competitionIds} onChange={(ids) => { setOffset(0); setCompetitionIds(ids); }} />
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-slate-300">{total === 0 ? "0–0 sur 0" : `${offset + 1}–${Math.min(offset + visible.length, total)} sur ${total}`}</p>
        <div className="flex gap-2">
          <button type="button" className={chip(false)} disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - 50))}>Précédent</button>
          <button type="button" className={chip(false)} disabled={offset + visible.length >= total} onClick={() => setOffset(offset + 50)}>Suivant</button>
        </div>
      </div>
      {loading && <p className="text-slate-300">Chargement des matchs…</p>}
      {!loading && !visible.length && <Empty text={mode === "signals" ? "Aucun signal dans cette fenêtre." : "Aucun match à venir dans cette fenêtre."} />}
      {view === "calendar" && (
        <div className="grid gap-3 md:grid-cols-2">
          {byDay.map(([day, items]) => (
            <article key={day} className="rounded-2xl bg-slate-900 p-3">
              <h2 className="text-white">{day} · {items.length}</h2>
              {items.map((item) => (
                <p key={item.id} className="text-sm text-slate-300">{item.home_team} vs {item.away_team}</p>
              ))}
            </article>
          ))}
        </div>
      )}
      {view === "table" && !!visible.length && (
        <div className="overflow-x-auto rounded-2xl border border-slate-800">
          <table className="w-full text-left text-sm">
            <thead className="bg-slate-900 text-slate-400">
              <tr>{["Date", "Heure", "Compétition", "Domicile", "Extérieur", "Statut", "Source", "Vu"].map((header) => <th key={header} className="px-3 py-2">{header}</th>)}</tr>
            </thead>
            <tbody>
              {visible.map((item) => (
                <tr key={item.id} className="border-t border-slate-800">
                  <td className="px-3 py-2">{(item.scheduled_at_local || item.scheduled_at_utc).slice(0, 10)}</td>
                  <td>{(item.scheduled_at_local || item.scheduled_at_utc).slice(11, 16)}</td>
                  <td>{item.competition}</td>
                  <td>{item.home_team}</td>
                  <td>{item.away_team}</td>
                  <td>{item.status}</td>
                  <td>{item.source}</td>
                  <td>{item.last_seen_at?.slice(0, 16) ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
