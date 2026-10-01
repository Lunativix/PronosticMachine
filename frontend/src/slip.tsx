import { createContext, useContext, useMemo, useState, type ReactNode } from "react";
import { CorrelationBadge, OddsDisplay, ProbabilityDisplay } from "./components/metrics";

export type SlipLeg = {
  matchId: number;
  match: string;
  selection: string;
  odds: number | null;
  probability: number | null;
};

type SlipApi = {
  legs: SlipLeg[];
  notice: string;
  has: (matchId: number, selection: string) => boolean;
  add: (leg: SlipLeg) => void;
  remove: (matchId: number, selection: string) => void;
};

const SlipContext = createContext<SlipApi | null>(null);

export function SlipProvider({ children }: { children: ReactNode }) {
  const [legs, setLegs] = useState<SlipLeg[]>([]);
  const [notice, setNotice] = useState("");
  const api = useMemo<SlipApi>(() => ({
    legs,
    notice,
    has(matchId, selection) {
      return legs.some((item) => item.matchId === matchId && item.selection === selection);
    },
    add(leg) {
      setLegs((current) => {
        if (current.some((item) => item.matchId === leg.matchId && item.selection === leg.selection)) {
          setNotice("Cette sélection est déjà dans le combiné.");
          return current;
        }
        const withoutMatch = current.filter((item) => item.matchId !== leg.matchId);
        if (withoutMatch.length >= 5) {
          setNotice("Combiné plein : 5 sélections maximum.");
          return current;
        }
        setNotice(current.some((item) => item.matchId === leg.matchId) ? "Sélection du match remplacée." : "Sélection ajoutée au combiné.");
        return [...withoutMatch, leg];
      });
    },
    remove(matchId, selection) {
      setNotice("");
      setLegs((current) => current.filter((item) => item.matchId !== matchId || item.selection !== selection));
    },
  }), [legs, notice]);
  return <SlipContext.Provider value={api}>{children}</SlipContext.Provider>;
}

export function useSlip(): SlipApi {
  const value = useContext(SlipContext);
  if (!value) throw new Error("SlipProvider manquant");
  return value;
}

export function SlipPanel() {
  const { legs, notice, remove } = useSlip();
  const sameMatch = new Set(legs.map((leg) => leg.matchId)).size < legs.length;
  const odds = legs.length > 0 && legs.every((leg) => leg.odds && leg.odds > 1)
    ? legs.reduce((product, leg) => product * (leg.odds ?? 1), 1)
    : null;
  const probability = legs.length > 0 && !sameMatch && legs.every((leg) => leg.probability != null)
    ? legs.reduce((product, leg) => product * (leg.probability ?? 1), 1)
    : null;
  return (
    <aside className="rounded-2xl border border-line bg-panel p-4 md:sticky md:top-4">
      <p className="text-xs font-semibold uppercase tracking-wide text-white">Combiné</p>
      <h2 className="text-xl font-semibold text-white">{legs.length} / 5</h2>
      {notice && <p className="mt-2 text-sm text-white">{notice}</p>}
      {legs.length === 0 && <p className="mt-3 text-sm text-foam/70">Aucune sélection. Utilise « Ajouter au combiné » sur un pronostic.</p>}
      <ol className="mt-3 space-y-2 text-sm text-foam">
        {legs.map((leg) => (
          <li key={`${leg.matchId}-${leg.selection}`} className="rounded-xl bg-ink px-3 py-2">
            <div className="flex items-start justify-between gap-3">
              <span>{leg.selection}</span>
              <OddsDisplay value={leg.odds} />
            </div>
            <p className="text-xs text-foam/60">{leg.match}</p>
            <button className="mt-1 text-xs font-semibold text-white underline" type="button" onClick={() => remove(leg.matchId, leg.selection)}>Retirer</button>
          </li>
        ))}
      </ol>
      <dl className="mt-4 grid grid-cols-2 gap-2 text-sm">
        <dt className="text-foam/60">Cote combinée</dt><dd className="text-right text-2xl font-semibold text-white"><OddsDisplay value={odds} /></dd>
        <dt className="text-foam/60">Probabilité</dt><dd className="text-right text-lg">{probability == null ? "—" : <ProbabilityDisplay value={probability} />}</dd>
        <dt className="text-foam/60">Corrélation</dt><dd className="text-right"><CorrelationBadge value={legs.length < 2 ? "—" : sameMatch ? "ÉLEVÉE" : "FAIBLE"} /></dd>
      </dl>
      {sameMatch && <p className="mt-2 text-xs text-amber-200">Même match : la probabilité n'est pas le produit des sélections.</p>}
    </aside>
  );
}
