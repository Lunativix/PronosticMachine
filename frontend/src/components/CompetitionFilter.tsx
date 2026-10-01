import { useEffect, useMemo, useState } from "react";

export type CompetitionOption = {
  id: number;
  name: string;
  display_name?: string;
  country: string;
  matches: number;
};

export function CompetitionFilter({
  days,
  selected,
  onChange,
}: {
  days: number;
  selected: number[];
  onChange: (ids: number[]) => void;
}) {
  const [options, setOptions] = useState<CompetitionOption[]>([]);
  const [search, setSearch] = useState("");

  useEffect(() => {
    fetch(`/fixtures/competitions?days=${days}`)
      .then((response) => response.json())
      .then((payload) => setOptions(payload.items ?? []))
      .catch(() => setOptions([]));
  }, [days]);

  const visible = useMemo(() => {
    const needle = search.trim().toLocaleLowerCase("fr");
    if (!needle) return options;
    return options.filter((item) => `${item.country} ${item.display_name || item.name} ${item.name}`.toLocaleLowerCase("fr").includes(needle));
  }, [options, search]);

  function toggle(id: number) {
    onChange(selected.includes(id) ? selected.filter((item) => item !== id) : [...selected, id]);
  }

  return (
    <div className="rounded-2xl border border-slate-800 bg-slate-900 p-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-slate-300">Compétitions · {options.length} avec des matchs</p>
        <button className="text-sm text-amber-300" type="button" onClick={() => onChange([])}>Toutes</button>
      </div>
      <input
        className="mt-3 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm"
        placeholder="Filtrer une compétition ou un pays"
        value={search}
        onChange={(event) => setSearch(event.target.value)}
      />
      <div className="mt-3 max-h-52 space-y-1 overflow-y-auto">
        {visible.map((item) => (
          <label key={item.id} className={`flex cursor-pointer items-center justify-between gap-3 rounded-xl px-3 py-2 text-sm hover:bg-slate-800 ${selected.includes(item.id) ? "bg-slate-800" : ""}`}>
            <span className="flex items-center gap-3 text-slate-100">
              <input className="h-4 w-4" type="checkbox" checked={selected.includes(item.id)} onChange={() => toggle(item.id)} />
              <span>{item.display_name || item.name}</span>
              <span className="text-slate-500">{item.country}</span>
            </span>
            <span className="tabular-nums text-slate-400">{item.matches}</span>
          </label>
        ))}
        {visible.length === 0 && <p className="text-sm text-slate-400">Aucune compétition ne correspond.</p>}
      </div>
    </div>
  );
}
