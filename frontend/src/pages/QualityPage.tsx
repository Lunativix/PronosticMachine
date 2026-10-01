import { useEffect, useState } from "react";
import { Empty } from "../components/ui";
import { api } from "../services/api";
import type { QualityReport } from "../types/api";

export function QualityPage() {
  const [items, setItems] = useState<QualityReport[]>([]);
  useEffect(() => {
    api.quality().then((payload) => setItems(payload.items)).catch(() => setItems([]));
  }, []);
  if (!items.length) return <Empty text="Aucun rapport de qualité. Importez un fichier pour en produire un." />;
  return (
    <section className="space-y-4">
      <h1 className="text-3xl font-semibold text-white">Data Quality</h1>
      {items.map((item) => (
        <article key={item.id} className="rounded-2xl border border-slate-800 bg-slate-900 p-4">
          <h2 className="text-lg text-white">{item.source}</h2>
          <p className="text-sm text-slate-300">
            {item.records_valid} valides / {item.records_total} · invalides {item.records_invalid} · manquants {item.missing_values} · doublons {item.duplicates} · fuite {item.future_leakage}
          </p>
          <ul className="mt-2 text-sm text-amber-200">
            {item.errors.slice(0, 8).map((error, index) => (
              <li key={`${error.code}-${index}`}>Erreur ligne {error.row}: {error.message}</li>
            ))}
            {item.warnings.slice(0, 8).map((warning, index) => (
              <li key={`${warning.code}-${index}`}>Warning ligne {warning.row}: {warning.message}</li>
            ))}
          </ul>
        </article>
      ))}
    </section>
  );
}
