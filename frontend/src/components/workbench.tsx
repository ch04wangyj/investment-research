"use client";

import { useEffect, useMemo, useState, type ReactNode } from "react";
import {
  Activity,
  AlertCircle,
  Bell,
  Bot,
  Brain,
  CalendarClock,
  ChevronDown,
  ChevronUp,
  CheckCircle2,
  ClipboardList,
  Database,
  FileText,
  FolderOpen,
  Gauge,
  Layers3,
  Loader2,
  MessageSquareText,
  Newspaper,
  RefreshCw,
  Search,
  Settings2,
  ShieldAlert,
  Sparkles,
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
  apiGet,
  apiPost,
  API_BASE,
  type Provider,
  type EvidenceItem,
  type Quote,
  type RatingSummary,
  type ResearchReport,
  type RiskAlert,
  type RiskSummary,
  type SectorSummary,
  type SymbolItem,
  type SymbolProfile,
} from "@/lib/api";

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
  const [period, setPeriod] = useState("6mo");
  const [providerId, setProviderId] = useState("deepseek");
  const [useLlm, setUseLlm] = useState(true);
  const [stockSearch, setStockSearch] = useState("");
  const [sectorFilter, setSectorFilter] = useState("all");
  const [ratingFilter, setRatingFilter] = useState("all");
  const [assistantMessages, setAssistantMessages] = useState<string[]>([]);
  const [riskAlerts, setRiskAlerts] = useState<RiskAlert[]>([]);
  const [riskSummary, setRiskSummary] = useState<RiskSummary>(defaultRiskSummary);
  const [report, setReport] = useState<ResearchReport | null>(null);
  const [profile, setProfile] = useState<SymbolProfile | null>(null);
  const [showSettings, setShowSettings] = useState(false);
  const [loading, setLoading] = useState(true);
  const [analyzing, setAnalyzing] = useState(false);
  const [assistantLoading, setAssistantLoading] = useState(false);
  const [riskLoading, setRiskLoading] = useState(false);
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

    apiGet<Overview>("/api/market/overview")
      .then(setOverview)
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
    <main className="min-h-screen bg-[#f5f5f7] text-zinc-950">
      <div className="mx-auto flex w-full max-w-7xl flex-col gap-6 px-4 py-5 sm:px-6 lg:px-8">
        <header className="flex flex-col gap-4 rounded-lg border border-white/80 bg-white/86 px-5 py-4 shadow-sm backdrop-blur md:flex-row md:items-center md:justify-between">
          <div>
            <div className="flex items-center gap-2 text-xs font-medium uppercase tracking-[0.14em] text-zinc-500">
              <Sparkles className="h-3.5 w-3.5" />
              Evidence-first AI Research Workbench
            </div>
            <h1 className="mt-2 text-2xl font-semibold tracking-tight text-zinc-950 md:text-3xl">
              AI 深度研报工作台
            </h1>
            <p className="mt-2 max-w-2xl text-sm leading-6 text-zinc-600">
              先快速收集宏观、公告/年报、公开研报线索、新闻与渠道观点，再生成可追溯的机构风格研报。
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant={health?.status === "ok" ? "default" : "secondary"} className="h-8 rounded-md px-3">
              {health?.status === "ok" ? "API Online" : "API Pending"}
            </Badge>
            <Button variant="outline" size="sm" onClick={refresh} disabled={loading}>
              <RefreshCw className="mr-2 h-4 w-4" />
              Refresh
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
              {error}。确认后端已启动：<code className="rounded bg-white px-1 py-0.5">python scripts/run_api.py</code>
            </AlertDescription>
          </Alert>
        ) : null}

        <section className="grid gap-4 md:grid-cols-5">
          <MetricCard icon={<Gauge />} label="Tracked Symbols" value={overview.watchlist.length} />
          <MetricCard icon={<Database />} label="Data Routes" value={providerCount} />
          <MetricCard icon={<FileText />} label="Research Runs" value={runs.length} />
          <MetricCard icon={<ShieldAlert />} label="Risk Alerts" value={activeRiskCount} />
          <MetricCard icon={<Activity />} label="API Version" value={health?.version || "0.2.0"} />
        </section>

        <Tabs defaultValue="research" className="space-y-5">
          <TabsList className="grid h-auto w-full grid-cols-2 rounded-lg bg-white p-1 shadow-sm md:w-[780px] md:grid-cols-5">
            <TabsTrigger value="research">研报工作台</TabsTrigger>
            <TabsTrigger value="evidence">资料目录</TabsTrigger>
            <TabsTrigger value="universe">股票池</TabsTrigger>
            <TabsTrigger value="risk">风险提醒</TabsTrigger>
            <TabsTrigger value="reports">报告历史</TabsTrigger>
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
            />
          </TabsContent>

          <TabsContent value="evidence" className="space-y-5">
            <EvidenceLibraryTab report={report} overview={overview} />
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
            />
          </TabsContent>

          <TabsContent value="reports">
            <ReportsTab runs={runs} />
          </TabsContent>
        </Tabs>

        {showSettings ? <SettingsTab health={health} providers={providers} /> : null}
      </div>
    </main>
  );
}

