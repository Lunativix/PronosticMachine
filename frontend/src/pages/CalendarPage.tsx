import { useEffect, useState } from "react";
import { CompetitionFilter } from "../components/CompetitionFilter";
import { Empty } from "../components/ui";

type Day = { date: string; matches: number; competitions: number; signals: number; propositions: number };

function dayLabel(date: string): string {
  const today = new Date();
  const start = new Date(today.getFullYear(), today.getMonth(), today.getDate());
  const target = new Date(`${date}T00:00:00`);
  const diff = Math.round((target.getTime() - start.getTime()) / 86400000);
  if (diff === 0) return "Aujourd'hui";
  if (diff === 1) return "Demain";
  if (diff > 1) return `J+${diff}`;
  return date;
}

export function CalendarPage() {
  const [days, setDays] = useState<Day[]>([]);
  const [competitionIds, setCompetitionIds] = useState<number[]>([]);
  const [error, setError] = useState("");
  useEffect(() => {
    const params = new URLSearchParams({ days: "14" });
    for (const id of competitionIds) params.append("competition_id", String(id));
    fetch(`/fixtures/calendar?${params}`)
      .then(async (response) => {
        if (!response.ok) throw new Error(await response.text());
        return response.json();
      })
      .then((payload) => setDays(payload.days))
      .catch((reason: Error) => setError(reason.message));
  }, [competitionIds]);
  if (error) return <Empty text="Le calendrier n'a pas pu être chargé." />;
  return (
    <section className="space-y-4">
      <h1 className="text-3xl font-semibold text-white">Calendrier</h1>
      <CompetitionFilter days={14} selected={competitionIds} onChange={setCompetitionIds} />
      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
        {days.map((day) => (
          <article key={day.date} className="rounded-2xl border border-slate-800 bg-slate-900 p-4">
            <h2 className="text-lg text-white">{dayLabel(day.date)}</h2>
            <p className="text-sm text-slate-400">{day.date}</p>
            <p className="mt-2 text-2xl font-semibold tabular-nums text-white">{day.matches}</p>
            <p className="text-sm text-slate-400">matchs · {day.competitions} compétitions</p>
            <p className="text-sm text-slate-300">{day.signals} signaux · {day.propositions} propositions</p>
          </article>
        ))}
      </div>
      {days.length === 0 && <Empty text="Aucun match dans la fenêtre." />}
    </section>
  );
}
