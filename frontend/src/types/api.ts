export type Metrics = {
  bets?: number;
  profit?: number;
  yield?: number;
  roi?: number;
  max_drawdown?: number;
  win_rate?: number;
  final_bankroll?: number;
};

export type MatchItem = {
  id: number;
  kickoff: string;
  home_team: string;
  away_team: string;
  home_goals: number | null;
  away_goals: number | null;
  status: string;
  source: string;
};

export type Probability = { selection: string; raw: number; calibrated: number };

export type Prediction = {
  id: number;
  match_id: number;
  state: string;
  confidence: number | null;
  signal_quality: number | null;
  data_quality: number;
  probabilities_shrunk: boolean;
  explanation_method: string;
  explanation: {
    method?: string;
    factors?: { name: string; value: number; direction: string }[];
    poisson_contributions?: { name: string; value: number; target: string }[];
    ensemble_weights?: Record<string, number>;
    disclaimer?: string;
  };
  model_version: string | null;
  probabilities: Probability[];
};

export type Opportunity = {
  id: number;
  match: string;
  kickoff: string;
  market: string;
  selection: string;
  odds: number;
  model_probability: number;
  market_probability: number;
  edge: number;
  expected_value: number;
  signal_quality: number;
  state: string;
  label: string;
};

export type ModelRow = {
  id: number;
  model_key: string;
  version: string;
  training_date: string;
  dataset_hash: string;
  feature_version: string;
  metrics: Record<string, number | string>;
  is_active: boolean;
};

export type QualityReport = {
  id: number;
  source: string;
  records_total: number;
  records_valid: number;
  records_invalid: number;
  missing_values: number;
  duplicates: number;
  future_leakage: number;
  warnings: { code: string; message: string; row: number }[];
  errors: { code: string; message: string; row: number }[];
};