function MetricCard({ icon, label, value }: { icon: ReactNode; label: string; value: string | number }) {
  return (
    <Card className="rounded-lg border-white/80 bg-white shadow-sm">
      <CardContent className="flex items-center justify-between p-5">
        <div>
          <p className="text-xs font-medium uppercase tracking-[0.12em] text-zinc-500">{label}</p>
          <p className="mt-2 text-2xl font-semibold tracking-tight">{value}</p>
        </div>
        <div className="rounded-lg border bg-zinc-50 p-2 text-zinc-700 [&_svg]:h-5 [&_svg]:w-5">{icon}</div>
      </CardContent>
    </Card>
  );
}

function NewsDirectory({ items }: { items: Array<Record<string, unknown>> }) {
  const [expanded, setExpanded] = useState<string | null>(null);
  const [filter, setFilter] = useState("all");
  const filtered = items.filter((item) => filter === "all" || newsCategory(item) === filter);
  const filters = [
    ["all", "全部"],
    ["policy", "政策"],
    ["earnings", "财报"],
    ["macro", "宏观"],
    ["market", "市场"],
  ];

  if (!items.length) {
    return <div className="rounded-lg border border-dashed bg-zinc-50 p-6 text-sm text-zinc-500">暂无新闻流。</div>;
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
                    {riskCategoryLabel(newsCategory(item))} · {String(item.display_time || item.source || "")}
                  </span>
                </span>
                {open ? <ChevronUp className="mt-1 h-4 w-4 shrink-0 text-zinc-500" /> : <ChevronDown className="mt-1 h-4 w-4 shrink-0 text-zinc-500" />}
              </button>
              {open ? (
                <div className="border-t px-3 py-3 text-sm leading-6 text-zinc-700">
                  <p>{String(item.summary || "无摘要")}</p>
                  <div className="mt-3 flex items-center justify-between gap-3">
                    <Badge variant="secondary" className="rounded-md">{String(item.source || "news")}</Badge>
                    {item.url ? (
                      <a
                        href={String(item.url)}
                        target="_blank"
                        rel="noreferrer"
                        className="text-xs font-medium text-blue-600 hover:text-blue-700"
                      >
                        打开原文
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

function EvidenceLibraryTab({ report, overview }: { report: ResearchReport | null; overview: Overview }) {
  const evidence = report?.research_evidence;
  return (
    <section className="grid gap-5 lg:grid-cols-[1.15fr_0.85fr]">
      <Card className="rounded-lg border-white/80 bg-white shadow-sm">
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <FolderOpen className="h-4 w-4" />
            {report ? `${report.symbol} 公开资料目录` : "公开资料目录"}
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-5">
          {report ? (
            <>
              <EvidenceGroup title="公告 / 年报 / 监管披露" items={evidence?.filings || []} />
              <EvidenceGroup title="公开机构研报线索" items={evidence?.institutional_reports || []} />
              <EvidenceGroup title="宏观与政策背景" items={evidence?.macro || []} />
              <EvidenceGroup title="渠道观点与新闻共识" items={[...(evidence?.channel_analysis || []), ...(evidence?.news || [])]} />
              {evidence?.errors?.length ? <InfoList title="检索问题" items={evidence.errors} tone="warning" /> : null}
            </>
          ) : (
            <div className="rounded-lg border border-dashed bg-zinc-50 p-6 text-sm leading-6 text-zinc-500">
              先在研报工作台生成一份报告，这里会展开公告/年报、公开研报线索、宏观政策和渠道分析目录。
            </div>
          )}
        </CardContent>
      </Card>

      <Card className="rounded-lg border-white/80 bg-white shadow-sm">
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <Newspaper className="h-4 w-4" />
            新闻与政策目录
          </CardTitle>
        </CardHeader>
        <CardContent>
          <NewsDirectory items={overview.news} />
        </CardContent>
      </Card>
    </section>
  );
}

function EvidenceGroup({ title, items }: { title: string; items: EvidenceItem[] }) {
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
              {sourceQualityLabel(item.quality)} · {item.source || "source"} · score {Math.round(item.score)}
            </span>
            {item.summary ? <span className="mt-2 line-clamp-2 block text-xs leading-5 text-zinc-600">{item.summary}</span> : null}
          </a>
        ))}
        {!items.length ? <p className="rounded-md bg-white px-3 py-2 text-xs text-zinc-500">暂无可用来源，报告会降低置信度。</p> : null}
      </div>
    </div>
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
}) {
  const quoteMap = new Map(props.quotes.map((quote) => [quote.symbol || "", quote]));
  return (
    <section className="grid gap-5 lg:grid-cols-[0.76fr_1.24fr]">
      <Card className="rounded-lg border-white/80 bg-white shadow-sm">
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <Layers3 className="h-4 w-4" />
            股票池筛选
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="relative">
            <Search className="absolute left-3 top-2.5 h-4 w-4 text-zinc-400" />
            <Input
              className="pl-9"
              value={props.stockSearch}
              onChange={(event) => props.setStockSearch(event.target.value)}
              placeholder="搜索代码 / 公司名"
            />
          </div>
          <Select value={props.sectorFilter} onValueChange={props.setSectorFilter}>
            <SelectTrigger><SelectValue placeholder="板块" /></SelectTrigger>
            <SelectContent>
              <SelectItem value="all">全部板块</SelectItem>
              {props.sectors.map((sector) => <SelectItem key={sector} value={sector}>{sector}</SelectItem>)}
            </SelectContent>
          </Select>
          <Select value={props.ratingFilter} onValueChange={props.setRatingFilter}>
            <SelectTrigger><SelectValue placeholder="评级" /></SelectTrigger>
            <SelectContent>
              {["all", "BUY", "HOLD", "SELL", "未评级"].map((rating) => (
                <SelectItem key={rating} value={rating}>{rating === "all" ? "全部评级" : rating}</SelectItem>
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

      <Card className="rounded-lg border-white/80 bg-white shadow-sm">
        <CardHeader>
          <CardTitle className="flex items-center justify-between text-base">
            <span>可选股票列表</span>
            <Badge variant="secondary" className="rounded-md">{props.symbols.length} 支</Badge>
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
                    <MiniMetric label="板块" value={item.sector || "未分类"} />
                    <MiniMetric label="价格" value={formatNumber(quote?.close)} />
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
                      Agent分析
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
}) {
  const history = props.profile?.history.payload || [];

  return (
    <>
      <Card className="rounded-lg border-white/80 bg-white shadow-sm">
        <CardContent className="grid gap-3 p-4 md:grid-cols-[1.1fr_0.7fr_1fr_auto_auto]">
          <div className="relative">
            <Search className="absolute left-3 top-2.5 h-4 w-4 text-zinc-400" />
            <Input
              className="pl-9"
              value={props.symbol}
              onChange={(event) => props.setSymbol(event.target.value)}
              placeholder="AAPL / 600519 / 00700"
            />
          </div>
          <Select value={props.period} onValueChange={props.setPeriod}>
            <SelectTrigger><SelectValue placeholder="Period" /></SelectTrigger>
            <SelectContent>
              {["1mo", "3mo", "6mo", "1y", "2y"].map((item) => <SelectItem key={item} value={item}>{item}</SelectItem>)}
            </SelectContent>
          </Select>
          <Select value={props.providerId} onValueChange={props.setProviderId}>
            <SelectTrigger><SelectValue placeholder="LLM Provider" /></SelectTrigger>
            <SelectContent>
              {props.providers.map((provider) => (
                <SelectItem key={provider.id} value={provider.id}>{provider.name}</SelectItem>
              ))}
            </SelectContent>
          </Select>
          <label className="flex h-10 items-center gap-2 rounded-lg border px-3 text-sm text-zinc-700">
            <input
              type="checkbox"
              checked={props.useLlm}
              onChange={(event) => props.setUseLlm(event.target.checked)}
              className="h-4 w-4 accent-zinc-950"
            />
            LLM润色
          </label>
          <Button onClick={() => props.runResearch()} disabled={props.analyzing} className="min-w-32">
            {props.analyzing ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Brain className="mr-2 h-4 w-4" />}
            生成研报
          </Button>
        </CardContent>
      </Card>

      <section className="grid gap-5 lg:grid-cols-[0.92fr_1.08fr]">
        <div className="space-y-5">
          <ReportSummary report={props.report} />
          <EvidenceCoverage report={props.report} />
        </div>

        <Card className="rounded-lg border-white/80 bg-white shadow-sm">
          <CardHeader>
            <CardTitle className="text-base">价格背景与数据质量</CardTitle>
          </CardHeader>
          <CardContent>
            <PriceChart data={history} />
            <p className="mt-3 text-xs text-zinc-500">
              价格图仅作为背景信息，暂不生成技术交易策略。Source: {props.profile?.history.source || "-"} · stale: {String(props.profile?.history.stale || false)}
            </p>
          </CardContent>
        </Card>
      </section>

      {props.report ? <ReportDetail report={props.report} /> : null}
      <AgentAssistantCard
        messages={props.assistantMessages}
        loading={props.assistantLoading}
        onAsk={() => props.runAssistant()}
        report={props.report}
      />
    </>
  );
}

function ReportSummary({ report }: { report: ResearchReport | null }) {
  if (!report) {
    return (
      <Card className="rounded-lg border-white/80 bg-white shadow-sm">
        <CardHeader><CardTitle className="text-base">研究结论</CardTitle></CardHeader>
        <CardContent className="text-sm text-zinc-500">输入股票代码并运行分析后，这里会显示机构研报摘要。</CardContent>
      </Card>
    );
  }

  return (
    <Card className="rounded-lg border-white/80 bg-white shadow-sm">
      <CardHeader>
        <CardTitle className="flex items-center justify-between text-base">
          <span>{report.company_name}</span>
          <RatingBadge rating={report.rating} />
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div>
          <p className="text-xs uppercase tracking-[0.12em] text-zinc-500">Thesis</p>
          <p className="mt-2 text-sm leading-6 text-zinc-800">{report.thesis}</p>
        </div>
        <div className="grid grid-cols-2 gap-3">
          <MiniMetric label="Price" value={formatNumber(report.current_price)} />
          <MiniMetric label="Evidence" value={evidenceTotal(report)} />
          <MiniMetric label="Confidence" value={report.confidence} />
          <MiniMetric label="Risk Alerts" value={(report.risk_alerts || []).filter((item) => item.severity !== "info").length} />
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

function EvidenceCoverage({ report }: { report: ResearchReport | null }) {
  const evidence = report?.research_evidence;
  const groups = [
    ["宏观", evidence?.macro.length || 0],
    ["公告/年报", evidence?.filings.length || 0],
    ["公开研报", evidence?.institutional_reports.length || 0],
    ["渠道分析", evidence?.channel_analysis.length || 0],
    ["新闻", evidence?.news.length || 0],
  ] as const;
  return (
    <Card className="rounded-lg border-white/80 bg-white shadow-sm">
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <FolderOpen className="h-4 w-4" />
          资料覆盖
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

function ReportDetail({ report }: { report: ResearchReport }) {
  const views = [
    ["宏观周期", report.macro_context],
    ["估值", report.valuation],
    ["财务质量", report.financial_quality],
    ["市场共识", report.sentiment],
  ] as const;

  return (
    <section className="grid gap-5 lg:grid-cols-4">
      <Card className="rounded-lg border-white/80 bg-white shadow-sm lg:col-span-2">
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <ClipboardList className="h-4 w-4" />
            信息收集员总结
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <p className="text-sm leading-6 text-zinc-700">{report.information_summary?.summary || "暂无摘要"}</p>
          <div className="grid gap-3 md:grid-cols-2">
            <InfoList title="结构化事实" items={report.information_summary?.structured_facts || []} />
            <InfoList title="非结构观察" items={report.information_summary?.unstructured_notes || []} />
          </div>
          {report.information_summary?.data_gaps?.length ? (
            <InfoList title="数据缺口" items={report.information_summary.data_gaps} tone="warning" />
          ) : null}
        </CardContent>
      </Card>

      <Card className="rounded-lg border-white/80 bg-white shadow-sm lg:col-span-2">
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <FileText className="h-4 w-4" />
            公开资料目录
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <EvidenceGroup title="公告 / 年报 / SEC / HKEX" items={report.research_evidence?.filings || []} />
          <EvidenceGroup title="公开机构研报线索" items={report.research_evidence?.institutional_reports || []} />
          <EvidenceGroup title="宏观与政策" items={report.research_evidence?.macro || []} />
        </CardContent>
      </Card>

      <Card className="rounded-lg border-white/80 bg-white shadow-sm lg:col-span-4">
        <CardHeader>
          <CardTitle className="flex items-center justify-between text-base">
            <span className="flex items-center gap-2">
              <ShieldAlert className="h-4 w-4" />
              风险提醒与架构校验
            </span>
            <Badge variant="secondary" className="rounded-md">{report.pipeline_diagnostics?.topology || "guarded_dag"}</Badge>
          </CardTitle>
        </CardHeader>
        <CardContent className="grid gap-4 lg:grid-cols-[1.1fr_0.9fr]">
          <RiskAlertList alerts={report.risk_alerts || []} compact />
          <div className="grid gap-3 md:grid-cols-3 lg:grid-cols-1">
            <InfoList title="降延迟" items={report.pipeline_diagnostics?.latency_strategy || []} />
            <InfoList title="防单向幻觉" items={report.pipeline_diagnostics?.hallucination_controls || []} />
            <InfoList title="置信度调整" items={report.pipeline_diagnostics?.confidence_adjustments || []} tone="warning" />
          </div>
        </CardContent>
      </Card>

      {views.map(([label, view]) => (
        <Card key={label} className="rounded-lg border-white/80 bg-white shadow-sm">
          <CardHeader>
            <CardTitle className="flex items-center justify-between text-base">
              {label}
              <ScorePill score={view.score} />
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm leading-6 text-zinc-700">{view.summary}</p>
            <div className="mt-4 space-y-2">
              {view.evidence.slice(0, 4).map((item) => (
                <p key={item} className="rounded-md bg-zinc-50 px-3 py-2 text-xs text-zinc-600">{item}</p>
              ))}
            </div>
          </CardContent>
        </Card>
      ))}

      <Card className="rounded-lg border-white/80 bg-white shadow-sm lg:col-span-2">
        <CardHeader><CardTitle className="text-base">Bull Case</CardTitle></CardHeader>
        <CardContent className="space-y-2">
          {report.bull_case.map((item) => <Bullet key={item} tone="positive" text={item} />)}
        </CardContent>
      </Card>
      <Card className="rounded-lg border-white/80 bg-white shadow-sm lg:col-span-2">
        <CardHeader><CardTitle className="text-base">Bear Case</CardTitle></CardHeader>
        <CardContent className="space-y-2">
          {report.bear_case.map((item) => <Bullet key={item} tone="negative" text={item} />)}
        </CardContent>
      </Card>
    </section>
  );
}

function AgentAssistantCard({
  messages,
  loading,
  onAsk,
  report,
}: {
  messages: string[];
  loading: boolean;
  onAsk: () => void;
  report: ResearchReport | null;
}) {
  return (
    <Card className="rounded-lg border-white/80 bg-white shadow-sm">
      <CardHeader>
        <CardTitle className="flex items-center justify-between text-base">
          <span className="flex items-center gap-2"><Bot className="h-4 w-4" />Agent 助手分析</span>
          <Button size="sm" variant="outline" onClick={onAsk} disabled={loading}>
            {loading ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <MessageSquareText className="mr-2 h-4 w-4" />}
            让助手总结
          </Button>
        </CardTitle>
      </CardHeader>
      <CardContent className="grid gap-4 lg:grid-cols-[0.9fr_1.1fr]">
        <div className="space-y-3">
          {(messages.length ? messages : ["助手会读取最新研究报告，用信息收集员、宏观研究员和研究总监视角总结证据链、基本面结论和主要风险。"]).map((message, index) => (
            <div key={`${message}-${index}`} className="rounded-lg border bg-zinc-50 px-4 py-3 text-sm leading-6 text-zinc-700">
              {message}
            </div>
          ))}
        </div>
        <div className="rounded-lg border bg-white p-4">
          <p className="text-xs font-medium uppercase tracking-[0.12em] text-zinc-500">当前上下文</p>
          <p className="mt-2 text-sm leading-6 text-zinc-700">
            {report?.thesis || "还没有当前报告。先在研报工作台点击生成研报，或让助手触发一次基础分析。"}
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
}) {
  const severityItems = [
    ["critical", "严重"],
    ["warning", "警告"],
    ["watch", "观察"],
    ["info", "提示"],
  ] as const;

  return (
    <section className="grid gap-5 lg:grid-cols-[0.78fr_1.22fr]">
      <div className="space-y-5">
        <Card className="rounded-lg border-white/80 bg-white shadow-sm">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <Bell className="h-4 w-4" />
              风险扫描
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
                扫描单股
              </Button>
              <Button variant="outline" onClick={props.onRefreshAll} disabled={props.loading}>
                {props.loading ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Zap className="mr-2 h-4 w-4" />}
                扫描股票池
              </Button>
            </div>
            <p className="text-xs leading-5 text-zinc-500">
              报警覆盖大幅回撤、政策事件、周期转弱、财报季和数据质量降级；扫描不依赖 LLM。
            </p>
          </CardContent>
        </Card>

        <Card className="rounded-lg border-white/80 bg-white shadow-sm">
          <CardHeader><CardTitle className="text-base">告警级别</CardTitle></CardHeader>
          <CardContent className="grid grid-cols-2 gap-3">
            {severityItems.map(([severity, label]) => (
              <div key={severity} className="rounded-lg border bg-zinc-50 p-3">
                <RiskSeverityBadge severity={severity} />
                <p className="mt-3 text-2xl font-semibold">{props.summary.by_severity?.[severity] || 0}</p>
                <p className="text-xs text-zinc-500">{label}</p>
              </div>
            ))}
          </CardContent>
        </Card>

        <Card className="rounded-lg border-white/80 bg-white shadow-sm">
          <CardHeader><CardTitle className="flex items-center gap-2 text-base"><CalendarClock className="h-4 w-4" />触发类型</CardTitle></CardHeader>
          <CardContent className="space-y-2">
            {Object.entries(props.summary.by_category || {}).map(([category, count]) => (
              <div key={category} className="flex items-center justify-between rounded-lg border bg-zinc-50 px-3 py-2 text-sm">
                <span>{riskCategoryLabel(category)}</span>
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
              <span>实时风险队列</span>
              <Badge variant="secondary" className="rounded-md">{props.summary.total} 条</Badge>
            </CardTitle>
          </CardHeader>
          <CardContent>
            <RiskAlertList alerts={props.alerts} />
          </CardContent>
        </Card>

        {props.report ? (
          <Card className="rounded-lg border-white/80 bg-white shadow-sm">
            <CardHeader><CardTitle className="text-base">当前研报风险映射</CardTitle></CardHeader>
            <CardContent className="grid gap-3 md:grid-cols-3">
              <InfoList title="风险" items={props.report.risks || []} tone="warning" />
              <InfoList title="关键假设" items={props.report.catalysts || []} />
              <InfoList title="校验" items={props.report.pipeline_diagnostics?.validation_checks || []} />
            </CardContent>
          </Card>
        ) : null}
      </div>
    </section>
  );
}

function ReportsTab({ runs }: { runs: RunSummary[] }) {
  return (
    <Card className="rounded-lg border-white/80 bg-white shadow-sm">
      <CardHeader><CardTitle className="text-base">历史报告</CardTitle></CardHeader>
      <CardContent>
        <div className="overflow-x-auto">
        <Table className="min-w-[780px]">
          <TableHeader>
            <TableRow>
              <TableHead>Time</TableHead>
              <TableHead>Symbol</TableHead>
              <TableHead>Company</TableHead>
              <TableHead>Rating</TableHead>
              <TableHead>Confidence</TableHead>
              <TableHead>Run ID</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {runs.map((run) => (
              <TableRow key={run.id}>
                <TableCell className="font-mono text-xs">{new Date(run.created_at).toLocaleString()}</TableCell>
                <TableCell className="font-mono font-medium">{run.ticker}</TableCell>
                <TableCell>{run.company_name || "-"}</TableCell>
                <TableCell><RatingBadge rating={run.rating || "HOLD"} /></TableCell>
                <TableCell>{run.confidence || "-"}</TableCell>
                <TableCell className="max-w-44 truncate font-mono text-xs text-zinc-500">{run.run_id}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
        </div>
      </CardContent>
    </Card>
  );
}

function SettingsTab({ health, providers }: { health: Health | null; providers: Provider[] }) {
  return (
    <section className="grid gap-5 lg:grid-cols-[0.9fr_1.1fr]">
      <Card className="rounded-lg border-white/80 bg-white shadow-sm">
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <Settings2 className="h-4 w-4" />
            API & Storage
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3 text-sm">
          <MiniMetric label="API Base" value={API_BASE} />
          <MiniMetric label="Database" value={health?.database || "-"} />
          <MiniMetric label="Status" value={health?.status || "pending"} />
        </CardContent>
      </Card>

      <Card className="rounded-lg border-white/80 bg-white shadow-sm">
        <CardHeader><CardTitle className="text-base">LLM Providers</CardTitle></CardHeader>
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

function RiskAlertList({ alerts, compact = false }: { alerts: RiskAlert[]; compact?: boolean }) {
  if (!alerts.length) {
    return (
      <div className="flex min-h-32 items-center justify-center rounded-lg border border-dashed bg-zinc-50 text-sm text-zinc-500">
        <FolderOpen className="mr-2 h-4 w-4" />
        当前没有触发风险提醒
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
                <RiskSeverityBadge severity={alert.severity} />
                <Badge variant="secondary" className="rounded-md">{riskCategoryLabel(alert.category)}</Badge>
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

function RiskSeverityBadge({ severity }: { severity: string }) {
  const style = {
    critical: "bg-red-600 text-white",
    warning: "bg-amber-600 text-white",
    watch: "bg-zinc-900 text-white",
    info: "bg-zinc-200 text-zinc-800 hover:bg-zinc-200",
  }[severity] || "bg-zinc-200 text-zinc-800";
  const label = {
    critical: "严重",
    warning: "警告",
    watch: "观察",
    info: "提示",
  }[severity] || severity;
  return <Badge className={`rounded-md ${style}`}>{label}</Badge>;
}

function riskCategoryLabel(category: string) {
  return {
    drawdown: "回撤",
    policy_event: "政策",
    cycle_shift: "周期",
    earnings_season: "财报",
    data_quality: "数据",
    policy: "政策",
    earnings: "财报",
    macro: "宏观",
    market: "市场",
  }[category] || category;
}

function sourceQualityLabel(quality: string) {
  return {
    primary: "一手披露",
    institutional: "机构资料",
    media: "媒体",
    search: "搜索线索",
    unknown: "未知来源",
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

function InfoList({ title, items, tone = "default" }: { title: string; items: string[]; tone?: "default" | "warning" }) {
  const dot = tone === "warning" ? "bg-amber-500" : "bg-zinc-500";
  return (
    <div className="rounded-lg border bg-zinc-50 p-3">
      <p className="text-xs font-medium uppercase tracking-[0.12em] text-zinc-500">{title}</p>
      <div className="mt-3 space-y-2">
        {(items.length ? items : ["暂无"]).slice(0, 8).map((item) => (
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

function toNumber(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string" && value.trim()) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
}
