import { useEffect, useState } from "react";
import { Empty } from "../components/ui";

export function ConfigPage() {
  const [payload, setPayload] = useState<Record<string, string | number | boolean> | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    fetch("/config/thresholds")
      .then(async (response) => {
        if (!response.ok) throw new Error(await response.text());
        return response.json();
      })
      .then(setPayload)
      .catch((reason: Error) => setError(reason.message));
  }, []);
  if (error) return <Empty text="La configuration n'a pas pu être chargée." />;
  if (!payload) return <p className="text-slate-300">Chargement…</p>;
  return (
    <section className="space-y-4">
      <h1 className="text-3xl font-semibold text-white">Configuration</h1>
      <p className="text-sm text-slate-400">Ces seuils viennent des paramètres du serveur. Ils ne sont pas figés dans l'interface.</p>
      <dl className="grid max-w-xl gap-3 rounded-2xl border border-slate-800 bg-slate-900 p-4 text-sm">
        {Object.entries(payload).map(([key, value]) => (
          <div key={key} className="flex justify-between gap-4">
            <dt className="text-slate-400">{key}</dt>
            <dd className="tabular-nums text-white">{String(value)}</dd>
          </div>
        ))}
      </dl>
    </section>
  );
}
