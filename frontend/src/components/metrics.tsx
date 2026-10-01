import type { ReactNode } from "react";
import { confidence, odds, probability, quality, signedPercent, tone, unavailable } from "../format";

const tones = {
  positive: "text-emerald-300",
  negative: "text-rose-300",
  warning: "text-amber-300",
  neutral: "text-slate-200",
};

export function ProbabilityDisplay({ value }: { value: number | null | undefined }) {
  return <span className="tabular-nums">{probability(value)}</span>;
}

export function OddsDisplay({ value }: { value: number | null | undefined }) {
  return <span className="tabular-nums">{odds(value)}</span>;
}

export function EdgeDisplay({ value }: { value: number | null | undefined }) {
  return <span className={`tabular-nums ${tones[tone(value)]}`}>{signedPercent(value)}</span>;
}

export function EVDisplay({ value }: { value: number | null | undefined }) {
  return <span className={`tabular-nums ${tones[tone(value)]}`}>{signedPercent(value)}</span>;
}

export function ConfidenceBadge({ value }: { value: number | null | undefined }) {
  return <span className="tabular-nums text-slate-100">{confidence(value)}</span>;
}

export function DataQualityBadge({ value }: { value: number | null | undefined }) {
  return <span className="tabular-nums text-slate-100">{quality(value)}</span>;
}

export function ConfidenceGauge({ value }: { value: number | null | undefined }) {
  const width = unavailable(value) ? 0 : Math.max(0, Math.min(100, Math.round(value ?? 0)));
  return (
    <div>
      <p className="text-3xl font-semibold tabular-nums text-white">{confidence(value)}</p>
      <div className="mt-2 h-2 rounded-full bg-slate-800">
        <div className="h-2 rounded-full bg-emerald-400" style={{ width: `${width}%` }} />
      </div>
    </div>
  );
}

export function ModelAgreementBadge({ value }: { value: number | null | undefined }) {
  return <span className="tabular-nums text-slate-200">{unavailable(value) ? "Donnée indisponible" : confidence(value)}</span>;
}

