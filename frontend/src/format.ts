export function unavailable(value: number | null | undefined): value is null | undefined {
  return value === null || value === undefined || Number.isNaN(value);
}

export function probability(value: number | null | undefined): string {
  if (unavailable(value)) return "—";
  return `${(value * 100).toFixed(1)} %`;
}

export function odds(value: number | null | undefined): string {
  if (unavailable(value)) return "—";
  return value.toFixed(2);
}

export function signedPercent(value: number | null | undefined): string {
  if (unavailable(value)) return "—";
  const points = value * 100;
  const sign = points > 0 ? "+" : "";
  return `${sign}${points.toFixed(1)} %`;
}

export function confidence(value: number | null | undefined): string {
  if (unavailable(value)) return "—";
  return `${Math.round(value)} / 100`;
}

export function quality(value: number | null | undefined): string {
  if (unavailable(value)) return "—";
  const score = value <= 1 ? value * 100 : value;
  return `${Math.round(score)} / 100`;
}

export function money(value: number | null | undefined): string {
  if (unavailable(value)) return "—";
  return `${value.toFixed(2)} €`;
}

export function tone(value: number | null | undefined): "positive" | "negative" | "neutral" | "warning" {
  if (unavailable(value)) return "neutral";
  if (value > 0) return "positive";
  if (value < 0) return "negative";
  return "neutral";
}

export function teamsFromMatch(match: string): { home: string; away: string } {
  const [home = "", away = ""] = match.split(" vs ");
  return { home, away };
}

export function outcomeLabel(selection: string, home?: string, away?: string): string {
  if (selection === "home") return home || "Domicile";
  if (selection === "away") return away || "Extérieur";
  if (selection === "draw") return "Nul";
  return selection;
}
