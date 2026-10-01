import { useEffect, useState } from "react";
import { Empty, num } from "../components/ui";
import { api } from "../services/api";
import type { ModelRow } from "../types/api";

export function ModelsPage() {
  const [items, setItems] = useState<ModelRow[]>([]);
  useEffect(() => {
    api.models().then((payload) => setItems(payload.items)).catch(() => setItems([]));
  }, []);
  if (!items.length) return <Empty text="Aucun modèle versionné. Entraînez d'abord avec sportwise model train." />;
  return (
    <section className="space-y-4">
      <h1 className="text-3xl font-semibold text-white">Models</h1>
      <div className="grid gap-4">
        {items.map((item) => (
          <article key={item.id} className="rounded-2xl border border-slate-800 bg-slate-900 p-4">
            <h2 className="text-xl text-white">{item.model_key} {item.version} {item.is_active ? "· actif" : ""}</h2>
            <p className="text-sm text-slate-400">{item.training_date} · features {item.feature_version}</p>
            <p className="text-sm text-slate-400">dataset {item.dataset_hash.slice(0, 12)}</p>
            <p className="mt-2 text-sm text-slate-200">
              Brier {num(Number(item.metrics.brier ?? item.metrics.validation_brier))} · Log loss {num(Number(item.metrics.log_loss ?? item.metrics.validation_log_loss))} · ECE {num(Number(item.metrics.ece ?? item.metrics.validation_ece))}
            </p>
          </article>
        ))}
      </div>
    </section>
  );
}
