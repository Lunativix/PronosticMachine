import { NavLink, Outlet } from "react-router-dom";
import { SlipPanel } from "../slip";

const groups = [
  {
    title: "Décider",
    links: [
      ["/", "Propositions"],
      ["/signals", "Signaux"],
      ["/combinations", "Combinés"],
    ],
  },
  {
    title: "Explorer",
    links: [
      ["/matches", "Matchs"],
      ["/calendar", "Calendrier"],
      ["/coverage", "Compétitions"],
    ],
  },
  {
    title: "Outils",
    links: [
      ["/backtests", "Backtest"],
      ["/models", "Modèles"],
      ["/config", "Configuration"],
    ],
  },
];

function itemClass(isActive: boolean) {
  return `rounded-xl px-3 py-2.5 text-sm font-medium focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-amber-400 ${
    isActive ? "bg-white text-ink" : "text-white hover:bg-white/10"
  }`;
}

export function Layout() {
  return (
    <div className="min-h-screen">
      <div className="bg-white px-4 py-2 text-center text-sm font-semibold text-ink">
        Les probabilités sont des estimations statistiques et ne garantissent aucun résultat.
      </div>
      <div className="mx-auto grid max-w-7xl gap-6 px-4 py-6 md:grid-cols-[200px_1fr_280px]">
        <aside className="md:sticky md:top-4 md:self-start">
          <div className="mb-3">
            <p className="text-lg font-semibold text-white">Sportwise AI</p>
            <p className="text-xs text-slate-400">Analyse · 60 jours de matchs</p>
          </div>
          <nav className="flex flex-col gap-5" aria-label="Navigation principale">
            {groups.map((group) => (
              <div key={group.title} className="flex flex-col gap-1">
                <p className="px-3 pb-1 text-xs font-semibold uppercase tracking-wide text-slate-500">{group.title}</p>
                {group.links.map(([to, label]) => (
                  <NavLink key={to} to={to} end={to === "/"} className={({ isActive }) => itemClass(isActive)}>
                    {label}
                  </NavLink>
                ))}
              </div>
            ))}
          </nav>
        </aside>
        <main className="min-w-0">
          <Outlet />
        </main>
        <SlipPanel />
      </div>
    </div>
  );
}
