"use client";

import { useEffect, useMemo, useState, type CSSProperties, type ReactNode } from "react";
import {
  Activity,
  AlertCircle,
  Bell,
  Bot,
  Brain,
  BookOpen,
  CalendarClock,
  ChevronDown,
  ChevronUp,
  CheckCircle2,
  ClipboardList,
  Database,
  Download,
  ExternalLink,
  FileText,
  FolderOpen,
  Gauge,
  Layers3,
  Languages,
  Loader2,
  MessageSquareText,
  Newspaper,
  RefreshCw,
  Search,
  Settings2,
  ShieldAlert,
  ShieldCheck,
  Sparkles,
  Trash2,
  Zap,
} from "lucide-react";

import { PriceChart } from "@/components/price-chart";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  apiDelete,
  apiGet,
  apiPost,
  API_BASE,
  type DailyReads,
  type Provider,
  type EvidenceItem,
  type Quote,
  type RatingSummary,
  type ResearchReport,
  type RiskAlert,
  type RiskSummary,
  type SectorSummary,
  type StrategyResearch,
  type SymbolComparison,
  type SymbolCompareItem,
  type SymbolItem,
  type SymbolProfile,
  type WorkflowBlueprint,
} from "@/lib/api";

type Lang = "zh" | "en";

type Health = {
  status: string;
  version: string;
  providers: Record<string, string[]>;
  database: string;
};

type Overview = {
  indices: Array<Record<string, unknown>>;
  news: Array<Record<string, unknown>>;
  watchlist: SymbolItem[];
  quotes: Quote[];
  sectors?: SectorSummary[];
  ratings?: RatingSummary;
};

type RiskResponse = {
  symbol?: string;
  market?: string;
  alerts: RiskAlert[];
  summary: RiskSummary;
};

type NewsResponse = {
  symbol?: string | null;
  items: Array<Record<string, unknown>>;
};

type RunSummary = {
  id: number;
  run_id: string;
  ticker: string;
  created_at: string;
  rating?: string;
  confidence?: string;
  company_name?: string;
};

const defaultOverview: Overview = {
  indices: [],
  news: [],
  watchlist: [],
  quotes: [],
};

const defaultRiskSummary: RiskSummary = {
  total: 0,
  symbols: 0,
  by_severity: { critical: 0, warning: 0, watch: 0, info: 0 },
  by_category: {},
  highest: "info",
};

