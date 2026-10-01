import { useEffect, useState } from "react";
import { Bar, BarChart, CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Empty, pct } from "../components/ui";
import { api } from "../services/api";

export function BacktestPage() {
  const [runs, setRuns] = useState<{ id: number; name: string; staking: string }[]>([]);
  const [detail, setDetail] = useState<{ metrics: Record<string, number>; bankroll: { as_of: string; bankroll: number; drawdown: number }[]; results: { pnl: number }[] } | null>(null);

  useEffect(() => {
    api.backtests().then((payload) => {
      setRuns(payload.items);
      if (payload.items[0]) {
        api.backtest(payload.items[0].id).then(setDetail).catch(() => setDetail(null));
      }
    }).catch(() => setRuns([]));
  }, []);

  if (!runs.length) return <Empty text="Aucun backtest enregistré. La commande est : sportwise backtest run" />;
  return (
    <section className="space-y-4">
      <h1 className="text-3xl font-semibold text-white">Backtesting</h1>
      <p className="text-slate-400">Walk-forward uniquement. Le ROI ci-dessous décrit une simulation, pas un gain futur.</p>
      <div className="grid gap-4 md:grid-cols-3">
        <p className="rounded-2xl bg-slate-900 p-4">ROI {pct(detail?.metrics.roi)}</p>
        <p className="rounded-2xl bg-slate-900 p-4">Drawdown {pct(detail?.metrics.max_drawdown)}</p>
        <p className="rounded-2xl bg-slate-900 p-4">Paris {detail?.metrics.bets ?? 0}</p>
      </div>
      <div className="grid gap-4 md:grid-cols-2">
        <div className="h-64 rounded-2xl bg-slate-900 p-3">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={detail?.bankroll ?? []}>
              <CartesianGrid stroke="#1f2937" />
              <XAxis dataKey="as_of" hide />
              <YAxis stroke="#94a3b8" />
              <Tooltip />
              <Line dataKey="bankroll" stroke="#38bdf8" dot={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>
        <div className="h-64 rounded-2xl bg-slate-900 p-3">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={detail?.bankroll ?? []}>
              <CartesianGrid stroke="#1f2937" />
              <XAxis dataKey="as_of" hide />
              <YAxis stroke="#94a3b8" />
              <Tooltip />
              <Bar dataKey="drawdown" fill="#f97316" />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>
    </section>
  );
}
