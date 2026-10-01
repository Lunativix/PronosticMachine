async function get<T>(path: string): Promise<T> {
  const response = await fetch(path);
  if (!response.ok) {
    throw new Error(await response.text());
  }
  return response.json() as Promise<T>;
}

export const api = {
  performance: () => get<Record<string, unknown>>("/analytics/performance"),
  matches: () => get<{ items: import("../types/api").MatchItem[] }>("/matches"),
  prediction: (id: number) => get<import("../types/api").Prediction>(`/matches/${id}/prediction`),
  value: (id: number) => get<{ items: import("../types/api").Opportunity[] }>(`/matches/${id}/value`),
  opportunities: (query = "") => get<{ items: import("../types/api").Opportunity[] }>(`/opportunities${query}`),
  backtests: () => get<{ items: { id: number; name: string; metrics: Record<string, number>; staking: string }[] }>("/backtests"),
  backtest: (id: number) =>
    get<{ metrics: Record<string, number>; bankroll: { as_of: string; bankroll: number; drawdown: number }[]; results: { pnl: number }[] }>(
      `/backtests/${id}`,
    ),
  models: () => get<{ items: import("../types/api").ModelRow[] }>("/models"),
  quality: () => get<{ items: import("../types/api").QualityReport[] }>("/quality"),
};