export function SignalCard({
  title,
  competition,
  when,
  probabilityValue,
  oddsValue,
  marketProbability,
  edge,
  ev,
  confidenceValue,
  qualityValue,
  agreement,
  signalLabel,
  onOpen,
  onAdd,
  added,
}: {
  title: string;
  competition: string;
  when: string;
  probabilityValue: number | null;
  oddsValue: number | null;
  marketProbability: number | null;
  edge: number | null;
  ev: number | null;
  confidenceValue: number | null;
  qualityValue: number | null;
  agreement: number | null;
  signalLabel: string;
  onOpen?: () => void;
  onAdd?: () => void;
  added?: boolean;
}) {
  return (
    <article className="rounded-2xl border border-slate-800 bg-slate-900 p-5">
      <p className="text-xs uppercase tracking-wide text-slate-400">{competition} · {when}</p>
      <h3 className="mt-2 text-3xl font-semibold text-white">{title}</h3>
      <p className="mt-1"><SignalBadge label={signalLabel} /></p>
      <dl className="mt-4 grid grid-cols-2 gap-x-6 gap-y-2 text-sm md:grid-cols-3">
        <div><dt className="text-slate-400">Probabilité</dt><dd className="text-xl"><ProbabilityDisplay value={probabilityValue} /></dd></div>
        <div><dt className="text-slate-400">Cote</dt><dd className="text-xl"><OddsDisplay value={oddsValue} /></dd></div>
        <div><dt className="text-slate-400">Marché</dt><dd className="text-xl"><ProbabilityDisplay value={marketProbability} /></dd></div>
        <div><dt className="text-slate-400">Edge</dt><dd className="text-xl"><EdgeDisplay value={edge} /></dd></div>
        <div><dt className="text-slate-400">EV</dt><dd className="text-xl"><EVDisplay value={ev} /></dd></div>
        <div><dt className="text-slate-400">Confiance</dt><dd className="text-xl"><ConfidenceBadge value={confidenceValue} /></dd></div>
        <div><dt className="text-slate-400">Qualité</dt><dd><DataQualityBadge value={qualityValue} /></dd></div>
        <div><dt className="text-slate-400">Accord modèles</dt><dd><ModelAgreementBadge value={agreement} /></dd></div>
      </dl>
      <div className="mt-4 flex gap-4">
        {onOpen && <button className="text-sm font-medium text-white underline" type="button" onClick={onOpen}>Voir l'analyse</button>}
        {onAdd && (
          <button className={`rounded-xl px-4 py-2 text-sm font-semibold ${added ? "border-2 border-white text-white" : "bg-white text-ink"}`} type="button" onClick={onAdd}>
            {added ? "Dans le combiné" : "Ajouter au combiné"}
          </button>
        )}
      </div>
    </article>
  );
}

export function SignalBadge({ label }: { label: string }) {
  const warning = label.toLowerCase().includes("insuff") || label.toLowerCase().includes("aucun");
  const strong = label.toLowerCase().includes("fort");
  const color = warning ? tones.negative : strong ? tones.positive : tones.warning;
  return <span className={color}>{label}</span>;
}

export function CorrelationBadge({ value }: { value: string | null | undefined }) {
  if (!value) return <span>—</span>;
  const color = value === "FAIBLE" || value === "LOW" ? tones.positive : value === "ÉLEVÉE" || value === "HIGH" ? tones.negative : tones.warning;
  return <span className={color}>{value}</span>;
}

export function MetricCard({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="rounded-2xl border border-slate-800 bg-slate-900 p-5">
      <p className="text-xs font-medium uppercase tracking-wide text-slate-400">{label}</p>
      <p className="mt-3 text-4xl font-semibold tabular-nums text-white">{value}</p>
    </div>
  );
}

export function MatchCard({
  competition,
  when,
  home,
  away,
  homeProbability,
  awayProbability,
  drawProbability,
  signal,
  onOpen,
}: {
  competition: string;
  when: string;
  home: string;
  away: string;
  homeProbability?: number | null;
  awayProbability?: number | null;
  drawProbability?: number | null;
  signal?: string;
  onOpen?: () => void;
}) {
  return (
    <article className="rounded-2xl border border-slate-800 bg-slate-900 p-4">
      <p className="text-xs uppercase tracking-wide text-slate-400">{competition}</p>
      <p className="text-sm text-slate-300">{when}</p>
      <div className="mt-3 grid grid-cols-[1fr_auto_1fr] items-end gap-3">
        <div>
          <p className="text-lg text-white">{home}</p>
          <p className="text-2xl font-semibold tabular-nums text-white"><ProbabilityDisplay value={homeProbability} /></p>
          <p className="text-xs text-slate-400">Victoire</p>
        </div>
        <div className="text-center text-sm text-slate-300">
          <p>Nul</p>
          <p className="font-semibold tabular-nums"><ProbabilityDisplay value={drawProbability} /></p>
        </div>
        <div className="text-right">
          <p className="text-lg text-white">{away}</p>
          <p className="text-2xl font-semibold tabular-nums text-white"><ProbabilityDisplay value={awayProbability} /></p>
          <p className="text-xs text-slate-400">Victoire</p>
        </div>
      </div>
      <p className="mt-3 text-sm text-slate-300">Signal : {signal ?? "Donnée indisponible"}</p>
      {onOpen && (
        <button className="mt-3 text-sm text-amber-300" onClick={onOpen} type="button">Voir analyse complète</button>
      )}
    </article>
  );
}

export function CombinationCard({
  title,
  legs,
  combinedOdds,
  probabilityValue,
  ev,
  confidenceValue,
  correlation,
  stance,
}: {
  title: string;
  legs: { label: string; odds: number | null }[];
  combinedOdds: number | null;
  probabilityValue: number | null;
  ev: number | null;
  confidenceValue: number | null;
  correlation: string;
  stance?: string;
}) {
  return (
    <article className="rounded-2xl border border-slate-800 bg-slate-900 p-4">
      <h3 className="text-lg text-white">{title}</h3>
      {stance && <p className="mt-1 inline-block rounded-full bg-white px-3 py-1 text-xs font-semibold text-ink">{stance}</p>}
      <p className="mt-2 text-sm text-slate-400">{legs.length} sélections</p>
      <ol className="mt-3 space-y-1 text-sm text-slate-200">
        {legs.map((leg, index) => (
          <li key={`${leg.label}-${index}`} className="flex justify-between gap-4">
            <span>{index + 1}. {leg.label}</span>
            <OddsDisplay value={leg.odds} />
          </li>
        ))}
      </ol>
      <dl className="mt-4 grid grid-cols-2 gap-2 text-sm">
        <dt className="text-slate-400">Cote combinée</dt><dd className="text-right"><OddsDisplay value={combinedOdds} /></dd>
        <dt className="text-slate-400">Probabilité estimée</dt><dd className="text-right"><ProbabilityDisplay value={probabilityValue} /></dd>
        <dt className="text-slate-400">EV</dt><dd className="text-right"><EVDisplay value={ev} /></dd>
        <dt className="text-slate-400">Confiance</dt><dd className="text-right"><ConfidenceBadge value={confidenceValue} /></dd>
        <dt className="text-slate-400">Corrélation</dt><dd className="text-right"><CorrelationBadge value={correlation} /></dd>
      </dl>
      <p className="mt-3 text-xs text-slate-400">Un EV positif avec une confiance faible reste spéculatif. La confiance n'est pas la probabilité de gain.</p>
    </article>
  );
}
