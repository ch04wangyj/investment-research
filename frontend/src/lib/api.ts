export const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL || "http://127.0.0.1:8000";

export type ApiMeta = {
  source?: string;
  as_of?: string;
  stale?: boolean;
  error?: string | null;
};

export type Quote = {
  symbol?: string;
  name?: string;
  market?: string;
  currency?: string;
  close?: number | null;
  open?: number | null;
  high?: number | null;
  low?: number | null;
  volume?: number | null;
  change_pct?: number | null;
  _meta?: ApiMeta;
};

export type SymbolItem = {
  id: number;
  symbol: string;
  name: string;
  exchange: string;
  sector?: string;
  active: boolean;
};

export type Provider = {
  id: string;
  name: string;
  kind: string;
  base_url: string;
  api_key_env: string | null;
  quick_model: string;
  deep_model: string;
  thinking_supported: boolean;
  available: boolean;
};

export type AnalystView = {
  summary: string;
  score: number;
  evidence: string[];
  data_quality: "high" | "limited" | "missing";
};

export type ResearchReport = {
  run_id: string;
  symbol: string;
  market: "ashare" | "hk" | "us";
  company_name: string;
  generated_at: string;
  rating: "BUY" | "HOLD" | "SELL";
  confidence: "low" | "medium" | "high";
  current_price?: number | null;
  price_target_6m?: number | null;
  thesis: string;
  key_metrics: Record<string, unknown>;
  valuation: AnalystView;
  financial_quality: AnalystView;
  technical: AnalystView;
  sentiment: AnalystView;
  information_summary: {
    structured_facts: string[];
    unstructured_notes: string[];
    data_gaps: string[];
    source_count: number;
    summary: string;
  };
  trading_strategy?: {
    action: "accumulate" | "hold" | "reduce" | "avoid";
    horizon: "swing" | "position" | "long_term";
    entry_zone: string;
    stop_loss?: number | null;
    take_profit?: number | null;
    position_size_pct: number;
    rationale: string[];
    invalidation: string[];
  } | null;
  bull_case: string[];
  bear_case: string[];
  catalysts: string[];
  risks: string[];
  sources: { name: string; as_of?: string; stale: boolean; error?: string | null }[];
  llm_status: string;
  disclaimer: string;
};

export type HistoryPoint = {
  date: string;
  open?: number | null;
  high?: number | null;
  low?: number | null;
  close?: number | null;
  volume?: number | null;
};

export type SymbolProfile = {
  symbol: string;
  market: string;
  quote: { payload?: Quote[]; source?: string; as_of?: string; stale?: boolean; error?: string | null };
  fundamentals: { payload?: Record<string, unknown>; source?: string; as_of?: string; stale?: boolean; error?: string | null };
  history: { payload?: HistoryPoint[]; source?: string; as_of?: string; stale?: boolean; error?: string | null };
};

export type SectorSummary = {
  sector: string;
  count: number;
  avg_change_pct?: number | null;
  positive: number;
  negative: number;
  symbols: Array<{
    symbol: string;
    name: string;
    exchange: string;
    change_pct?: number | null;
  }>;
};

export type RatingSummary = {
  counts: Record<string, number>;
  buckets: Record<string, Array<{
    symbol: string;
    company_name?: string;
    rating: string;
    confidence: string;
    created_at?: string;
  }>>;
};

export async function apiGet<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`${response.status} ${response.statusText}`);
  }
  return response.json();
}

export async function apiPost<T>(path: string, body: unknown): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `${response.status} ${response.statusText}`);
  }
  return response.json();
}