export function Workbench() {
  const [health, setHealth] = useState<Health | null>(null);
  const [providers, setProviders] = useState<Provider[]>([]);
  const [overview, setOverview] = useState<Overview>(defaultOverview);
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [symbol, setSymbol] = useState("AAPL");
  const [compareInput, setCompareInput] = useState("AAPL, MSFT, 600519, 00700");
  const [period, setPeriod] = useState("6mo");
  const [providerId, setProviderId] = useState("deepseek");
  const [useLlm, setUseLlm] = useState(true);
  const [stockSearch, setStockSearch] = useState("");
  const [sectorFilter, setSectorFilter] = useState("all");
  const [ratingFilter, setRatingFilter] = useState("all");
  const [lang, setLang] = useState<Lang>("zh");
  const [assistantMessages, setAssistantMessages] = useState<string[]>([]);
  const [riskAlerts, setRiskAlerts] = useState<RiskAlert[]>([]);
  const [riskSummary, setRiskSummary] = useState<RiskSummary>(defaultRiskSummary);
  const [strategyResearch, setStrategyResearch] = useState<StrategyResearch | null>(null);
  const [dailyReads, setDailyReads] = useState<DailyReads | null>(null);
  const [workflowBlueprint, setWorkflowBlueprint] = useState<WorkflowBlueprint | null>(null);
  const [comparison, setComparison] = useState<SymbolComparison | null>(null);
  const [report, setReport] = useState<ResearchReport | null>(null);
  const [profile, setProfile] = useState<SymbolProfile | null>(null);
  const [showSettings, setShowSettings] = useState(false);
  const [loading, setLoading] = useState(true);
  const [analyzing, setAnalyzing] = useState(false);
  const [comparing, setComparing] = useState(false);
  const [assistantLoading, setAssistantLoading] = useState(false);
  const [riskLoading, setRiskLoading] = useState(false);
  const [deletingReportIds, setDeletingReportIds] = useState<number[]>([]);
  const [selectedReportIds, setSelectedReportIds] = useState<number[]>([]);
  const [error, setError] = useState<string | null>(null);

  async function refresh() {
    setLoading(true);
    setError(null);
    const [healthResult, modelResult, symbolsResult, runsResult] = await Promise.allSettled([
      apiGet<Health>("/api/health"),
      apiGet<{ providers: Provider[] }>("/api/models"),
      apiGet<{ symbols: SymbolItem[] }>("/api/symbols"),
      apiGet<{ runs: RunSummary[] }>("/api/research/runs"),
    ]);

    if (healthResult.status === "fulfilled") setHealth(healthResult.value);
    if (modelResult.status === "fulfilled") setProviders(modelResult.value.providers);
    if (symbolsResult.status === "fulfilled") {
      setOverview((current) => ({ ...current, watchlist: symbolsResult.value.symbols }));
    }
    if (runsResult.status === "fulfilled") setRuns(runsResult.value.runs);

    const rejected = [healthResult, modelResult, symbolsResult, runsResult].find(
      (item) => item.status === "rejected",
    );
    if (rejected?.status === "rejected") {
      setError(`API 未完全可用：${rejected.reason instanceof Error ? rejected.reason.message : String(rejected.reason)}`);
    }
    setLoading(false);

    apiGet<NewsResponse>("/api/news?limit=40")
      .then((response) => setOverview((current) => ({ ...current, news: response.items })))
      .catch(() => undefined);
    apiGet<StrategyResearch>("/api/strategy/research?limit=6")
      .then(setStrategyResearch)
      .catch(() => undefined);
    apiGet<DailyReads>("/api/research/daily-reads?limit=5")
      .then(setDailyReads)
      .catch(() => undefined);
    apiGet<WorkflowBlueprint>("/api/workflow/blueprint")
      .then(setWorkflowBlueprint)
      .catch(() => undefined);
    apiGet<Overview>("/api/market/overview")
      .then((next) => setOverview((current) => ({ ...next, news: current.news.length ? current.news : next.news })))
      .catch((err) => {
        setError(`市场概览加载较慢或失败：${err instanceof Error ? err.message : String(err)}`);
      });
    void refreshRisk();
  }

  async function refreshRisk(targetSymbol?: string) {
    const clean = targetSymbol?.trim().toUpperCase();
    setRiskLoading(true);
    try {
      const response = clean
        ? await apiGet<RiskResponse>(`/api/risk/alerts/${clean}?period=${period}`)
        : await apiGet<RiskResponse>("/api/risk/alerts?limit=12");
      setRiskAlerts(response.alerts);
      setRiskSummary(response.summary);
    } catch (err) {
      setError(`风险提醒加载失败：${err instanceof Error ? err.message : String(err)}`);
    } finally {
      setRiskLoading(false);
    }
  }

  useEffect(() => {
    const timer = window.setTimeout(() => {
      void refresh();
    }, 0);
    return () => window.clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function runResearch(targetSymbol?: string) {
    const clean = (targetSymbol || symbol).trim().toUpperCase();
    if (!clean) return;
    setSymbol(clean);
    setAnalyzing(true);
    setError(null);
    try {
      const [researchResponse, profileResponse] = await Promise.all([
        apiPost<{ report: ResearchReport }>(`/api/research/${clean}`, {
          provider_id: providerId,
          use_llm: useLlm,
          period,
          language: lang,
        }),
        apiGet<SymbolProfile>(`/api/symbols/${clean}?period=${period}`).catch(() => null),
      ]);
      setReport(researchResponse.report);
      setRiskAlerts(researchResponse.report.risk_alerts || []);
      setRiskSummary(buildRiskSummary(researchResponse.report.risk_alerts || []));
      setProfile(profileResponse);
      const latestRuns = await apiGet<{ runs: RunSummary[] }>("/api/research/runs").catch(() => null);
      if (latestRuns) setRuns(latestRuns.runs);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setAnalyzing(false);
    }
  }

  async function selectSymbol(nextSymbol: string, loadProfile = true) {
    const clean = nextSymbol.trim().toUpperCase();
    setSymbol(clean);
    setReport(null);
    setAssistantMessages([]);
    if (!loadProfile) return;
    const [nextProfile] = await Promise.all([
      apiGet<SymbolProfile>(`/api/symbols/${clean}?period=${period}`).catch(() => null),
      refreshRisk(clean),
    ]);
    setProfile(nextProfile);
  }

  async function runAssistant(question = "") {
    const clean = symbol.trim().toUpperCase();
    if (!clean) return;
    setAssistantLoading(true);
    setError(null);
    try {
      const response = await apiPost<{ messages: string[]; report: ResearchReport }>(`/api/assistant/${clean}`, {
        provider_id: providerId,
        use_llm: useLlm,
        period,
        question,
        language: lang,
      });
      setAssistantMessages(response.messages);
      if (response.report) {
        setReport(response.report);
        setRiskAlerts(response.report.risk_alerts || []);
        setRiskSummary(buildRiskSummary(response.report.risk_alerts || []));
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setAssistantLoading(false);
    }
  }

  async function runComparison() {
    const symbols = parseSymbolInput(compareInput);
    if (symbols.length < 2) {
      setError(tx(lang, "至少输入两只股票才能对比。", "Enter at least two symbols to compare."));
      return;
    }
    setComparing(true);
    setError(null);
    try {
      const response = await apiGet<SymbolComparison>(
        `/api/symbols/compare?symbols=${encodeURIComponent(symbols.join(","))}&period=${encodeURIComponent(period)}`,
      );
      setComparison(response);
    } catch (err) {
      setError(`股票对比失败：${err instanceof Error ? err.message : String(err)}`);
    } finally {
      setComparing(false);
    }
  }

  function appendCompareSymbol(nextSymbol: string) {
    const current = parseSymbolInput(compareInput);
    const normalized = nextSymbol.trim().toUpperCase();
    if (!normalized || current.includes(normalized)) return;
    setCompareInput([...current, normalized].slice(0, 10).join(", "));
  }

  async function deleteReport(reportId: number) {
    const target = runs.find((run) => run.id === reportId);
    const confirmed = window.confirm(
      tx(
        lang,
        `删除 ${target?.ticker || ""} 的这份历史报告？该操作只影响本地数据库。`,
        `Delete this ${target?.ticker || ""} report from local history?`,
      ),
    );
    if (!confirmed) return;
    setDeletingReportIds([reportId]);
    setError(null);
    try {
      await apiDelete<{ status: string; id: number }>(`/api/research/runs/${reportId}`);
      setRuns((current) => current.filter((run) => run.id !== reportId));
      setSelectedReportIds((current) => current.filter((id) => id !== reportId));
      if (target?.run_id && report?.run_id === target.run_id) {
        setReport(null);
      }
    } catch (err) {
      setError(`报告删除失败：${err instanceof Error ? err.message : String(err)}`);
    } finally {
      setDeletingReportIds([]);
    }
  }

  async function deleteSelectedReports() {
    const ids = selectedReportIds.filter((id) => runs.some((run) => run.id === id));
    if (!ids.length) return;
    const confirmed = window.confirm(
      tx(
        lang,
        `批量删除 ${ids.length} 份历史报告？本地数据库会少一点回忆。`,
        `Delete ${ids.length} selected reports from local history?`,
      ),
    );
    if (!confirmed) return;
    const selectedRuns = runs.filter((run) => ids.includes(run.id));
    setDeletingReportIds(ids);
    setError(null);
    try {
      const response = await apiPost<{ status: string; requested: number; deleted: number; ids: number[] }>(
        "/api/research/runs/delete",
        { ids },
      );
      setRuns((current) => current.filter((run) => !ids.includes(run.id)));
      setSelectedReportIds([]);
      if (report && selectedRuns.some((run) => run.run_id === report.run_id)) {
        setReport(null);
      }
      if (response.deleted !== ids.length) {
        setError(tx(lang, `已删除 ${response.deleted}/${ids.length} 份报告，部分记录可能已不存在。`, `Deleted ${response.deleted}/${ids.length}; some records may already be gone.`));
      }
    } catch (err) {
      setError(`批量删除失败：${err instanceof Error ? err.message : String(err)}`);
    } finally {
      setDeletingReportIds([]);
    }
  }

  function toggleReportSelection(reportId: number) {
    setSelectedReportIds((current) => (
      current.includes(reportId)
        ? current.filter((id) => id !== reportId)
        : [...current, reportId]
    ));
  }

  function toggleAllReports(checked: boolean) {
    setSelectedReportIds(checked ? runs.map((run) => run.id) : []);
  }

  const providerCount = useMemo(
    () => health ? Object.values(health.providers).flat().length : 0,
    [health],
  );
  const activeRiskCount = useMemo(
    () => riskAlerts.filter((item) => item.severity !== "info").length,
    [riskAlerts],
  );
  const latestRatingBySymbol = useMemo(() => {
    const map = new Map<string, string>();
    for (const run of runs) {
      if (!map.has(run.ticker)) map.set(run.ticker, run.rating || "HOLD");
    }
    return map;
  }, [runs]);
  const sectors = useMemo(
    () => Array.from(new Set(overview.watchlist.map((item) => item.sector || "未分类"))),
    [overview.watchlist],
  );
  const filteredSymbols = useMemo(() => {
    const query = stockSearch.trim().toUpperCase();
    return overview.watchlist.filter((item) => {
      const rating = latestRatingBySymbol.get(item.symbol) || "未评级";
      const matchesQuery = !query || item.symbol.includes(query) || item.name.toUpperCase().includes(query);
      const matchesSector = sectorFilter === "all" || (item.sector || "未分类") === sectorFilter;
      const matchesRating = ratingFilter === "all" || rating === ratingFilter || (ratingFilter === "未评级" && rating === "未评级");
      return matchesQuery && matchesSector && matchesRating;
    });
  }, [overview.watchlist, stockSearch, sectorFilter, ratingFilter, latestRatingBySymbol]);

  return (
    <main className="relative min-h-screen overflow-hidden text-zinc-950">
      <ParticleField />
      <div className="relative z-10 mx-auto flex w-full max-w-7xl flex-col gap-6 px-4 py-5 sm:px-6 lg:px-8">
        <header className="shell-surface relative overflow-hidden rounded-lg border border-white/80 px-5 py-5 backdrop-blur md:flex md:items-center md:justify-between">
          <div className="absolute inset-x-0 top-0 h-1 bg-[linear-gradient(90deg,#14b8a6,#3b82f6,#f59e0b,#ec4899)]" />
          <div>
            <div className="inline-flex items-center gap-2 rounded-md border border-teal-100 bg-teal-50/80 px-2.5 py-1 text-xs font-medium uppercase tracking-[0.14em] text-teal-800">
              <Sparkles className="h-3.5 w-3.5" />
              {tx(lang, "Evidence-first AI Research Workbench", "Evidence-first AI Research Workbench")}
            </div>
            <h1 className="mt-2 text-2xl font-semibold tracking-tight text-zinc-950 md:text-3xl">
              {tx(lang, "AI 深度研报工作台", "AI Research Workbench")}
            </h1>
            <p className="mt-2 max-w-2xl text-sm leading-6 text-zinc-600">
              {tx(
                lang,
                "先快速收集宏观、公告/年报、公开研报线索、新闻与渠道观点，再生成可追溯的机构风格研报。",
                "Rapidly collect macro context, filings, public report leads, news, and market views before producing an auditable institutional-style report.",
              )}
            </p>
          </div>
          <div className="mt-4 flex flex-wrap items-center justify-start gap-2 md:mt-0 md:justify-end">
            <Badge variant={health?.status === "ok" ? "default" : "secondary"} className="h-8 rounded-md border border-emerald-200 bg-emerald-50 px-3 text-emerald-800">
              {health?.status === "ok" ? "API Online" : "API Pending"}
            </Badge>
            <Button variant="outline" size="sm" onClick={() => setLang((value) => (value === "zh" ? "en" : "zh"))}>
              <Languages className="mr-2 h-4 w-4" />
              {lang === "zh" ? "EN" : "中"}
            </Button>
            <Button variant="outline" size="sm" onClick={refresh} disabled={loading}>
              <RefreshCw className="mr-2 h-4 w-4" />
              {tx(lang, "刷新", "Refresh")}
            </Button>
            <Button
              variant="outline"
              size="icon"
              aria-label="打开配置"
              onClick={() => setShowSettings((value) => !value)}
            >
              <Settings2 className="h-4 w-4" />
            </Button>
          </div>
        </header>

        {error ? (
          <Alert className="border-amber-200 bg-amber-50">
            <AlertCircle className="h-4 w-4" />
            <AlertTitle>运行提示</AlertTitle>
            <AlertDescription>
              {error}。{tx(lang, "确认后端已启动", "Confirm the backend is running")}：
              <code className="rounded bg-white px-1 py-0.5">python scripts/run_api.py</code>
            </AlertDescription>
          </Alert>
        ) : null}

        <section className="grid items-stretch gap-4 md:grid-cols-5">
          <MetricCard icon={<Gauge />} label={tx(lang, "跟踪股票", "Tracked Symbols")} value={overview.watchlist.length} tone="teal" />
          <MetricCard icon={<Database />} label={tx(lang, "数据路由", "Data Routes")} value={providerCount} tone="blue" />
          <MetricCard icon={<FileText />} label={tx(lang, "研报记录", "Research Runs")} value={runs.length} tone="amber" />
          <MetricCard icon={<ShieldAlert />} label={tx(lang, "风险提醒", "Risk Alerts")} value={activeRiskCount} tone="rose" />
          <MetricCard icon={<Activity />} label={tx(lang, "API版本", "API Version")} value={health?.version || "0.2.0"} tone="violet" />
        </section>

        <GuideStrip lang={lang} />

        <Tabs defaultValue="research" className="space-y-5">
          <TabsList className="mx-auto grid h-auto w-full grid-cols-2 rounded-lg p-1 md:w-[1120px] md:grid-cols-7">
            <TabsTrigger value="research">{tx(lang, "研报工作台", "Research")}</TabsTrigger>
            <TabsTrigger value="evidence">{tx(lang, "资料目录", "Evidence")}</TabsTrigger>
            <TabsTrigger value="strategy">{tx(lang, "策略方法", "Methods")}</TabsTrigger>
            <TabsTrigger value="compare">{tx(lang, "股票对比", "Compare")}</TabsTrigger>
            <TabsTrigger value="universe">{tx(lang, "股票池", "Universe")}</TabsTrigger>
            <TabsTrigger value="risk">{tx(lang, "风险提醒", "Risk")}</TabsTrigger>
            <TabsTrigger value="reports">{tx(lang, "报告历史", "Reports")}</TabsTrigger>
          </TabsList>

          <TabsContent value="research" className="space-y-5">
            <ResearchTab
              symbol={symbol}
              setSymbol={setSymbol}
              period={period}
              setPeriod={setPeriod}
              providers={providers}
              providerId={providerId}
              setProviderId={setProviderId}
              useLlm={useLlm}
              setUseLlm={setUseLlm}
              analyzing={analyzing}
              runResearch={runResearch}
              runAssistant={runAssistant}
              assistantLoading={assistantLoading}
              assistantMessages={assistantMessages}
              report={report}
              profile={profile}
              lang={lang}
            />
          </TabsContent>

          <TabsContent value="evidence" className="space-y-5">
            <EvidenceLibraryTab report={report} overview={overview} dailyReads={dailyReads} lang={lang} />
          </TabsContent>

          <TabsContent value="strategy" className="space-y-5">
            <StrategyResearchTab
              research={strategyResearch}
              blueprint={workflowBlueprint}
              lang={lang}
              onRefresh={refresh}
              loading={loading}
            />
          </TabsContent>

          <TabsContent value="compare" className="space-y-5">
            <StockCompareTab
              input={compareInput}
              setInput={setCompareInput}
              period={period}
              setPeriod={setPeriod}
              comparison={comparison}
              loading={comparing}
              watchlist={overview.watchlist}
              onCompare={runComparison}
              onAppend={appendCompareSymbol}
              onSelect={(next) => void selectSymbol(next)}
              onAnalyze={(next) => void runResearch(next)}
              lang={lang}
            />
          </TabsContent>

          <TabsContent value="universe" className="space-y-5">
            <StockUniverseTab
              symbols={filteredSymbols}
              sectors={sectors}
              stockSearch={stockSearch}
              setStockSearch={setStockSearch}
              sectorFilter={sectorFilter}
              setSectorFilter={setSectorFilter}
              ratingFilter={ratingFilter}
              setRatingFilter={setRatingFilter}
              ratingBySymbol={latestRatingBySymbol}
              quotes={overview.quotes}
              onSelect={(item) => void selectSymbol(item.symbol)}
              onAnalyze={(item) => {
                void runResearch(item.symbol);
              }}
              lang={lang}
            />
          </TabsContent>

          <TabsContent value="risk" className="space-y-5">
            <RiskCenterTab
              symbol={symbol}
              watchlist={overview.watchlist}
              alerts={riskAlerts}
              summary={riskSummary}
              loading={riskLoading}
              report={report}
              onSelect={(next) => void selectSymbol(next)}
              onRefresh={(next) => void refreshRisk(next)}
              onRefreshAll={() => void refreshRisk()}
              lang={lang}
            />
          </TabsContent>

          <TabsContent value="reports">
            <ReportsTab
              runs={runs}
              lang={lang}
              selectedIds={selectedReportIds}
              deletingIds={deletingReportIds}
              onToggle={toggleReportSelection}
              onToggleAll={toggleAllReports}
              onDelete={deleteReport}
              onDeleteSelected={deleteSelectedReports}
            />
          </TabsContent>
        </Tabs>

        {showSettings ? <SettingsTab health={health} providers={providers} lang={lang} /> : null}
      </div>
    </main>
  );
}

function ParticleField() {
  const particles = [
    ["8%", "12%", "3px", "#14b8a6", "36px", "24px", "7s", "-1s"],
    ["18%", "34%", "2px", "#3b82f6", "-28px", "34px", "8s", "-3s"],
    ["31%", "16%", "4px", "#f59e0b", "22px", "-22px", "9s", "-2s"],
    ["48%", "28%", "2px", "#ec4899", "-30px", "-18px", "7.5s", "-4s"],
    ["63%", "10%", "3px", "#22c55e", "18px", "30px", "8.4s", "-2.6s"],
    ["78%", "24%", "2px", "#6366f1", "-24px", "26px", "9.2s", "-5s"],
    ["88%", "14%", "3px", "#0ea5e9", "20px", "-28px", "7.8s", "-1.8s"],
    ["10%", "58%", "2px", "#f97316", "34px", "-18px", "10s", "-4.5s"],
    ["38%", "52%", "3px", "#06b6d4", "-18px", "28px", "8.8s", "-3.8s"],
    ["70%", "58%", "2px", "#84cc16", "30px", "12px", "9.6s", "-6s"],
  ] as const;
  const lines = [
    ["9%", "22%", "180px", "#14b8a6", "8s", "-2s"],
    ["42%", "18%", "220px", "#3b82f6", "9s", "-4s"],
    ["66%", "38%", "170px", "#f59e0b", "7s", "-1s"],
    ["18%", "68%", "210px", "#ec4899", "10s", "-5s"],
  ] as const;

  return (
    <div className="particle-field" aria-hidden="true">
      {particles.map(([left, top, size, color, x, y, duration, delay], index) => (
        <span
          key={`particle-${index}`}
          className="particle-dot"
          style={{
            left,
            top,
            "--particle-size": size,
            "--particle-color": color,
            "--particle-x": x,
            "--particle-y": y,
            "--particle-duration": duration,
            "--particle-delay": delay,
          } as CSSProperties}
        />
      ))}
      {lines.map(([left, top, width, color, duration, delay], index) => (
        <span
          key={`line-${index}`}
          className="particle-line"
          style={{
            left,
            top,
            "--line-width": width,
            "--line-color": color,
            "--line-duration": duration,
            "--line-delay": delay,
          } as CSSProperties}
        />
      ))}
    </div>
  );
}

function GuideStrip({ lang }: { lang: Lang }) {
  const lines = [
    tx(lang, "先喂材料，再问观点；别让模型空腹写研报。", "Feed the evidence first; never ask a model to write hungry."),
    tx(lang, "市场先生今天心情未知，我们先查账本。", "Mr. Market has moods. We check the ledger first."),
    tx(lang, "观点可以幽默，证据必须严肃。", "The tone can smile; the evidence cannot bluff."),
  ];
  return (
    <section className="grid gap-3 rounded-lg border border-white/80 bg-white/70 p-3 shadow-[0_12px_32px_rgba(15,23,42,0.06)] backdrop-blur md:grid-cols-3">
      {lines.map((line, index) => (
        <div key={line} className="flex min-h-16 items-center gap-3 rounded-lg border bg-white/72 px-4 py-3">
          <span className={[
            "flex h-7 w-7 shrink-0 items-center justify-center rounded-md text-xs font-semibold",
            index === 0 ? "bg-teal-50 text-teal-700" : index === 1 ? "bg-amber-50 text-amber-700" : "bg-sky-50 text-sky-700",
          ].join(" ")}
          >
            {index + 1}
          </span>
          <p className="text-sm leading-5 text-zinc-700">{line}</p>
        </div>
      ))}
    </section>
  );
}

function MetricCard({
  icon,
  label,
  value,
  tone,
}: {
  icon: ReactNode;
  label: string;
  value: string | number;
  tone: "teal" | "blue" | "amber" | "rose" | "violet";
}) {
  const tones = {
    teal: "from-teal-50 to-white text-teal-700 border-teal-100",
    blue: "from-sky-50 to-white text-sky-700 border-sky-100",
    amber: "from-amber-50 to-white text-amber-700 border-amber-100",
    rose: "from-rose-50 to-white text-rose-700 border-rose-100",
    violet: "from-violet-50 to-white text-violet-700 border-violet-100",
  }[tone];
  return (
    <Card className="h-full rounded-lg border-white/80 bg-white/84 shadow-[0_12px_34px_rgba(15,23,42,0.06)]">
      <CardContent className="flex items-center justify-between p-5">
        <div>
          <p className="text-xs font-medium uppercase tracking-[0.12em] text-zinc-500">{label}</p>
          <p className="mt-2 text-2xl font-semibold tracking-tight">{value}</p>
        </div>
        <div className={`rounded-lg border bg-gradient-to-br p-2 ${tones} [&_svg]:h-5 [&_svg]:w-5`}>{icon}</div>
      </CardContent>
    </Card>
  );
}

function NewsDirectory({ items, lang }: { items: Array<Record<string, unknown>>; lang: Lang }) {
  const [expanded, setExpanded] = useState<string | null>(null);
  const [filter, setFilter] = useState("all");
  const filtered = items.filter((item) => filter === "all" || newsCategory(item) === filter);
  const filters = [
    ["all", tx(lang, "全部", "All")],
    ["policy", tx(lang, "政策", "Policy")],
    ["earnings", tx(lang, "财报", "Earnings")],
    ["macro", tx(lang, "宏观", "Macro")],
    ["market", tx(lang, "市场", "Market")],
  ];

  if (!items.length) {
    return (
      <div className="rounded-lg border border-dashed border-sky-200 bg-sky-50/60 p-6 text-sm leading-6 text-sky-800">
        {tx(lang, "新闻流还没开张。先喝口水，下一次刷新可能就有市场小作文。", "The news feed has not opened shop yet. Hydrate first; the next refresh may bring market essays.")}
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-2">
        {filters.map(([value, label]) => (
          <Button
            key={value}
            size="sm"
            variant={filter === value ? "default" : "outline"}
            onClick={() => setFilter(value)}
          >
            {label}
          </Button>
        ))}
      </div>
      <div className="space-y-2">
        {filtered.slice(0, 14).map((item, index) => {
          const id = `${String(item.title || "news")}-${index}`;
          const open = expanded === id;
          return (
            <div key={id} className="rounded-lg border bg-zinc-50">
              <button
                onClick={() => setExpanded(open ? null : id)}
                className="flex w-full items-start justify-between gap-3 px-3 py-3 text-left"
              >
                <span>
                  <span className="line-clamp-2 text-sm font-medium text-zinc-950">{String(item.title || "Untitled")}</span>
                  <span className="mt-1 block text-xs text-zinc-500">
                    {riskCategoryLabel(newsCategory(item), lang)} · {String(item.source_channel || item.source || "news")} · {String(item.display_time || "")}
                  </span>
                </span>
                {open ? <ChevronUp className="mt-1 h-4 w-4 shrink-0 text-zinc-500" /> : <ChevronDown className="mt-1 h-4 w-4 shrink-0 text-zinc-500" />}
              </button>
              {open ? (
                <div className="border-t px-3 py-3 text-sm leading-6 text-zinc-700">
                  <p>{String(item.summary || tx(lang, "无摘要", "No summary"))}</p>
                  <div className="mt-3 flex items-center justify-between gap-3">
                    <Badge variant="secondary" className="rounded-md">{String(item.source || "news")}</Badge>
                    {item.url ? (
                      <a
                        href={String(item.url)}
                        target="_blank"
                        rel="noreferrer"
                        className="text-xs font-medium text-blue-600 hover:text-blue-700"
                      >
                        {tx(lang, "打开原文", "Open source")}
                      </a>
                    ) : null}
                  </div>
                </div>
              ) : null}
            </div>
          );
        })}
      </div>
    </div>
  );
}

function EvidenceLibraryTab({
  report,
  overview,
  dailyReads,
  lang,
}: {
  report: ResearchReport | null;
  overview: Overview;
  dailyReads: DailyReads | null;
  lang: Lang;
}) {
  const evidence = report?.research_evidence;
  return (
    <section className="space-y-5">
      <div className="grid items-start gap-5 lg:grid-cols-[1.15fr_0.85fr]">
        <Card className="h-full rounded-lg border-white/80 bg-white shadow-sm">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <FolderOpen className="h-4 w-4" />
              {report ? `${report.symbol} ${tx(lang, "公开资料目录", "Evidence Book")}` : tx(lang, "公开资料目录", "Evidence Book")}
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-5">
            {report ? (
              <>
                <EvidenceGroup title={tx(lang, "公告 / 年报 / 监管披露", "Filings / Annual Reports / Disclosures")} items={evidence?.filings || []} lang={lang} />
                <EvidenceGroup title={tx(lang, "公开机构研报线索", "Public Institutional Report Leads")} items={evidence?.institutional_reports || []} lang={lang} />
                <EvidenceGroup title={tx(lang, "宏观与政策背景", "Macro And Policy Context")} items={evidence?.macro || []} lang={lang} />
                <EvidenceGroup title={tx(lang, "渠道观点与新闻共识", "Channel Views And News")} items={[...(evidence?.channel_analysis || []), ...(evidence?.news || [])]} lang={lang} />
                {evidence?.errors?.length ? <InfoList title={tx(lang, "检索问题", "Search Issues")} items={evidence.errors} tone="warning" lang={lang} /> : null}
              </>
            ) : (
              <div className="rounded-lg border border-dashed bg-zinc-50 p-6 text-sm leading-6 text-zinc-500">
                {tx(
                  lang,
                  "先在研报工作台生成一份报告，这里会展开公告/年报、公开研报线索、宏观政策和渠道分析目录。",
                  "Generate a report first. Filings, public research leads, macro context, and channel analysis will appear here.",
                )}
              </div>
            )}
          </CardContent>
        </Card>

        <Card className="h-full rounded-lg border-white/80 bg-white shadow-sm">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <Newspaper className="h-4 w-4" />
              {tx(lang, "新闻与政策目录", "News And Policy Directory")}
            </CardTitle>
          </CardHeader>
          <CardContent>
            <NewsDirectory items={overview.news} lang={lang} />
          </CardContent>
        </Card>
      </div>

      <DailyReadsPanel reads={dailyReads} lang={lang} />
    </section>
  );
}

function DailyReadsPanel({ reads, lang }: { reads: DailyReads | null; lang: Lang }) {
  return (
    <Card className="rounded-lg border-white/80 bg-white shadow-sm">
      <CardHeader>
        <CardTitle className="flex flex-wrap items-center justify-between gap-3 text-base">
          <span className="flex items-center gap-2">
            <BookOpen className="h-4 w-4" />
            {tx(lang, "每日优质研报阅读", "Daily Research Reading")}
          </span>
          <span className="text-xs font-normal text-zinc-500">
            {reads?.generated_at ? new Date(reads.generated_at).toLocaleString() : tx(lang, "加载中", "Loading")}
          </span>
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-5">
        <div className="grid gap-2 md:grid-cols-4">
          {(reads?.reading_protocol || [
            tx(lang, "先读宏观策略，再读行业/公司，最后回到公告原文。", "Read macro first, then sector/company, then primary filings."),
          ]).map((item, index) => (
            <div key={`${index}-${item}`} className="rounded-lg border bg-zinc-50 px-3 py-2 text-xs leading-5 text-zinc-600">
              {item}
            </div>
          ))}
        </div>

        <div className="grid gap-4 lg:grid-cols-3">
          {(reads?.sections || []).map((section) => (
            <div key={section.id} className="rounded-lg border bg-zinc-50 p-3">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <p className="text-sm font-semibold text-zinc-950">{dailySectionTitle(section.id, section.title, lang)}</p>
                  <p className="mt-1 text-xs leading-5 text-zinc-500">{dailySectionDescription(section.id, section.description, lang)}</p>
                </div>
                <Badge variant="secondary" className="rounded-md">{section.items.length}</Badge>
              </div>
              <div className="mt-3 space-y-2">
                {section.items.map((item) => (
                  <a
                    key={`${section.id}-${item.url}-${item.title}`}
                    href={item.url || "#"}
                    target="_blank"
                    rel="noreferrer"
                    className="group block rounded-md border bg-white px-3 py-2 transition hover:border-zinc-400"
                  >
                    <div className="flex items-start justify-between gap-2">
                      <span className="line-clamp-2 text-sm font-medium leading-5 text-zinc-900">{item.title || "Untitled"}</span>
                      <ExternalLink className="mt-1 h-3.5 w-3.5 shrink-0 text-zinc-400 group-hover:text-zinc-800" />
                    </div>
                    <p className="mt-2 line-clamp-2 text-xs leading-5 text-zinc-600">{item.summary || item.why_read}</p>
                    <div className="mt-2 flex flex-wrap items-center gap-2">
                      <Badge variant="secondary" className="rounded-md">{sourceQualityLabel(item.quality, lang)}</Badge>
                      <span className="text-xs text-zinc-500">{item.source || "-"}</span>
                      <span className="text-xs text-zinc-400">{item.reading_time_min} min</span>
                    </div>
                  </a>
                ))}
                {!section.items.length ? (
                  <div className="rounded-md border border-dashed bg-white px-3 py-4 text-xs text-zinc-500">
                    {tx(lang, "暂无阅读材料，搜索源可能暂不可用。", "No reading material yet; search sources may be unavailable.")}
                  </div>
                ) : null}
              </div>
            </div>
          ))}
          {!reads?.sections?.length ? (
            <div className="rounded-lg border border-dashed bg-zinc-50 p-6 text-sm text-zinc-500 lg:col-span-3">
              {tx(lang, "每日阅读清单正在加载。", "Daily reading list is loading.")}
            </div>
          ) : null}
        </div>
      </CardContent>
    </Card>
  );
}

function EvidenceGroup({ title, items, lang }: { title: string; items: EvidenceItem[]; lang: Lang }) {
  return (
    <div className="rounded-lg border bg-zinc-50 p-3">
      <div className="flex items-center justify-between gap-3">
        <p className="text-xs font-medium uppercase tracking-[0.12em] text-zinc-500">{title}</p>
        <Badge variant="secondary" className="rounded-md">{items.length}</Badge>
      </div>
      <div className="mt-3 space-y-2">
        {(items.length ? items : []).slice(0, 6).map((item) => (
          <a
            key={`${item.channel}-${item.url}-${item.title}`}
            href={item.url || "#"}
            target="_blank"
            rel="noreferrer"
            className="block rounded-md border bg-white px-3 py-2 text-sm leading-5 text-zinc-800 hover:border-zinc-400"
          >
            <span className="line-clamp-2 font-medium">{item.title || "Untitled source"}</span>
            <span className="mt-1 block text-xs text-zinc-500">
              {sourceQualityLabel(item.quality, lang)} · {item.source || "source"} · score {Math.round(item.score)}
            </span>
            {item.summary ? <span className="mt-2 line-clamp-2 block text-xs leading-5 text-zinc-600">{item.summary}</span> : null}
          </a>
        ))}
        {!items.length ? (
          <p className="rounded-md bg-white px-3 py-2 text-xs leading-5 text-zinc-500">
            {tx(lang, "暂无可用来源。研究员已把自信心音量调小。", "No available source. Confidence volume has been turned down.")}
          </p>
        ) : null}
      </div>
    </div>
  );
}

function StrategyResearchTab({
  research,
  blueprint,
  lang,
  onRefresh,
  loading,
}: {
  research: StrategyResearch | null;
  blueprint: WorkflowBlueprint | null;
  lang: Lang;
  onRefresh: () => void;
  loading: boolean;
}) {
  return (
    <section className="grid items-start gap-5 lg:grid-cols-[0.7fr_1.3fr]">
      <Card className="h-full rounded-lg border-white/80 bg-white shadow-sm">
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <BookOpen className="h-4 w-4" />
            {tx(lang, "价值投资 / 策略方法库", "Value Investing / Strategy Library")}
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <p className="text-sm leading-6 text-zinc-600">
            {tx(
              lang,
              "该模块只沉淀方法、前沿论文和市场观点，不直接给出买卖点。个股研报仍优先关注宏观、公司基本面、估值和证据链。",
              "This module stores methods, frontier papers, and market views rather than direct trading signals. Stock reports still prioritize macro context, fundamentals, valuation, and auditable evidence.",
            )}
          </p>
          <Button variant="outline" size="sm" onClick={onRefresh} disabled={loading}>
            {loading ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <RefreshCw className="mr-2 h-4 w-4" />}
            {tx(lang, "刷新方法库", "Refresh Library")}
          </Button>
          <div className="space-y-2">
            {(research?.principles || [
              tx(lang, "先理解商业模式、资本回报和估值区间，再考虑交易策略。", "Understand business quality, returns on capital, and valuation before strategy."),
              tx(lang, "前沿论文必须经过样本外稳健性和交易成本审查。", "Frontier papers need out-of-sample robustness and cost checks."),
            ]).map((item) => (
              <Bullet key={item} tone="positive" text={item} />
            ))}
          </div>
          <p className="text-xs text-zinc-500">
            {tx(lang, "更新时间", "Updated at")}: {research?.generated_at ? new Date(research.generated_at).toLocaleString() : "-"}
          </p>
        </CardContent>
      </Card>

      <div className="grid gap-5">
        <WorkflowBlueprintPanel blueprint={blueprint} lang={lang} />
        {(research?.sections || []).map((section) => (
          <Card key={section.id} className="rounded-lg border-white/80 bg-white shadow-sm">
            <CardHeader>
              <CardTitle className="flex flex-wrap items-center justify-between gap-2 text-base">
                <span>{strategySectionTitle(section.id, section.title, lang)}</span>
                <Badge variant="secondary" className="rounded-md">{section.items.length}</Badge>
              </CardTitle>
              <p className="text-sm leading-6 text-zinc-500">{strategySectionDescription(section.id, section.description, lang)}</p>
            </CardHeader>
            <CardContent className="grid gap-3 md:grid-cols-2">
              {section.items.length ? section.items.map((item) => (
                <a
                  key={`${section.id}-${item.url}-${item.title}`}
                  href={item.url || "#"}
                  target="_blank"
                  rel="noreferrer"
                  className="group flex min-h-36 flex-col rounded-lg border bg-zinc-50 p-4 transition hover:border-zinc-400 hover:bg-white"
                >
                  <div className="flex items-start justify-between gap-3">
                    <p className="line-clamp-2 text-sm font-semibold leading-5 text-zinc-950">{item.title || "Untitled"}</p>
                    <ExternalLink className="mt-0.5 h-3.5 w-3.5 shrink-0 text-zinc-400 group-hover:text-zinc-800" />
                  </div>
                  <p className="mt-2 line-clamp-3 text-xs leading-5 text-zinc-600">{item.summary || tx(lang, "暂无摘要", "No summary")}</p>
                  <div className="mt-auto flex flex-wrap items-center gap-2 pt-3">
                    <Badge variant="secondary" className="rounded-md">{sourceQualityLabel(item.quality, lang)}</Badge>
                    <span className="text-xs text-zinc-500">{item.source}</span>
                    {item.method_tags.slice(0, 2).map((tag) => (
                      <span key={tag} className="rounded-md bg-white px-2 py-1 text-[11px] text-zinc-500">{tag}</span>
                    ))}
                  </div>
                </a>
              )) : (
                <div className="rounded-lg border border-dashed bg-zinc-50 p-6 text-sm text-zinc-500">
                  {tx(lang, "暂未检索到策略资料。", "No strategy material collected yet.")}
                </div>
              )}
            </CardContent>
          </Card>
        ))}
        {!research?.sections?.length ? (
          <Card className="rounded-lg border-white/80 bg-white shadow-sm">
            <CardContent className="p-6 text-sm text-zinc-500">
              {tx(lang, "策略方法库正在加载，或搜索服务暂不可用。", "Strategy library is loading or the search service is unavailable.")}
            </CardContent>
          </Card>
        ) : null}
      </div>
    </section>
  );
}

function WorkflowBlueprintPanel({ blueprint, lang }: { blueprint: WorkflowBlueprint | null; lang: Lang }) {
  return (
    <Card className="rounded-lg border-white/80 bg-white shadow-sm">
      <CardHeader>
        <CardTitle className="flex flex-wrap items-center justify-between gap-3 text-base">
          <span className="flex items-center gap-2">
            <Brain className="h-4 w-4" />
            {tx(lang, "主流 FinAgent 工作流对比", "FinAgent Workflow Benchmark")}
          </span>
          <Badge variant="secondary" className="rounded-md">
            {blueprint?.comparisons?.length || 0} frameworks
          </Badge>
        </CardTitle>
        <p className="text-sm leading-6 text-zinc-500">
          {blueprint?.positioning || tx(
            lang,
            "当前工作台优先做好快速信息收集、证据校验和专业研报形成；交易策略作为独立模块后置。",
            "The workbench prioritizes fast evidence collection, validation, and institutional research; strategy remains a separated later module.",
          )}
        </p>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid gap-3 lg:grid-cols-3">
          {(blueprint?.comparisons || []).map((item) => (
            <div key={item.framework} className="rounded-lg border bg-zinc-50 p-3">
              <div className="flex items-center justify-between gap-2">
                <p className="font-semibold text-zinc-950">{item.framework}</p>
                <Badge variant="outline" className="rounded-md">{tx(lang, "已吸收", "Adopted")}</Badge>
              </div>
              <p className="mt-2 line-clamp-3 text-xs leading-5 text-zinc-600">{item.observed_pattern}</p>
              <p className="mt-3 text-xs font-medium text-zinc-900">{tx(lang, "本项目改进", "Local Upgrade")}</p>
              <p className="mt-1 text-xs leading-5 text-zinc-600">{item.adopted_improvement}</p>
              <p className="mt-3 text-xs font-medium text-zinc-900">{tx(lang, "防幻觉机制", "Anti-Hallucination")}</p>
              <p className="mt-1 text-xs leading-5 text-zinc-600">{item.risk_control}</p>
            </div>
          ))}
          {!blueprint?.comparisons?.length ? (
            <div className="rounded-lg border border-dashed bg-zinc-50 p-6 text-sm text-zinc-500 lg:col-span-3">
              {tx(lang, "工作流对比正在加载。", "Workflow benchmark is loading.")}
            </div>
          ) : null}
        </div>

        {blueprint?.workflow?.length ? (
          <div className="rounded-lg border bg-zinc-50 p-3">
            <p className="text-xs font-medium uppercase tracking-[0.12em] text-zinc-500">
              {tx(lang, "改进后的研报链路", "Improved Research Flow")}
            </p>
            <div className="mt-3 grid gap-3 md:grid-cols-2">
              {blueprint.workflow.map((stage) => (
                <div key={stage.stage} className="rounded-md bg-white p-3">
                  <p className="text-sm font-semibold text-zinc-950">{stage.stage}</p>
                  <p className="mt-1 text-xs leading-5 text-zinc-600">{stage.goal}</p>
                  <p className="mt-2 text-xs leading-5 text-zinc-500">{stage.latency_strategy}</p>
                </div>
              ))}
            </div>
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}

function StockCompareTab(props: {
  input: string;
  setInput: (value: string) => void;
  period: string;
  setPeriod: (value: string) => void;
  comparison: SymbolComparison | null;
  loading: boolean;
  watchlist: SymbolItem[];
  onCompare: () => void;
  onAppend: (symbol: string) => void;
  onSelect: (symbol: string) => void;
  onAnalyze: (symbol: string) => void;
  lang: Lang;
}) {
  const items = props.comparison?.items || [];
  const insights = comparisonInsights(items, props.lang);
  return (
    <section className="grid items-start gap-5 lg:grid-cols-[minmax(320px,0.74fr)_minmax(0,1.26fr)]">
      <Card className="min-w-0 rounded-lg border-white/80 bg-white/86 shadow-sm">
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <Layers3 className="h-4 w-4" />
            {tx(props.lang, "多股对比台", "Multi-Symbol Compare")}
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div>
            <p className="text-xs font-medium uppercase tracking-[0.12em] text-zinc-500">
              {tx(props.lang, "股票代码", "Symbols")}
            </p>
            <textarea
              value={props.input}
              onChange={(event) => props.setInput(event.target.value)}
              className="mt-2 min-h-24 w-full resize-none rounded-lg border border-slate-200 bg-white/80 px-3 py-2 text-sm leading-6 outline-none transition focus:border-teal-500 focus:ring-3 focus:ring-teal-500/15"
              placeholder="AAPL, MSFT, 600519, 00700"
            />
            <p className="mt-2 text-xs leading-5 text-zinc-500">
              {tx(props.lang, "最多对比 10 只；逗号、分号、换行都可以。", "Compare up to 10 symbols; commas, semicolons, and new lines all work.")}
            </p>
          </div>
          <div className="grid grid-cols-[1fr_auto] items-center gap-3">
            <Select value={props.period} onValueChange={props.setPeriod}>
              <SelectTrigger className="h-10 w-full border-slate-200 bg-white/80"><SelectValue placeholder="Period" /></SelectTrigger>
              <SelectContent>
                {["1mo", "3mo", "6mo", "1y", "2y"].map((item) => <SelectItem key={item} value={item}>{item}</SelectItem>)}
              </SelectContent>
            </Select>
            <Button onClick={props.onCompare} disabled={props.loading} className="h-10 bg-[#0f766e] hover:bg-[#115e59]">
              {props.loading ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Activity className="mr-2 h-4 w-4" />}
              {tx(props.lang, "开始对比", "Compare")}
            </Button>
          </div>
          <div>
            <p className="text-xs font-medium uppercase tracking-[0.12em] text-zinc-500">
              {tx(props.lang, "快速加入", "Quick Add")}
            </p>
            <div className="mt-2 flex flex-wrap gap-2">
              {props.watchlist.slice(0, 12).map((item) => (
                <Button
                  key={item.symbol}
                  size="sm"
                  variant="outline"
                  onClick={() => props.onAppend(item.symbol)}
                >
                  {item.symbol}
                </Button>
              ))}
            </div>
          </div>
          <div className="rounded-lg border border-amber-100 bg-amber-50/70 px-3 py-2 text-xs leading-5 text-amber-800">
            {tx(
              props.lang,
              "横向对比不是选美：低估值、好质量、强催化剂要一起看。",
              "Comparison is not a beauty contest: valuation, quality, and catalysts need to sit together.",
            )}
          </div>
        </CardContent>
      </Card>

      <div className="min-w-0 space-y-5">
        <Card className="rounded-lg border-white/80 bg-white/86 shadow-sm">
          <CardHeader>
            <CardTitle className="flex flex-wrap items-center justify-between gap-3 text-base">
              <span>{tx(props.lang, "对比摘要", "Comparison Snapshot")}</span>
              <Badge variant="secondary" className="rounded-md">
                {props.comparison?.generated_at ? new Date(props.comparison.generated_at).toLocaleString() : tx(props.lang, "未运行", "Not run")}
              </Badge>
            </CardTitle>
          </CardHeader>
          <CardContent className="grid gap-3 md:grid-cols-3">
            {insights.map((item) => (
              <div key={item.label} className={`rounded-lg border px-4 py-3 ${item.className}`}>
                <p className="text-xs font-medium uppercase tracking-[0.12em] opacity-75">{item.label}</p>
                <p className="mt-2 text-lg font-semibold">{item.value}</p>
                <p className="mt-1 text-xs leading-5 opacity-80">{item.note}</p>
              </div>
            ))}
          </CardContent>
        </Card>

        <Card className="rounded-lg border-white/80 bg-white/86 shadow-sm">
          <CardHeader>
            <CardTitle className="flex flex-wrap items-center justify-between gap-3 text-base">
              <span>{tx(props.lang, "横向数据表", "Comparison Table")}</span>
              <Badge variant="secondary" className="rounded-md">{items.length}</Badge>
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="overflow-x-auto">
              <Table className="min-w-[1120px]">
                <TableHeader>
                  <TableRow>
                    <TableHead>Symbol</TableHead>
                    <TableHead>{tx(props.lang, "公司", "Company")}</TableHead>
                    <TableHead>{tx(props.lang, "市场", "Market")}</TableHead>
                    <TableHead>{tx(props.lang, "价格", "Price")}</TableHead>
                    <TableHead>{tx(props.lang, "涨跌", "Change")}</TableHead>
                    <TableHead>PE</TableHead>
                    <TableHead>PB</TableHead>
                    <TableHead>ROE</TableHead>
                    <TableHead>{tx(props.lang, "市值", "Mkt Cap")}</TableHead>
                    <TableHead>{tx(props.lang, "评级", "Rating")}</TableHead>
                    <TableHead>{tx(props.lang, "来源", "Source")}</TableHead>
                    <TableHead className="text-right">{tx(props.lang, "操作", "Action")}</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {items.map((item) => (
                    <TableRow key={item.symbol}>
                      <TableCell className="font-mono font-medium">{item.symbol}</TableCell>
                      <TableCell className="max-w-48 truncate">{item.company_name || "-"}</TableCell>
                      <TableCell>{marketLabel(item.market, props.lang)}</TableCell>
                      <TableCell>{formatNumber(item.price)}</TableCell>
                      <TableCell><Pct value={item.change_pct} /></TableCell>
                      <TableCell>{formatNumber(item.pe_ratio)}</TableCell>
                      <TableCell>{formatNumber(item.pb_ratio)}</TableCell>
                      <TableCell>{formatPercent(item.roe)}</TableCell>
                      <TableCell>{formatNumber(item.market_cap)}</TableCell>
                      <TableCell>{item.rating ? <RatingBadge rating={item.rating} /> : <span className="text-zinc-500">-</span>}</TableCell>
                      <TableCell className="max-w-44 truncate text-xs text-zinc-500">
                        {item.data_sources.quote || item.data_sources.fundamentals || "-"}
                        {item.stale ? ` · ${tx(props.lang, "缓存", "stale")}` : ""}
                      </TableCell>
                      <TableCell className="text-right">
                        <div className="flex justify-end gap-2">
                          <Button size="sm" variant="outline" onClick={() => props.onSelect(item.symbol)}>
                            {tx(props.lang, "查看", "Open")}
                          </Button>
                          <Button size="sm" variant="secondary" onClick={() => props.onAnalyze(item.symbol)}>
                            {tx(props.lang, "研报", "Report")}
                          </Button>
                        </div>
                      </TableCell>
                    </TableRow>
                  ))}
                  {!items.length ? (
                    <TableRow>
                      <TableCell colSpan={12} className="h-32 text-center text-sm text-zinc-500">
                        {tx(props.lang, "输入多只股票后运行对比。横向表还没开席。", "Enter multiple symbols and run comparison. The table is waiting for guests.")}
                      </TableCell>
                    </TableRow>
                  ) : null}
                </TableBody>
              </Table>
            </div>
          </CardContent>
        </Card>
      </div>
    </section>
  );
}

function StockUniverseTab(props: {
  symbols: SymbolItem[];
  sectors: string[];
  stockSearch: string;
  setStockSearch: (value: string) => void;
  sectorFilter: string;
  setSectorFilter: (value: string) => void;
  ratingFilter: string;
  setRatingFilter: (value: string) => void;
  ratingBySymbol: Map<string, string>;
  quotes: Quote[];
  onSelect: (item: SymbolItem) => void;
  onAnalyze: (item: SymbolItem) => void;
  lang: Lang;
}) {
  const quoteMap = new Map(props.quotes.map((quote) => [quote.symbol || "", quote]));
  return (
    <section className="grid items-start gap-5 lg:grid-cols-[0.76fr_1.24fr]">
      <Card className="h-full rounded-lg border-white/80 bg-white shadow-sm">
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <Layers3 className="h-4 w-4" />
            {tx(props.lang, "股票池筛选", "Universe Filters")}
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="relative">
            <Search className="absolute left-3 top-2.5 h-4 w-4 text-zinc-400" />
            <Input
              className="pl-9"
              value={props.stockSearch}
              onChange={(event) => props.setStockSearch(event.target.value)}
              placeholder={tx(props.lang, "搜索代码 / 公司名", "Search ticker / company")}
            />
          </div>
          <Select value={props.sectorFilter} onValueChange={props.setSectorFilter}>
            <SelectTrigger><SelectValue placeholder="板块" /></SelectTrigger>
            <SelectContent>
              <SelectItem value="all">{tx(props.lang, "全部板块", "All Sectors")}</SelectItem>
              {props.sectors.map((sector) => <SelectItem key={sector} value={sector}>{sector}</SelectItem>)}
            </SelectContent>
          </Select>
          <Select value={props.ratingFilter} onValueChange={props.setRatingFilter}>
            <SelectTrigger><SelectValue placeholder="评级" /></SelectTrigger>
            <SelectContent>
              {["all", "BUY", "HOLD", "SELL", "未评级"].map((rating) => (
                <SelectItem key={rating} value={rating}>{rating === "all" ? tx(props.lang, "全部评级", "All Ratings") : rating}</SelectItem>
              ))}
            </SelectContent>
          </Select>
          <div className="grid grid-cols-2 gap-2 pt-2">
            {props.sectors.slice(0, 8).map((sector) => (
              <button
                key={sector}
                onClick={() => props.setSectorFilter(sector)}
                className="rounded-lg border bg-zinc-50 px-3 py-2 text-left text-xs font-medium text-zinc-700 hover:bg-white"
              >
                {sector}
              </button>
            ))}
          </div>
        </CardContent>
      </Card>

      <Card className="h-full rounded-lg border-white/80 bg-white shadow-sm">
        <CardHeader>
          <CardTitle className="flex items-center justify-between text-base">
            <span>{tx(props.lang, "可选股票列表", "Selectable Symbols")}</span>
            <Badge variant="secondary" className="rounded-md">{props.symbols.length}</Badge>
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
            {props.symbols.map((item) => {
              const quote = quoteMap.get(item.symbol);
              const rating = props.ratingBySymbol.get(item.symbol) || "未评级";
              return (
                <div
                  key={item.symbol}
                  onClick={() => props.onSelect(item)}
                  role="button"
                  tabIndex={0}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" || event.key === " ") props.onSelect(item);
                  }}
                  className="rounded-lg border bg-white p-4 text-left shadow-sm transition hover:-translate-y-0.5 hover:border-zinc-400 hover:shadow-md"
                >
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <p className="font-mono text-sm font-semibold">{item.symbol}</p>
                      <p className="mt-1 line-clamp-1 text-sm text-zinc-700">{item.name}</p>
                    </div>
                    <RatingBadge rating={rating === "未评级" ? "HOLD" : rating} />
                  </div>
                  <div className="mt-4 grid grid-cols-2 gap-2 text-xs">
                    <MiniMetric label={tx(props.lang, "板块", "Sector")} value={item.sector || tx(props.lang, "未分类", "Unclassified")} />
                    <MiniMetric label={tx(props.lang, "价格", "Price")} value={formatNumber(quote?.close)} />
                  </div>
                  <div className="mt-3 flex items-center justify-between">
                    <Pct value={quote?.change_pct} />
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={(event) => {
                        event.stopPropagation();
                        props.onAnalyze(item);
                      }}
                    >
                      {tx(props.lang, "Agent分析", "Agent Analyze")}
                    </Button>
                  </div>
                </div>
              );
            })}
          </div>
        </CardContent>
      </Card>
    </section>
  );
}

function ResearchTab(props: {
  symbol: string;
  setSymbol: (value: string) => void;
  period: string;
  setPeriod: (value: string) => void;
  providers: Provider[];
  providerId: string;
  setProviderId: (value: string) => void;
  useLlm: boolean;
  setUseLlm: (value: boolean) => void;
  analyzing: boolean;
  runResearch: () => void;
  runAssistant: () => void;
  assistantLoading: boolean;
  assistantMessages: string[];
  report: ResearchReport | null;
  profile: SymbolProfile | null;
  lang: Lang;
}) {
  const history = props.profile?.history.payload || [];

  return (
    <>
      <Card className="rounded-lg border-white/80 bg-white/84 shadow-[0_14px_38px_rgba(15,23,42,0.07)]">
        <CardContent className="grid items-center gap-3 p-4 md:grid-cols-[1.1fr_0.7fr_1fr_auto_auto]">
          <div className="relative">
            <Search className="absolute left-3 top-3 h-4 w-4 text-zinc-400" />
            <Input
              className="h-10 border-slate-200 bg-white/80 pl-9 shadow-inner shadow-slate-950/[0.02]"
              value={props.symbol}
              onChange={(event) => props.setSymbol(event.target.value)}
              placeholder="AAPL / 600519 / 00700"
            />
          </div>
          <Select value={props.period} onValueChange={props.setPeriod}>
            <SelectTrigger className="h-10 w-full border-slate-200 bg-white/80"><SelectValue placeholder="Period" /></SelectTrigger>
            <SelectContent>
              {["1mo", "3mo", "6mo", "1y", "2y"].map((item) => <SelectItem key={item} value={item}>{item}</SelectItem>)}
            </SelectContent>
          </Select>
          <Select value={props.providerId} onValueChange={props.setProviderId}>
            <SelectTrigger className="h-10 w-full border-slate-200 bg-white/80"><SelectValue placeholder={tx(props.lang, "LLM 服务", "LLM Provider")} /></SelectTrigger>
            <SelectContent>
              {props.providers.map((provider) => (
                <SelectItem key={provider.id} value={provider.id}>{provider.name}</SelectItem>
              ))}
            </SelectContent>
          </Select>
          <label className="flex h-10 items-center justify-center gap-2 rounded-lg border border-slate-200 bg-white/80 px-3 text-sm text-zinc-700">
            <input
              type="checkbox"
              checked={props.useLlm}
              onChange={(event) => props.setUseLlm(event.target.checked)}
              className="h-4 w-4 accent-teal-700"
            />
            {tx(props.lang, "LLM润色", "LLM Polish")}
          </label>
          <Button
            onClick={() => props.runResearch()}
            disabled={props.analyzing}
            className="h-10 min-w-32 bg-[#0f766e] text-white shadow-[0_12px_28px_rgba(15,118,110,0.2)] hover:bg-[#115e59]"
          >
            {props.analyzing ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Brain className="mr-2 h-4 w-4" />}
            {tx(props.lang, "生成研报", "Generate")}
          </Button>
        </CardContent>
      </Card>

      <section className="grid items-stretch gap-5 lg:grid-cols-[0.92fr_1.08fr]">
        <div className="grid gap-5">
          <ReportSummary report={props.report} lang={props.lang} />
          <EvidenceCoverage report={props.report} lang={props.lang} />
        </div>

        <Card className="h-full rounded-lg border-white/80 bg-white shadow-sm">
          <CardHeader>
            <CardTitle className="text-base">{tx(props.lang, "价格背景与数据质量", "Price Context And Data Quality")}</CardTitle>
          </CardHeader>
          <CardContent>
            <PriceChart data={history} />
            <p className="mt-3 text-xs text-zinc-500">
              {tx(
                props.lang,
                "价格图仅作为背景信息，当前阶段暂不输出技术交易策略。",
                "The chart is context only; technical trading strategy is deferred in this phase.",
              )} Source: {props.profile?.history.source || "-"} · stale: {String(props.profile?.history.stale || false)}
            </p>
          </CardContent>
        </Card>
      </section>

      {props.report ? <ReportDetail report={props.report} lang={props.lang} /> : null}
      <AgentAssistantCard
        messages={props.assistantMessages}
        loading={props.assistantLoading}
        onAsk={() => props.runAssistant()}
        report={props.report}
        lang={props.lang}
      />
    </>
  );
}

function ReportSummary({ report, lang }: { report: ResearchReport | null; lang: Lang }) {
  if (!report) {
    return (
      <Card className="h-full rounded-lg border-white/80 bg-white shadow-sm">
        <CardHeader><CardTitle className="text-base">{tx(lang, "研究结论", "Research Conclusion")}</CardTitle></CardHeader>
        <CardContent className="space-y-3 text-sm text-zinc-500">
          <p>
            {tx(
              lang,
              "输入股票代码后点击生成研报。模型可以发言，但证据先坐主桌。",
              "Enter a ticker and generate a report. The model may speak, but evidence gets the head seat.",
            )}
          </p>
          <div className="rounded-lg border border-teal-100 bg-teal-50/70 px-3 py-2 text-xs leading-5 text-teal-800">
            {tx(lang, "今日小规矩：没有来源的观点，先去冷静区。", "House rule: unsourced opinions sit in the quiet corner.")}
          </div>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card className="h-full rounded-lg border-white/80 bg-white shadow-sm">
      <CardHeader>
        <CardTitle className="flex flex-wrap items-center justify-between gap-2 text-base">
          <span>{report.company_name}</span>
          <span className="flex items-center gap-2">
            <Button asChild size="sm" variant="outline">
              <a href={`${API_BASE}/api/research/${encodeURIComponent(report.symbol)}/pdf?lang=${lang}`} target="_blank" rel="noreferrer">
                <Download className="mr-2 h-3.5 w-3.5" />
                PDF
              </a>
            </Button>
            <RatingBadge rating={report.rating} />
          </span>
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div>
          <p className="text-xs uppercase tracking-[0.12em] text-zinc-500">{tx(lang, "投资摘要", "Thesis")}</p>
          <p className="mt-2 text-sm leading-6 text-zinc-800">{report.thesis}</p>
        </div>
        <div className="grid grid-cols-2 gap-3">
          <MiniMetric label={tx(lang, "价格", "Price")} value={formatNumber(report.current_price)} />
          <MiniMetric label={tx(lang, "证据", "Evidence")} value={evidenceTotal(report)} />
          <MiniMetric label={tx(lang, "置信度", "Confidence")} value={confidenceLabel(report.confidence, lang)} />
          <MiniMetric label={tx(lang, "风险提醒", "Risk Alerts")} value={(report.risk_alerts || []).filter((item) => item.severity !== "info").length} />
          <MiniMetric label={tx(lang, "出版质检", "Publication Gate")} value={auditStatusLabel(report.publication_audit?.status, lang)} />
        </div>
        {(report.risk_alerts || []).some((item) => item.severity !== "info") ? (
          <div className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs leading-5 text-amber-900">
            {(report.risk_alerts || []).filter((item) => item.severity !== "info")[0]?.title}
            ：{(report.risk_alerts || []).filter((item) => item.severity !== "info")[0]?.message}
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}

function EvidenceCoverage({ report, lang }: { report: ResearchReport | null; lang: Lang }) {
  const evidence = report?.research_evidence;
  const groups = [
    [tx(lang, "宏观", "Macro"), evidence?.macro.length || 0],
    [tx(lang, "公告/年报", "Filings"), evidence?.filings.length || 0],
    [tx(lang, "公开研报", "Reports"), evidence?.institutional_reports.length || 0],
    [tx(lang, "渠道分析", "Channels"), evidence?.channel_analysis.length || 0],
    [tx(lang, "新闻", "News"), evidence?.news.length || 0],
  ] as const;
  return (
    <Card className="h-full rounded-lg border-white/80 bg-white shadow-sm">
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <FolderOpen className="h-4 w-4" />
          {tx(lang, "资料覆盖", "Evidence Coverage")}
        </CardTitle>
      </CardHeader>
      <CardContent className="grid grid-cols-2 gap-3 md:grid-cols-5 lg:grid-cols-2">
        {groups.map(([label, count]) => (
          <div key={label} className="rounded-lg border bg-zinc-50 p-3">
            <p className="text-xs text-zinc-500">{label}</p>
            <p className="mt-2 text-2xl font-semibold">{count}</p>
          </div>
        ))}
      </CardContent>
    </Card>
  );
}

function ReportDetail({ report, lang }: { report: ResearchReport; lang: Lang }) {
  const views = [
    {
      label: tx(lang, "宏观周期", "Macro Cycle"),
      view: report.macro_context,
      metrics: [
        [tx(lang, "资料数", "Sources"), report.research_evidence?.macro?.length || 0],
        [tx(lang, "评分", "Score"), Math.round(report.macro_context.score)],
      ],
    },
    {
      label: tx(lang, "估值", "Valuation"),
      view: report.valuation,
      metrics: [
        ["PE", formatNumber(report.key_metrics?.pe_ratio)],
        ["Forward PE", formatNumber(report.key_metrics?.forward_pe)],
        ["PB", formatNumber(report.key_metrics?.pb_ratio)],
        [tx(lang, "市值", "Market Cap"), formatNumber(report.key_metrics?.market_cap)],
      ],
    },
    {
      label: tx(lang, "财务质量", "Financial Quality"),
      view: report.financial_quality,
      metrics: [
        ["ROE", formatPercent(report.key_metrics?.roe)],
        ["ROA", formatPercent(report.key_metrics?.roa)],
        [tx(lang, "净利率", "Net Margin"), formatPercent(report.key_metrics?.profit_margins)],
        [tx(lang, "收入增速", "Revenue Growth"), formatPercent(report.key_metrics?.revenue_growth)],
      ],
    },
    {
      label: tx(lang, "市场共识", "Market Consensus"),
      view: report.sentiment,
      metrics: [
        [tx(lang, "新闻", "News"), report.research_evidence?.news?.length || 0],
        [tx(lang, "机构线索", "Report Leads"), report.research_evidence?.institutional_reports?.length || 0],
      ],
    },
  ] as const;

  return (
    <section className="grid items-stretch gap-5 lg:grid-cols-4">
      <Card className="h-full rounded-lg border-white/80 bg-white shadow-sm lg:col-span-2">
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <ClipboardList className="h-4 w-4" />
            {tx(lang, "信息收集员总结", "Information Collector Summary")}
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <p className="text-sm leading-6 text-zinc-700">{report.information_summary?.summary || tx(lang, "暂无摘要", "No summary")}</p>
          <div className="grid gap-3 md:grid-cols-2">
            <InfoList title={tx(lang, "结构化事实", "Structured Facts")} items={report.information_summary?.structured_facts || []} lang={lang} />
            <InfoList title={tx(lang, "非结构观察", "Unstructured Notes")} items={report.information_summary?.unstructured_notes || []} lang={lang} />
          </div>
          {report.information_summary?.data_gaps?.length ? (
            <InfoList title={tx(lang, "数据缺口", "Data Gaps")} items={report.information_summary.data_gaps} tone="warning" lang={lang} />
          ) : null}
        </CardContent>
      </Card>

      <Card className="h-full rounded-lg border-white/80 bg-white shadow-sm lg:col-span-2">
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <FileText className="h-4 w-4" />
            {tx(lang, "公开资料目录", "Public Evidence Book")}
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <EvidenceGroup title={tx(lang, "公告 / 年报 / SEC / HKEX", "Filings / SEC / HKEX")} items={report.research_evidence?.filings || []} lang={lang} />
          <EvidenceGroup title={tx(lang, "公开机构研报线索", "Public Institutional Report Leads")} items={report.research_evidence?.institutional_reports || []} lang={lang} />
          <EvidenceGroup title={tx(lang, "宏观与政策", "Macro And Policy")} items={report.research_evidence?.macro || []} lang={lang} />
        </CardContent>
      </Card>

      <Card className="h-full rounded-lg border-white/80 bg-white shadow-sm lg:col-span-4">
        <CardHeader>
          <CardTitle className="flex items-center justify-between text-base">
            <span className="flex items-center gap-2">
              <ShieldAlert className="h-4 w-4" />
              {tx(lang, "风险提醒与架构校验", "Risk Alerts And Architecture Checks")}
            </span>
            <Badge variant="secondary" className="rounded-md">{report.pipeline_diagnostics?.topology || "guarded_dag"}</Badge>
          </CardTitle>
        </CardHeader>
        <CardContent className="grid gap-4 lg:grid-cols-[1.1fr_0.9fr]">
          <RiskAlertList alerts={report.risk_alerts || []} compact lang={lang} />
          <div className="grid gap-3 md:grid-cols-3 lg:grid-cols-1">
            <InfoList title={tx(lang, "降延迟", "Latency")} items={report.pipeline_diagnostics?.latency_strategy || []} lang={lang} />
            <InfoList title={tx(lang, "防单向幻觉", "Anti Hallucination")} items={report.pipeline_diagnostics?.hallucination_controls || []} lang={lang} />
            <InfoList title={tx(lang, "置信度调整", "Confidence Adjustments")} items={report.pipeline_diagnostics?.confidence_adjustments || []} tone="warning" lang={lang} />
          </div>
        </CardContent>
      </Card>

      <Card className="h-full rounded-lg border-white/80 bg-white shadow-sm lg:col-span-4">
        <CardHeader>
          <CardTitle className="flex flex-wrap items-center justify-between gap-3 text-base">
            <span className="flex items-center gap-2">
              <ShieldCheck className="h-4 w-4" />
              {tx(lang, "出版质量门", "Publication Gate")}
            </span>
            <Badge className={`rounded-md ${auditStatusClass(report.publication_audit?.status)}`}>
              {auditStatusLabel(report.publication_audit?.status, lang)}
              {report.publication_audit ? ` · ${Math.round(report.publication_audit.score)}/100` : ""}
            </Badge>
          </CardTitle>
        </CardHeader>
        <CardContent className="grid gap-4 lg:grid-cols-[1.15fr_0.85fr]">
          <div className="space-y-2">
            {(report.publication_audit?.findings?.length
              ? report.publication_audit.findings
              : [{
                  code: "pending",
                  severity: "info" as const,
                  category: "audit",
                  title: tx(lang, "未发现自动出版阻断项", "No automated publication blockers found"),
                  detail: tx(lang, "质量门仍不替代逐条人工事实核验。", "The gate still does not replace claim-level human verification."),
                  remediation: "",
                }]
            ).slice(0, 6).map((item) => (
              <div key={item.code} className="rounded-lg border border-slate-200 bg-slate-50/80 px-3 py-2">
                <p className="text-sm font-medium text-zinc-800">{item.title}</p>
                <p className="mt-1 text-xs leading-5 text-zinc-600">{item.detail}</p>
                {item.remediation ? <p className="mt-1 text-xs leading-5 text-amber-800">{item.remediation}</p> : null}
              </div>
            ))}
          </div>
          <InfoList
            title={tx(lang, "自动检查范围", "Automated Checks")}
            items={report.publication_audit?.checks || [tx(lang, "旧报告未记录出版质量门结果。", "Legacy report has no publication gate record.")]}
            lang={lang}
          />
        </CardContent>
      </Card>

      {views.map((item) => (
        <AnalysisViewCard
          key={item.label}
          title={item.label}
          view={item.view}
          metrics={item.metrics}
          fallback={report.information_summary?.data_gaps || []}
          lang={lang}
        />
      ))}

      <Card className="h-full rounded-lg border-white/80 bg-white shadow-sm lg:col-span-2">
        <CardHeader><CardTitle className="text-base">{tx(lang, "多头论点", "Bull Case")}</CardTitle></CardHeader>
        <CardContent className="space-y-2">
          {report.bull_case.map((item) => <Bullet key={item} tone="positive" text={item} />)}
        </CardContent>
      </Card>
      <Card className="h-full rounded-lg border-white/80 bg-white shadow-sm lg:col-span-2">
        <CardHeader><CardTitle className="text-base">{tx(lang, "空头论点", "Bear Case")}</CardTitle></CardHeader>
        <CardContent className="space-y-2">
          {report.bear_case.map((item) => <Bullet key={item} tone="negative" text={item} />)}
        </CardContent>
      </Card>
    </section>
  );
}

function AnalysisViewCard({
  title,
  view,
  metrics,
  fallback,
  lang,
}: {
  title: string;
  view: ResearchReport["valuation"];
  metrics: readonly (readonly [string, string | number])[];
  fallback: string[];
  lang: Lang;
}) {
  const evidence = view.evidence?.length ? view.evidence : fallback.slice(0, 3);
  return (
    <Card className="flex h-full min-h-80 flex-col rounded-lg border-white/80 bg-white shadow-sm">
      <CardHeader>
        <CardTitle className="flex items-center justify-between gap-3 text-base">
          <span>{title}</span>
          <ScorePill score={view.score} />
        </CardTitle>
      </CardHeader>
      <CardContent className="flex flex-1 flex-col">
        <p className="min-h-20 text-sm leading-6 text-zinc-700">
          {view.summary || tx(lang, "暂无摘要，见数据缺口。", "No summary; see data gaps.")}
        </p>
        <div className="mt-4 grid grid-cols-2 gap-2">
          {metrics.map(([label, value]) => (
            <MiniMetric key={label} label={label} value={value} />
          ))}
        </div>
        <div className="mt-4 space-y-2">
          {(evidence.length ? evidence : [tx(lang, "暂无证据，报告置信度会下调。", "No evidence; report confidence is reduced.")]).slice(0, 4).map((item) => (
            <p key={item} className="rounded-md bg-zinc-50 px-3 py-2 text-xs leading-5 text-zinc-600">{item}</p>
          ))}
        </div>
        <div className="mt-auto pt-3">
          <Badge variant="secondary" className="rounded-md">{tx(lang, "数据质量", "Data Quality")}: {view.data_quality}</Badge>
        </div>
      </CardContent>
    </Card>
  );
}

function AgentAssistantCard({
  messages,
  loading,
  onAsk,
  report,
  lang,
}: {
  messages: string[];
  loading: boolean;
  onAsk: () => void;
  report: ResearchReport | null;
  lang: Lang;
}) {
  return (
    <Card className="rounded-lg border-white/80 bg-white shadow-sm">
      <CardHeader>
        <CardTitle className="flex items-center justify-between text-base">
          <span className="flex items-center gap-2"><Bot className="h-4 w-4" />{tx(lang, "Agent 助手分析", "Agent Assistant")}</span>
          <Button size="sm" variant="outline" onClick={onAsk} disabled={loading}>
            {loading ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <MessageSquareText className="mr-2 h-4 w-4" />}
            {tx(lang, "让助手总结", "Summarize")}
          </Button>
        </CardTitle>
      </CardHeader>
      <CardContent className="grid gap-4 lg:grid-cols-[0.9fr_1.1fr]">
        <div className="space-y-3">
          {(messages.length ? messages : [tx(lang, "助手会读取最新研究报告，用信息收集员、宏观研究员和研究总监视角总结证据链、基本面结论和主要风险。", "The assistant reads the latest report and summarizes evidence, fundamentals, macro context, and key risks.")]).map((message, index) => (
            <div key={`${message}-${index}`} className="rounded-lg border bg-zinc-50 px-4 py-3 text-sm leading-6 text-zinc-700">
              {message}
            </div>
          ))}
          {!messages.length ? (
            <div className="rounded-lg border border-amber-100 bg-amber-50/70 px-4 py-3 text-xs leading-5 text-amber-800">
              {tx(
                lang,
                "助手当前很安静，不是偷懒，是在等一份像样的证据清单。",
                "The assistant is quiet, not lazy. It is waiting for a decent evidence list.",
              )}
            </div>
          ) : null}
        </div>
        <div className="rounded-lg border border-slate-200 bg-white/78 p-4">
          <p className="text-xs font-medium uppercase tracking-[0.12em] text-zinc-500">{tx(lang, "当前上下文", "Current Context")}</p>
          <p className="mt-2 text-sm leading-6 text-zinc-700">
            {report?.thesis || tx(lang, "还没有当前报告。先让研究流水线跑起来，别让助手凭空气烹饪观点。", "No current report yet. Run the research flow first; do not let the assistant cook with air.")}
          </p>
        </div>
      </CardContent>
    </Card>
  );
}

function RiskCenterTab(props: {
  symbol: string;
  watchlist: SymbolItem[];
  alerts: RiskAlert[];
  summary: RiskSummary;
  loading: boolean;
  report: ResearchReport | null;
  onSelect: (symbol: string) => void;
  onRefresh: (symbol: string) => void;
  onRefreshAll: () => void;
  lang: Lang;
}) {
  const severityItems = [
    ["critical", tx(props.lang, "严重", "Critical")],
    ["warning", tx(props.lang, "警告", "Warning")],
    ["watch", tx(props.lang, "观察", "Watch")],
    ["info", tx(props.lang, "提示", "Info")],
  ] as const;

  return (
    <section className="grid items-start gap-5 lg:grid-cols-[0.78fr_1.22fr]">
      <div className="space-y-5">
        <Card className="rounded-lg border-white/80 bg-white shadow-sm">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <Bell className="h-4 w-4" />
              {tx(props.lang, "风险扫描", "Risk Scan")}
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <Select
              value={props.symbol}
              onValueChange={(value) => {
                props.onSelect(value);
              }}
            >
              <SelectTrigger><SelectValue placeholder="选择股票" /></SelectTrigger>
              <SelectContent>
                {props.watchlist.map((item) => (
                  <SelectItem key={item.symbol} value={item.symbol}>{item.symbol} · {item.name}</SelectItem>
                ))}
              </SelectContent>
            </Select>
            <div className="grid grid-cols-2 gap-2">
              <Button variant="outline" onClick={() => props.onRefresh(props.symbol)} disabled={props.loading}>
                {props.loading ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <ShieldAlert className="mr-2 h-4 w-4" />}
                {tx(props.lang, "扫描单股", "Scan Symbol")}
              </Button>
              <Button variant="outline" onClick={props.onRefreshAll} disabled={props.loading}>
                {props.loading ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Zap className="mr-2 h-4 w-4" />}
                {tx(props.lang, "扫描股票池", "Scan Universe")}
              </Button>
            </div>
            <p className="text-xs leading-5 text-zinc-500">
              {tx(
                props.lang,
                "报警覆盖大幅回撤、政策事件、周期转弱、财报季和数据质量降级；扫描不依赖 LLM。",
                "Alerts cover drawdowns, policy events, cycle shifts, earnings season, and data quality degradation without relying on an LLM.",
              )}
            </p>
          </CardContent>
        </Card>

        <Card className="rounded-lg border-white/80 bg-white shadow-sm">
          <CardHeader><CardTitle className="text-base">{tx(props.lang, "告警级别", "Alert Severity")}</CardTitle></CardHeader>
          <CardContent className="grid grid-cols-2 gap-3">
            {severityItems.map(([severity, label]) => (
              <div key={severity} className="rounded-lg border bg-zinc-50 p-3">
                <RiskSeverityBadge severity={severity} lang={props.lang} />
                <p className="mt-3 text-2xl font-semibold">{props.summary.by_severity?.[severity] || 0}</p>
                <p className="text-xs text-zinc-500">{label}</p>
              </div>
            ))}
          </CardContent>
        </Card>

        <Card className="rounded-lg border-white/80 bg-white shadow-sm">
          <CardHeader><CardTitle className="flex items-center gap-2 text-base"><CalendarClock className="h-4 w-4" />{tx(props.lang, "触发类型", "Trigger Types")}</CardTitle></CardHeader>
          <CardContent className="space-y-2">
            {Object.entries(props.summary.by_category || {}).map(([category, count]) => (
              <div key={category} className="flex items-center justify-between rounded-lg border bg-zinc-50 px-3 py-2 text-sm">
                <span>{riskCategoryLabel(category, props.lang)}</span>
                <Badge variant="secondary" className="rounded-md">{count}</Badge>
              </div>
            ))}
          </CardContent>
        </Card>
      </div>

      <div className="space-y-5">
        <Card className="rounded-lg border-white/80 bg-white shadow-sm">
          <CardHeader>
            <CardTitle className="flex items-center justify-between text-base">
              <span>{tx(props.lang, "实时风险队列", "Live Risk Queue")}</span>
              <Badge variant="secondary" className="rounded-md">{props.summary.total}</Badge>
            </CardTitle>
          </CardHeader>
          <CardContent>
            <RiskAlertList alerts={props.alerts} lang={props.lang} />
          </CardContent>
        </Card>

        {props.report ? (
          <Card className="rounded-lg border-white/80 bg-white shadow-sm">
            <CardHeader><CardTitle className="text-base">{tx(props.lang, "当前研报风险映射", "Report Risk Map")}</CardTitle></CardHeader>
            <CardContent className="grid gap-3 md:grid-cols-3">
              <InfoList title={tx(props.lang, "风险", "Risks")} items={props.report.risks || []} tone="warning" lang={props.lang} />
              <InfoList title={tx(props.lang, "关键假设", "Catalysts")} items={props.report.catalysts || []} lang={props.lang} />
              <InfoList title={tx(props.lang, "校验", "Checks")} items={props.report.pipeline_diagnostics?.validation_checks || []} lang={props.lang} />
            </CardContent>
          </Card>
        ) : null}
      </div>
    </section>
  );
}

function ReportsTab({
  runs,
  lang,
  onDelete,
  selectedIds,
  deletingIds,
  onToggle,
  onToggleAll,
  onDeleteSelected,
}: {
  runs: RunSummary[];
  lang: Lang;
  onDelete: (reportId: number) => void;
  selectedIds: number[];
  deletingIds: number[];
  onToggle: (reportId: number) => void;
  onToggleAll: (checked: boolean) => void;
  onDeleteSelected: () => void;
}) {
  const allSelected = runs.length > 0 && selectedIds.length === runs.length;
  const someSelected = selectedIds.length > 0;
  return (
    <Card className="rounded-lg border-white/80 bg-white shadow-sm">
      <CardHeader>
        <CardTitle className="flex flex-wrap items-center justify-between gap-3 text-base">
          <span>{tx(lang, "历史报告", "Report History")}</span>
          <div className="flex flex-wrap items-center justify-end gap-2">
            <span className="text-xs font-normal text-zinc-500">
              {someSelected
                ? tx(lang, `已选 ${selectedIds.length} 份，准备清理历史尘埃。`, `${selectedIds.length} selected for cleanup.`)
                : tx(lang, "本地报告可删除，评级统计会随之更新", "Local reports are deletable; rating summaries update after refresh")}
            </span>
            <Button
              size="sm"
              variant="destructive"
              disabled={!someSelected || deletingIds.length > 0}
              onClick={onDeleteSelected}
            >
              {deletingIds.length > 1 ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Trash2 className="mr-2 h-4 w-4" />}
              {tx(lang, "批量删除", "Delete Selected")}
            </Button>
          </div>
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="overflow-x-auto">
        <Table className="min-w-[940px]">
          <TableHeader>
            <TableRow>
              <TableHead className="w-10">
                <input
                  type="checkbox"
                  checked={allSelected}
                  onChange={(event) => onToggleAll(event.target.checked)}
                  aria-label={tx(lang, "选择全部报告", "Select all reports")}
                  className="h-4 w-4 accent-teal-700"
                />
              </TableHead>
              <TableHead>Time</TableHead>
              <TableHead>Symbol</TableHead>
              <TableHead>Company</TableHead>
              <TableHead>Rating</TableHead>
              <TableHead>Confidence</TableHead>
              <TableHead>Run ID</TableHead>
              <TableHead className="w-20 text-right">{tx(lang, "操作", "Action")}</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {runs.map((run) => (
              <TableRow key={run.id}>
                <TableCell>
                  <input
                    type="checkbox"
                    checked={selectedIds.includes(run.id)}
                    onChange={() => onToggle(run.id)}
                    aria-label={tx(lang, "选择报告", "Select report")}
                    className="h-4 w-4 accent-teal-700"
                  />
                </TableCell>
                <TableCell className="font-mono text-xs">{new Date(run.created_at).toLocaleString()}</TableCell>
                <TableCell className="font-mono font-medium">{run.ticker}</TableCell>
                <TableCell>{run.company_name || "-"}</TableCell>
                <TableCell><RatingBadge rating={run.rating || "HOLD"} /></TableCell>
                <TableCell>{run.confidence || "-"}</TableCell>
                <TableCell className="max-w-44 truncate font-mono text-xs text-zinc-500">{run.run_id}</TableCell>
                <TableCell className="text-right">
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-8 w-8 text-zinc-500 hover:bg-red-50 hover:text-red-600"
                    aria-label={tx(lang, "删除报告", "Delete report")}
                    disabled={deletingIds.includes(run.id)}
                    onClick={() => onDelete(run.id)}
                  >
                    {deletingIds.includes(run.id) ? <Loader2 className="h-4 w-4 animate-spin" /> : <Trash2 className="h-4 w-4" />}
                  </Button>
                </TableCell>
              </TableRow>
            ))}
            {!runs.length ? (
              <TableRow>
                <TableCell colSpan={8} className="h-28 text-center text-sm text-zinc-500">
                  {tx(lang, "暂无历史报告。", "No report history yet.")}
                </TableCell>
              </TableRow>
            ) : null}
          </TableBody>
        </Table>
        </div>
      </CardContent>
    </Card>
  );
}

function SettingsTab({ health, providers, lang }: { health: Health | null; providers: Provider[]; lang: Lang }) {
  return (
    <section className="grid gap-5 lg:grid-cols-[0.9fr_1.1fr]">
      <Card className="rounded-lg border-white/80 bg-white shadow-sm">
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <Settings2 className="h-4 w-4" />
            {tx(lang, "API 与存储", "API & Storage")}
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3 text-sm">
          <MiniMetric label="API Base" value={API_BASE} />
          <MiniMetric label="Database" value={health?.database || "-"} />
          <MiniMetric label="Status" value={health?.status || "pending"} />
        </CardContent>
      </Card>

      <Card className="rounded-lg border-white/80 bg-white shadow-sm">
        <CardHeader><CardTitle className="text-base">{tx(lang, "LLM 服务", "LLM Providers")}</CardTitle></CardHeader>
        <CardContent className="space-y-3">
          {providers.map((provider) => (
            <div key={provider.id} className="flex items-center justify-between rounded-lg border bg-zinc-50 px-4 py-3">
              <div>
                <p className="font-medium">{provider.name}</p>
                <p className="text-xs text-zinc-500">{provider.kind} · {provider.deep_model}</p>
              </div>
              <Badge variant={provider.available ? "default" : "secondary"} className="rounded-md">
                {provider.available ? <CheckCircle2 className="mr-1 h-3 w-3" /> : null}
                {provider.available ? "available" : provider.api_key_env || "local"}
              </Badge>
            </div>
          ))}
        </CardContent>
      </Card>
    </section>
  );
}

function RiskAlertList({ alerts, compact = false, lang }: { alerts: RiskAlert[]; compact?: boolean; lang: Lang }) {
  if (!alerts.length) {
    return (
      <div className="flex min-h-32 items-center justify-center rounded-lg border border-dashed bg-zinc-50 text-sm text-zinc-500">
        <FolderOpen className="mr-2 h-4 w-4" />
        {tx(lang, "当前没有触发风险提醒", "No active risk alerts")}
      </div>
    );
  }
  return (
    <div className={compact ? "space-y-2" : "space-y-3"}>
      {alerts.slice(0, compact ? 5 : 16).map((alert) => (
        <div key={alert.id} className="rounded-lg border bg-white p-4 shadow-sm">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <div className="flex flex-wrap items-center gap-2">
                <RiskSeverityBadge severity={alert.severity} lang={lang} />
                <Badge variant="secondary" className="rounded-md">{riskCategoryLabel(alert.category, lang)}</Badge>
                <span className="font-mono text-xs text-zinc-500">{alert.symbol}</span>
              </div>
              <p className="mt-2 text-sm font-semibold text-zinc-950">{alert.title}</p>
            </div>
            <span className="text-xs text-zinc-500">{new Date(alert.triggered_at).toLocaleString()}</span>
          </div>
          <p className="mt-2 text-sm leading-6 text-zinc-700">{alert.message}</p>
          {alert.evidence.length ? (
            <div className="mt-3 grid gap-2 md:grid-cols-2">
              {alert.evidence.slice(0, compact ? 2 : 4).map((item) => (
                <div key={item} className="rounded-md bg-zinc-50 px-3 py-2 text-xs leading-5 text-zinc-600">
                  {item}
                </div>
              ))}
            </div>
          ) : null}
          {alert.action_hint ? (
            <p className="mt-3 rounded-md bg-amber-50 px-3 py-2 text-xs leading-5 text-amber-900">{alert.action_hint}</p>
          ) : null}
        </div>
      ))}
    </div>
  );
}

function RiskSeverityBadge({ severity, lang }: { severity: string; lang: Lang }) {
  const style = {
    critical: "bg-red-600 text-white",
    warning: "bg-amber-600 text-white",
    watch: "bg-zinc-900 text-white",
    info: "bg-zinc-200 text-zinc-800 hover:bg-zinc-200",
  }[severity] || "bg-zinc-200 text-zinc-800";
  const label = {
    critical: tx(lang, "严重", "Critical"),
    warning: tx(lang, "警告", "Warning"),
    watch: tx(lang, "观察", "Watch"),
    info: tx(lang, "提示", "Info"),
  }[severity] || severity;
  return <Badge className={`rounded-md ${style}`}>{label}</Badge>;
}

function auditStatusLabel(status: "approved" | "conditional" | "blocked" | null | undefined, lang: Lang) {
  return {
    approved: tx(lang, "通过", "Approved"),
    conditional: tx(lang, "有条件通过", "Conditional"),
    blocked: tx(lang, "阻断出版", "Blocked"),
  }[String(status)] || tx(lang, "待质检", "Pending");
}

function auditStatusClass(status?: string | null) {
  return {
    approved: "bg-emerald-100 text-emerald-800 hover:bg-emerald-100",
    conditional: "bg-amber-100 text-amber-800 hover:bg-amber-100",
    blocked: "bg-red-100 text-red-800 hover:bg-red-100",
  }[String(status)] || "bg-slate-100 text-slate-700 hover:bg-slate-100";
}

function comparisonInsights(items: SymbolCompareItem[], lang: Lang) {
  if (!items.length) {
    return [
      {
        label: tx(lang, "估值锚", "Valuation Anchor"),
        value: tx(lang, "待对比", "Pending"),
        note: tx(lang, "先选几只股票，别让表格独自思考。", "Pick a few symbols first; tables should not think alone."),
        className: "border-sky-100 bg-sky-50/70 text-sky-900",
      },
      {
        label: tx(lang, "质量锚", "Quality Anchor"),
        value: tx(lang, "待对比", "Pending"),
        note: tx(lang, "ROE、增长和估值要一起看。", "ROE, growth, and valuation belong together."),
        className: "border-teal-100 bg-teal-50/70 text-teal-900",
      },
      {
        label: tx(lang, "市场温度", "Market Heat"),
        value: tx(lang, "待对比", "Pending"),
        note: tx(lang, "涨跌幅只负责提醒，不负责下结论。", "Price change alerts; it does not conclude."),
        className: "border-amber-100 bg-amber-50/70 text-amber-900",
      },
    ];
  }
  const cheapest = [...items].filter((item) => item.pe_ratio != null && item.pe_ratio > 0).sort((a, b) => Number(a.pe_ratio) - Number(b.pe_ratio))[0];
  const quality = [...items].filter((item) => item.roe != null).sort((a, b) => Number(b.roe) - Number(a.roe))[0];
  const momentum = [...items].filter((item) => item.change_pct != null).sort((a, b) => Number(b.change_pct) - Number(a.change_pct))[0];
  return [
    {
      label: tx(lang, "估值最低", "Lowest PE"),
      value: cheapest ? `${cheapest.symbol} · PE ${formatNumber(cheapest.pe_ratio)}` : tx(lang, "暂无 PE", "No PE"),
      note: tx(lang, "便宜不等于好，但值得继续查。", "Cheap is not always good, but it deserves a closer look."),
      className: "border-sky-100 bg-sky-50/70 text-sky-900",
    },
    {
      label: tx(lang, "质量最高", "Highest ROE"),
      value: quality ? `${quality.symbol} · ROE ${formatPercent(quality.roe)}` : tx(lang, "暂无 ROE", "No ROE"),
      note: tx(lang, "好生意通常先在回报率里露头。", "Good businesses often show up first in returns."),
      className: "border-teal-100 bg-teal-50/70 text-teal-900",
    },
    {
      label: tx(lang, "涨跌最强", "Strongest Move"),
      value: momentum ? `${momentum.symbol} · ${Number(momentum.change_pct).toFixed(2)}%` : tx(lang, "暂无涨跌", "No change"),
      note: tx(lang, "热闹归热闹，证据还是要补票。", "Momentum can be loud; evidence still needs a ticket."),
      className: "border-amber-100 bg-amber-50/70 text-amber-900",
    },
  ];
}

function marketLabel(market: string, lang: Lang) {
  return {
    ashare: tx(lang, "A股", "A-share"),
    hk: tx(lang, "港股", "HK"),
    us: tx(lang, "美股", "US"),
  }[market] || market;
}

function riskCategoryLabel(category: string, lang: Lang = "zh") {
  return {
    drawdown: tx(lang, "回撤", "Drawdown"),
    policy_event: tx(lang, "政策", "Policy"),
    cycle_shift: tx(lang, "周期", "Cycle"),
    earnings_season: tx(lang, "财报", "Earnings"),
    data_quality: tx(lang, "数据", "Data"),
    policy: tx(lang, "政策", "Policy"),
    earnings: tx(lang, "财报", "Earnings"),
    macro: tx(lang, "宏观", "Macro"),
    market: tx(lang, "市场", "Market"),
  }[category] || category;
}

function sourceQualityLabel(quality: string, lang: Lang = "zh") {
  return {
    primary: tx(lang, "一手披露", "Primary"),
    institutional: tx(lang, "机构资料", "Institutional"),
    media: tx(lang, "媒体", "Media"),
    search: tx(lang, "搜索线索", "Search"),
    unknown: tx(lang, "未知来源", "Unknown"),
  }[quality] || quality;
}

function newsCategory(item: Record<string, unknown>) {
  const text = `${String(item.title || "")} ${String(item.summary || "")}`.toLowerCase();
  if (/政策|监管|关税|制裁|央行|证监会|policy|regulation|tariff|sanction|fed|sec/.test(text)) return "policy";
  if (/财报|业绩|利润|营收|earnings|revenue|guidance/.test(text)) return "earnings";
  if (/利率|通胀|财政|经济|宏观|gdp|inflation|rates/.test(text)) return "macro";
  return "market";
}

function buildRiskSummary(alerts: RiskAlert[]): RiskSummary {
  const bySeverity: Record<string, number> = { critical: 0, warning: 0, watch: 0, info: 0 };
  const byCategory: Record<string, number> = {};
  const symbols = new Set<string>();
  for (const alert of alerts) {
    bySeverity[alert.severity] = (bySeverity[alert.severity] || 0) + 1;
    byCategory[alert.category] = (byCategory[alert.category] || 0) + 1;
    symbols.add(alert.symbol);
  }
  const highest = ["critical", "warning", "watch", "info"].find((severity) => bySeverity[severity] > 0) || "info";
  return { total: alerts.length, symbols: symbols.size, by_severity: bySeverity, by_category: byCategory, highest };
}

function MiniMetric({ label, value }: { label: string; value: string | number | null | undefined }) {
  return (
    <div className="rounded-lg border bg-zinc-50 px-3 py-2">
      <p className="text-[11px] uppercase tracking-[0.12em] text-zinc-500">{label}</p>
      <p className="mt-1 break-words text-sm font-medium text-zinc-900">{value ?? "-"}</p>
    </div>
  );
}

function InfoList({
  title,
  items,
  tone = "default",
  lang,
}: {
  title: string;
  items: string[];
  tone?: "default" | "warning";
  lang: Lang;
}) {
  const dot = tone === "warning" ? "bg-amber-500" : "bg-zinc-500";
  return (
    <div className="rounded-lg border bg-zinc-50 p-3">
      <p className="text-xs font-medium uppercase tracking-[0.12em] text-zinc-500">{title}</p>
      <div className="mt-3 space-y-2">
        {(items.length ? items : [tx(lang, "暂无", "None")]).slice(0, 8).map((item) => (
          <div key={item} className="flex gap-2 text-xs leading-5 text-zinc-700">
            <span className={`mt-2 h-1.5 w-1.5 shrink-0 rounded-full ${dot}`} />
            <span>{item}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function RatingBadge({ rating }: { rating: string }) {
  const color = rating === "BUY" ? "bg-emerald-600" : rating === "SELL" ? "bg-red-600" : "bg-zinc-900";
  return <Badge className={`rounded-md ${color}`}>{rating}</Badge>;
}

function ScorePill({ score }: { score: number }) {
  const tone = score >= 62 ? "text-emerald-700 bg-emerald-50" : score <= 42 ? "text-red-700 bg-red-50" : "text-zinc-700 bg-zinc-100";
  return <span className={`rounded-md px-2 py-1 text-xs font-medium ${tone}`}>{Math.round(score)}</span>;
}

function Bullet({ text, tone }: { text: string; tone: "positive" | "negative" }) {
  const color = tone === "positive" ? "bg-emerald-500" : "bg-red-500";
  return (
    <div className="flex gap-3 text-sm leading-6 text-zinc-700">
      <span className={`mt-2 h-1.5 w-1.5 shrink-0 rounded-full ${color}`} />
      <span>{text}</span>
    </div>
  );
}

function Pct({ value }: { value?: number | null }) {
  if (value == null || Number.isNaN(value)) return <span className="text-zinc-500">-</span>;
  const positive = value >= 0;
  return (
    <span className={positive ? "font-medium text-emerald-600" : "font-medium text-red-600"}>
      {positive ? "+" : ""}{value.toFixed(2)}%
    </span>
  );
}

function formatNumber(value: unknown) {
  const number = toNumber(value);
  if (number == null) return "-";
  if (Math.abs(number) >= 1e12) return `${(number / 1e12).toFixed(2)}T`;
  if (Math.abs(number) >= 1e9) return `${(number / 1e9).toFixed(2)}B`;
  if (Math.abs(number) >= 1e6) return `${(number / 1e6).toFixed(2)}M`;
  if (Math.abs(number) >= 1000) return number.toLocaleString(undefined, { maximumFractionDigits: 2 });
  return number.toLocaleString(undefined, { maximumFractionDigits: 2 });
}

function formatPercent(value: unknown) {
  const number = toNumber(value);
  if (number == null) return "-";
  const pct = Math.abs(number) <= 10 ? number * 100 : number;
  return `${pct.toFixed(1)}%`;
}

function confidenceLabel(value: string, lang: Lang) {
  return {
    low: tx(lang, "低", "Low"),
    medium: tx(lang, "中", "Medium"),
    high: tx(lang, "高", "High"),
  }[value] || value;
}

function strategySectionTitle(id: string, fallback: string, lang: Lang) {
  return {
    value_investing: tx(lang, "价值投资方法", "Value Investing Methods"),
    frontier_papers: tx(lang, "前沿论文与量化策略", "Frontier Papers And Quant Strategy"),
    market_views: tx(lang, "市场观点与资产配置", "Market Views And Allocation"),
  }[id] || fallback;
}

function strategySectionDescription(id: string, fallback: string, lang: Lang) {
  return {
    value_investing: tx(lang, "关注护城河、现金流、资本回报、估值安全边际和长期复利。", "Focus on moat, cash flow, returns on capital, margin of safety, and compounding."),
    frontier_papers: tx(lang, "跟踪机器学习、因子、组合优化、市场异象等近期研究。", "Track recent work in machine learning, factors, portfolio optimization, and anomalies."),
    market_views: tx(lang, "汇总大型资管、投行和策略团队对宏观、估值与风险溢价的观点。", "Summarize major asset-manager and sell-side views on macro, valuation, and risk premia."),
  }[id] || fallback;
}

function dailySectionTitle(id: string, fallback: string, lang: Lang) {
  return {
    macro_strategy: tx(lang, "每日宏观与策略必读", "Daily Macro And Strategy"),
    company_industry: tx(lang, "公司与行业深度线索", "Company And Sector Deep Dives"),
    filings_earnings: tx(lang, "公告、财报与一手披露", "Filings, Earnings And Primary Sources"),
  }[id] || fallback;
}

function dailySectionDescription(id: string, fallback: string, lang: Lang) {
  return {
    macro_strategy: tx(lang, "聚合公开宏观、政策、资产配置和策略观点，适合每日开盘前阅读。", "Public macro, policy, allocation, and strategy views for pre-market reading."),
    company_industry: tx(lang, "优先收集行业深度、公司深度和估值线索，用于后续个股研报交叉验证。", "Prioritizes sector, company, and valuation leads for later report cross-checks."),
    filings_earnings: tx(lang, "聚合 A/H/美股公告、年报、财报和监管披露入口，作为事实校验底稿。", "Collects A/H/US filings, reports, earnings, and disclosure portals for fact checks."),
  }[id] || fallback;
}

function tx(lang: Lang, zh: string, en: string) {
  return lang === "en" ? en : zh;
}

function evidenceTotal(report: ResearchReport | null) {
  const evidence = report?.research_evidence;
  if (!evidence) return 0;
  return [
    evidence.macro,
    evidence.filings,
    evidence.institutional_reports,
    evidence.channel_analysis,
    evidence.news,
  ].reduce((total, items) => total + items.length, 0);
}

function parseSymbolInput(value: string) {
  return value
    .split(/[\s,，;；、]+/)
    .map((item) => item.trim().toUpperCase())
    .filter(Boolean)
    .filter((item, index, array) => array.indexOf(item) === index)
    .slice(0, 10);
}

function toNumber(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string" && value.trim()) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
}
