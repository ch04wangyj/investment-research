export const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL || "http://127.0.0.1:8000";

export type ApiMeta = {
  source?: string;
  as_of?: string;
  stale?: boolean;
  error?: string | null;
};

export type NewsSource = {
  id: string;
  name: string;
  region: "cn" | "global" | string;
  kind: "company" | "macro" | "search" | string;
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

export type EvidenceItem = {
  channel: "macro" | "filing" | "institutional_report" | "channel_analysis" | "news";
  title: string;
  summary: string;
  url: string;
  source: string;
  quality: "primary" | "institutional" | "media" | "search" | "unknown";
  query: string;
  as_of?: string | null;
  score: number;
};

export type ResearchEvidenceBook = {
  macro: EvidenceItem[];
  filings: EvidenceItem[];
  institutional_reports: EvidenceItem[];
  channel_analysis: EvidenceItem[];
  news: EvidenceItem[];
  errors: string[];
};

export type RiskAlert = {
  id: string;
  symbol: string;
  market: "ashare" | "hk" | "us";
  severity: "info" | "watch" | "warning" | "critical";
  category: "drawdown" | "policy_event" | "cycle_shift" | "earnings_season" | "data_quality";
  title: string;
  message: string;
  evidence: string[];
  source: string;
  triggered_at: string;
  action_hint: string;
};

export type RiskSummary = {
  total: number;
  symbols: number;
  by_severity: Record<string, number>;
  by_category: Record<string, number>;
  highest: string;
};

export type AuditFinding = {
  code: string;
  severity: "info" | "warning" | "critical";
  category: string;
  title: string;
  detail: string;
  remediation: string;
};

export type PublicationAudit = {
  status: "approved" | "conditional" | "blocked";
  score: number;
  generated_at: string;
  reviewer: string;
  findings: AuditFinding[];
  checks: string[];
  disclaimer: string;
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
  macro_context: AnalystView;
  technical: AnalystView;
  sentiment: AnalystView;
  information_summary: {
    structured_facts: string[];
    unstructured_notes: string[];
    data_gaps: string[];
    source_count: number;
    summary: string;
  };
  research_evidence: ResearchEvidenceBook;
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
  risk_alerts: RiskAlert[];
  pipeline_diagnostics: {
    topology: string;
    latency_strategy: string[];
    hallucination_controls: string[];
    validation_checks: string[];
    confidence_adjustments: string[];
  };
  institutional_narrative?: {
    executive_summary: string;
    company_analysis: string;
    macro_analysis: string;
    valuation_analysis: string;
    technical_analysis: string;
    catalyst_analysis: string;
    risk_analysis: string;
    evidence_notes: string;
  };
  publication_audit?: PublicationAudit | null;
  bull_case: string[];
  bear_case: string[];
  catalysts: string[];
  risks: string[];
  sources: {
    name: string;
    as_of?: string;
    stale: boolean;
    error?: string | null;
    url?: string | null;
    channel?: string | null;
    quality?: string | null;
  }[];
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

export type SymbolCompareItem = {
  symbol: string;
  market: "ashare" | "hk" | "us" | string;
  company_name: string;
  currency?: string | null;
  price?: number | null;
  change_pct?: number | null;
  volume?: number | null;
  market_cap?: number | null;
  pe_ratio?: number | null;
  pb_ratio?: number | null;
  roe?: number | null;
  roa?: number | null;
  revenue_growth?: number | null;
  rating?: string | null;
  confidence?: string | null;
  thesis?: string | null;
  latest_report_at?: string | null;
  data_sources: {
    quote?: string | null;
    fundamentals?: string | null;
    history?: string | null;
    report?: string | null;
  };
  stale: boolean;
  errors: string[];
};

export type SymbolComparison = {
  generated_at: string;
  period: string;
  symbols: string[];
  items: SymbolCompareItem[];
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

export type StrategyResearchItem = {
  title: string;
  summary: string;
  url: string;
  source: string;
  quality: string;
  query: string;
  score: number;
  as_of: string;
  method_tags: string[];
};

export type StrategyResearchSection = {
  id: string;
  title: string;
  description: string;
  items: StrategyResearchItem[];
};

export type StrategyResearch = {
  generated_at: string;
  principles: string[];
  sections: StrategyResearchSection[];
};

export type DailyReadItem = {
  title: string;
  summary: string;
  url: string;
  source: string;
  quality: string;
  query: string;
  score: number;
  as_of: string;
  tags: string[];
  reading_time_min: number;
  why_read: string;
};

export type DailyReadSection = {
  id: string;
  title: string;
  description: string;
  items: DailyReadItem[];
};

export type DailyReads = {
  generated_at: string;
  reading_protocol: string[];
  sections: DailyReadSection[];
};

export type WorkflowComparison = {
  framework: string;
  observed_pattern: string;
  adopted_improvement: string;
  risk_control: string;
};

export type WorkflowStage = {
  stage: string;
  goal: string;
  latency_strategy: string;
};

export type WorkflowBlueprint = {
  generated_at: string;
  positioning: string;
  comparisons: WorkflowComparison[];
  workflow: WorkflowStage[];
  next_actions: string[];
};

export type FixedIncomeSignal = {
  name: string;
  value?: number | null;
  unit: string;
  as_of: string;
};

export type FixedIncomeCurvePoint = {
  tenor: string;
  treasury_yield?: number | null;
  aaa_note_yield?: number | null;
  credit_spread_bp?: number | null;
  as_of: string;
};

export type FixedIncomeFrameworkSection = {
  id: string;
  title: string;
  question: string;
  signals: string[];
  agent: string;
  interpretation: string;
};

export type FixedIncomeAgent = {
  id: string;
  name: string;
  mission: string;
  output: string;
  guardrail: string;
};

export type FixedIncomeProfile = {
  id: string;
  title: string;
  risk_level: string;
  equity_cap_pct: number;
  drawdown_guardrail_pct: number;
  focus: string;
};

export type FixedIncomeProductCategory = {
  id: string;
  title: string;
  risk_level: string;
  liquidity: string;
  focus: string;
  warning: string;
};

export type FixedIncomeProduct = {
  id: string;
  code: string;
  name: string;
  category: string;
  category_title: string;
  risk_level: string;
  rank?: number | null;
  as_of?: string;
  nav?: number | null;
  daily_return_pct?: number | null;
  return_1m_pct?: number | null;
  return_6m_pct?: number | null;
  return_1y_pct?: number | null;
  ytd_return_pct?: number | null;
  income_per_10k?: number | null;
  annualized_7d_pct?: number | null;
  annualized_14d_pct?: number | null;
  fee?: string;
  source: string;
  note: string;
};

export type FixedIncomeOverview = {
  generated_at: string;
  positioning: string;
  reference: { title: string; local_reference: boolean; usage: string };
  framework_sections: FixedIncomeFrameworkSection[];
  agents: FixedIncomeAgent[];
  research_protocol: string[];
  allocation_profiles: FixedIncomeProfile[];
  product_categories: FixedIncomeProductCategory[];
  market_snapshot: {
    yield_curve: FixedIncomeCurvePoint[];
    curve_signals: FixedIncomeSignal[];
    liquidity: FixedIncomeSignal[];
    source_status: ApiMeta[];
  };
  products: FixedIncomeProduct[];
  disclaimer: string;
};

export type ResearchSkillPack = {
  id: string;
  version: string;
  title: string;
  description: string;
  agent_roles: string[];
  guardrails: string[];
  status: string;
};

export type IntelligenceDocument = {
  id: string;
  kind: string;
  category: string;
  title: string;
  summary: string;
  url: string;
  source: string;
  quality: string;
  tags: string[];
  as_of: string;
  collected_at: string;
  content_hash: string;
  relevance: number;
};

export type ResearchIntelligence = {
  generated_at: string;
  positioning: string;
  stats: {
    total_documents: number;
    categories: Record<string, number>;
    qualities: Record<string, number>;
    latest_refresh?: {
      completed_at: string;
      status: string;
      document_count: number;
      error?: string | null;
    } | null;
  };
  skills: ResearchSkillPack[];
  documents: IntelligenceDocument[];
  auto_refresh: {
    enabled: boolean;
    scheduled: boolean;
    interval_hours: number;
  };
  learning_protocol: string[];
};

export type WorkflowStageResult = {
  stage: string;
  status: "pending" | "running" | "completed" | "failed" | "blocked" | "skipped";
  error?: string | null;
};

export type ResearchJob = {
  job_id: string;
  symbol: string;
  status: "queued" | "running" | "completed" | "failed";
  workflow?: {
    stages?: Record<string, WorkflowStageResult>;
    audit_status?: string | null;
  } | null;
  result?: {
    report: ResearchReport;
    audit: PublicationAudit;
    workflow: unknown;
  } | null;
  error?: string | null;
};

type ApiOptions = {
  timeoutMs?: number;
};

async function fetchWithTimeout(url: string, init: RequestInit = {}, timeoutMs = 12000) {
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetch(url, { ...init, signal: controller.signal });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      throw new Error(`请求超时（${Math.round(timeoutMs / 1000)}s）`);
    }
    throw error;
  } finally {
    window.clearTimeout(timer);
  }
}

export async function apiGet<T>(path: string, options: ApiOptions = {}): Promise<T> {
  const response = await fetchWithTimeout(`${API_BASE}${path}`, { cache: "no-store" }, options.timeoutMs);
  if (!response.ok) {
    throw new Error(`${response.status} ${response.statusText}`);
  }
  return response.json();
}

export async function apiDelete<T>(path: string, options: ApiOptions = {}): Promise<T> {
  const response = await fetchWithTimeout(`${API_BASE}${path}`, {
    method: "DELETE",
  }, options.timeoutMs);
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `${response.status} ${response.statusText}`);
  }
  return response.json();
}

export async function apiPost<T>(path: string, body: unknown, options: ApiOptions = {}): Promise<T> {
  const response = await fetchWithTimeout(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  }, options.timeoutMs);
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `${response.status} ${response.statusText}`);
  }
  return response.json();
}
