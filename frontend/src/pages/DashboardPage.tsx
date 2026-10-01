import { useEffect, useState } from "react";
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { MetricCard } from "../components/metrics";
import { Empty, Stat, pct } from "../components/ui";
import { api } from "../services/api";

export function DashboardPage() {
  const [data, setData] = useState<Record<string, unknown> | null>(null);
  const [overview, setOverview] = useState<{ matches: number; competitions: number; signals: number; last_sync: string | null; sync_status: string | null; syncing: boolean } | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api.performance().then(setData).catch((reason: Error) => setError(reason.message));
    fetch("/dashboard/overview").then((response) => response.json()).then(setOverview).catch(() => setOverview(null));
  }, []);

  if (error) return <Empty text="L'API n'est pas disponible. Démarrez le backend puis rechargez cette page." />;
  if (!data) return <p>Chargement…</p>;
  const metrics = ((data.latest_backtest as { metrics?: Record<string, number> } | null)?.metrics) ?? {};
  const bankroll = (data.bankroll as { as_of: string; bankroll: number; drawdown: number }[]) ?? [];
  return (
    <section className="space-y-6">
      <header>
        <h1 className="text-3xl font-semibold text-white">SPORTWISE AI</h1>
        <p className="text-slate-400">Football · 14 prochains jours</p>
        <p className="text-sm text-slate-300">
          Dernière synchronisation : {overview?.last_sync ? new Date(overview.last_sync).toLocaleString("fr-FR") : "—"}
          {" · "}
          {overview?.syncing ? "Synchronisation en cours" : overview?.sync_status === "error" ? "Erreur de synchronisation" : overview?.sync_status ? "À jour" : "Donnée indisponible"}
        </p>
      </header>
      <div className="grid gap-4 md:grid-cols-3">
        <MetricCard label="Matchs" value={overview ? overview.matches : "—"} />
        <MetricCard label="Compétitions" value={overview ? overview.competitions : "—"} />
        <MetricCard label="Signaux" value={overview ? overview.signals : "—"} />
      </div>
      {Boolean(data.synthetic_dataset) && (
        <p className="rounded-xl border border-amber-500/40 bg-amber-500/10 p-3 text-sm text-amber-100">
          Le jeu chargé est synthétique et sert aux tests. Les ROI affichés ne sont pas une performance sportive réelle.
        </p>
      )}
      <div className="grid gap-4 md:grid-cols-4">
        <Stat label="Matchs importés" value={String(data.matches ?? 0)} />
        <Stat label="Prédictions" value={String(data.predictions ?? 0)} />
        <Stat label="Model signals" value={String(data.signals ?? 0)} />
        <Stat label="ROI backtest" value={pct(metrics.roi)} />
      </div>
      <div className="grid gap-4 md:grid-cols-3">
        <Stat label="Yield" value={pct(metrics.yield)} />
        <Stat label="Drawdown max" value={pct(metrics.max_drawdown)} />
        <Stat label="Bankroll finale" value={metrics.final_bankroll?.toFixed(2) ?? "—"} />
      </div>
      <div className="h-72 rounded-2xl border border-slate-800 bg-slate-900 p-4">
        {bankroll.length ? (
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={bankroll}>
              <CartesianGrid stroke="#1f2937" />
              <XAxis dataKey="as_of" hide />
              <YAxis stroke="#94a3b8" />
              <Tooltip />
              <Line dataKey="bankroll" stroke="#f59e0b" dot={false} />
            </LineChart>
          </ResponsiveContainer>
        ) : (
          <Empty text="Aucune bankroll simulée. Lancez un backtest pour afficher la courbe." />
        )}
      </div>
    </section>
  );
}
