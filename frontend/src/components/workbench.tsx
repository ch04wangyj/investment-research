"use client";

import { useEffect, useMemo, useState, type ReactNode } from "react";
import {
  Activity,
  AlertCircle,
  BarChart3,
  Bot,
  Brain,
  CheckCircle2,
  ClipboardList,
  Database,
  FileText,
  Gauge,
  Layers3,
  Loader2,
  MessageSquareText,
  RefreshCw,
  Search,
  Settings2,
  Sparkles,
  Target,
  TrendingUp,
} from "lucide-react";

import { PriceChart } from "@/components/price-chart";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Separator } from "@/components/ui/separator";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  apiGet,
  apiPost,
  API_BASE,
  type Provider,
  type Quote,
  type RatingSummary,
  type ResearchReport,
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

export function Workbench() {
  const [health, setHealth] = useState<Health | null>(null);
  const [providers, setProviders] = useState<Provider[]>([]);
  const [overview, setOverview] = useState<Overview>(defaultOverview);
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [symbol, setSymbol] = useState("AAPL");
  const [period, setPeriod] = useState("6mo");
  const [providerId, setProviderId] = useState("deepseek");
  const [useLlm, setUseLlm] = useState(false);
  const [stockSearch, setStockSearch] = useState("");
  const [sectorFilter, setSectorFilter] = useState("all");
  const [ratingFilter, setRatingFilter] = useState("all");
  const [assistantMessages, setAssistantMessages] = useState<string[]>([]);
  const [report, setReport] = useState<ResearchReport | null>(null);
  const [profile, setProfile] = useState<SymbolProfile | null>(null);
  const [loading, setLoading] = useState(true);
  const [analyzing, setAnalyzing] = useState(false);
  const [assistantLoading, setAssistantLoading] = useState(false);
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
  }

  useEffect(() => {
    const timer = window.setTimeout(() => {
      void refresh();
    }, 0);
    return () => window.clearTimeout(timer);
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
    const nextProfile = await apiGet<SymbolProfile>(`/api/symbols/${clean}?period=${period}`).catch(() => null);
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
      if (response.report) setReport(response.report);
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
              Professional AI Research Workbench
            </div>
            <h1 className="mt-2 text-2xl font-semibold tracking-tight text-zinc-950 md:text-3xl">
              AI 投资研究工作台
            </h1>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant={health?.status === "ok" ? "default" : "secondary"} className="h-8 rounded-md px-3">
              {health?.status === "ok" ? "API Online" : "API Pending"}
            </Badge>
            <Button variant="outline" size="sm" onClick={refresh} disabled={loading}>
              <RefreshCw className="mr-2 h-4 w-4" />
              Refresh
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

        <section className="grid gap-4 md:grid-cols-4">
          <MetricCard icon={<Gauge />} label="Tracked Symbols" value={overview.watchlist.length} />
          <MetricCard icon={<Database />} label="Provider Routes" value={providerCount} />
          <MetricCard icon={<FileText />} label="Research Runs" value={runs.length} />
          <MetricCard icon={<Activity />} label="API Version" value={health?.version || "0.2.0"} />
        </section>

        <Tabs defaultValue="overview" className="space-y-5">
          <TabsList className="grid h-auto w-full grid-cols-2 rounded-lg bg-white p-1 shadow-sm md:w-[920px] md:grid-cols-6">
            <TabsTrigger value="overview">市场概览</TabsTrigger>
            <TabsTrigger value="universe">股票池</TabsTrigger>
            <TabsTrigger value="research">单股研究</TabsTrigger>
            <TabsTrigger value="assistant">Agent助手</TabsTrigger>
            <TabsTrigger value="strategy">策略评级</TabsTrigger>
            <TabsTrigger value="reports">报告历史</TabsTrigger>
          </TabsList>

          <TabsContent value="overview" className="space-y-5">
            <OverviewTab loading={loading} overview={overview} />
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

          <TabsContent value="assistant" className="space-y-5">
            <AssistantTab
              symbol={symbol}
              watchlist={overview.watchlist}
              onSelect={(next) => void selectSymbol(next)}
              onAsk={runAssistant}
              loading={assistantLoading}
              messages={assistantMessages}
              report={report}
            />
          </TabsContent>

          <TabsContent value="strategy" className="space-y-5">
            <StrategyTab overview={overview} runs={runs} report={report} onSelect={(next) => void selectSymbol(next)} />
          </TabsContent>

          <TabsContent value="reports">
            <ReportsTab runs={runs} />
          </TabsContent>
        </Tabs>

        <SettingsTab health={health} providers={providers} />
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

function OverviewTab({ loading, overview }: { loading: boolean; overview: Overview }) {
  if (loading) {
    return (
      <div className="grid gap-4 md:grid-cols-3">
        {Array.from({ length: 6 }).map((_, index) => <Skeleton key={index} className="h-32 rounded-lg" />)}
      </div>
    );
  }

  return (
    <>
      <section className="grid gap-4 lg:grid-cols-3">
        {overview.indices.slice(0, 6).map((item, index) => (
          <Card key={`${String(item.code || item.name)}-${index}`} className="rounded-lg border-white/80 bg-white shadow-sm">
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium text-zinc-500">{String(item.name || item.name_en || "Index")}</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="flex items-end justify-between">
                <p className="text-2xl font-semibold tracking-tight">{formatNumber(item.price)}</p>
                <Pct value={toNumber(item.change_pct)} />
              </div>
              <p className="mt-3 text-xs text-zinc-500">{String(item.source || "market data")}</p>
            </CardContent>
          </Card>
        ))}
      </section>

      <section className="grid gap-5 lg:grid-cols-[1.5fr_1fr]">
        <Card className="rounded-lg border-white/80 bg-white shadow-sm">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <BarChart3 className="h-4 w-4" />
              自选股行情
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="overflow-x-auto">
            <Table className="min-w-[640px]">
              <TableHeader>
                <TableRow>
                  <TableHead>Symbol</TableHead>
                  <TableHead>Name</TableHead>
                  <TableHead>Price</TableHead>
                  <TableHead>Change</TableHead>
                  <TableHead>Source</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {(overview.quotes.length ? overview.quotes : overview.watchlist.slice(0, 12).map((item): Quote => ({
                  symbol: item.symbol,
                  name: item.name,
                }))).slice(0, 12).map((quote, index) => (
                  <TableRow key={`${quote.symbol}-${index}`}>
                    <TableCell className="font-mono font-medium">{quote.symbol}</TableCell>
                    <TableCell>{quote.name || "-"}</TableCell>
                    <TableCell>{formatNumber(quote.close)}</TableCell>
                    <TableCell><Pct value={quote.change_pct} /></TableCell>
                    <TableCell className="text-xs text-zinc-500">{quote._meta?.source || "-"}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
            </div>
          </CardContent>
        </Card>

        <Card className="rounded-lg border-white/80 bg-white shadow-sm">
          <CardHeader>
            <CardTitle className="text-base">新闻与政策</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            {overview.news.slice(0, 8).map((item, index) => (
              <div key={`${String(item.title)}-${index}`}>
                <a
                  href={String(item.url || "#")}
                  target="_blank"
                  rel="noreferrer"
                  className="line-clamp-2 text-sm font-medium text-zinc-950 hover:text-blue-600"
                >
                  {String(item.title || "Untitled")}
                </a>
                <p className="mt-1 text-xs text-zinc-500">{String(item.display_time || item.source || "")}</p>
                {index < overview.news.slice(0, 8).length - 1 ? <Separator className="mt-4" /> : null}
              </div>
            ))}
          </CardContent>
        </Card>
      </section>
    </>
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
        <CardContent className="grid gap-3 p-4 md:grid-cols-[1.2fr_0.8fr_1fr_auto_auto]">
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
            LLM
          </label>
          <Button onClick={() => props.runResearch()} disabled={props.analyzing} className="min-w-32">
            {props.analyzing ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Brain className="mr-2 h-4 w-4" />}
            Analyze
          </Button>
        </CardContent>
      </Card>

      <section className="grid gap-5 lg:grid-cols-[1.25fr_0.75fr]">
        <Card className="rounded-lg border-white/80 bg-white shadow-sm">
          <CardHeader>
            <CardTitle className="text-base">K 线与成交量</CardTitle>
          </CardHeader>
          <CardContent>
            <PriceChart data={history} />
            <p className="mt-3 text-xs text-zinc-500">
              Source: {props.profile?.history.source || "-"} · stale: {String(props.profile?.history.stale || false)}
            </p>
          </CardContent>
        </Card>

        <ReportSummary report={props.report} />
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
          <MiniMetric label="Target 6M" value={formatNumber(report.price_target_6m)} />
          <MiniMetric label="Confidence" value={report.confidence} />
          <MiniMetric label="LLM" value={report.llm_status} />
        </div>
      </CardContent>
    </Card>
  );
}

function ReportDetail({ report }: { report: ResearchReport }) {
  const views = [
    ["估值", report.valuation],
    ["财务质量", report.financial_quality],
    ["技术面", report.technical],
    ["新闻情绪", report.sentiment],
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
            <Target className="h-4 w-4" />
            交易策略员
          </CardTitle>
        </CardHeader>
        <CardContent>
          {report.trading_strategy ? (
            <div className="space-y-4">
              <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
                <MiniMetric label="动作" value={strategyLabel(report.trading_strategy.action)} />
                <MiniMetric label="仓位" value={`${report.trading_strategy.position_size_pct}%`} />
                <MiniMetric label="止损" value={formatNumber(report.trading_strategy.stop_loss)} />
                <MiniMetric label="止盈" value={formatNumber(report.trading_strategy.take_profit)} />
              </div>
              <MiniMetric label="入场区间" value={report.trading_strategy.entry_zone} />
              <InfoList title="策略依据" items={report.trading_strategy.rationale} />
              <InfoList title="失效条件" items={report.trading_strategy.invalidation} tone="warning" />
            </div>
          ) : (
            <p className="text-sm text-zinc-500">暂无交易策略。</p>
          )}
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
          {(messages.length ? messages : ["助手会读取最新研究报告，分别用信息收集员和交易策略员人格给出重点总结。"]).map((message, index) => (
            <div key={`${message}-${index}`} className="rounded-lg border bg-zinc-50 px-4 py-3 text-sm leading-6 text-zinc-700">
              {message}
            </div>
          ))}
        </div>
        <div className="rounded-lg border bg-white p-4">
          <p className="text-xs font-medium uppercase tracking-[0.12em] text-zinc-500">当前上下文</p>
          <p className="mt-2 text-sm leading-6 text-zinc-700">
            {report?.thesis || "还没有当前报告。先在单股研究页运行 Analyze，或直接点击助手总结生成基础分析。"}
          </p>
        </div>
      </CardContent>
    </Card>
  );
}

function AssistantTab(props: {
  symbol: string;
  watchlist: SymbolItem[];
  onSelect: (symbol: string) => void;
  onAsk: (question?: string) => void;
  loading: boolean;
  messages: string[];
  report: ResearchReport | null;
}) {
  const [question, setQuestion] = useState("这只股票现在适合观察、持有还是减仓？");
  return (
    <section className="grid gap-5 lg:grid-cols-[0.72fr_1.28fr]">
      <Card className="rounded-lg border-white/80 bg-white shadow-sm">
        <CardHeader><CardTitle className="text-base">选择股票给 Agent 助手</CardTitle></CardHeader>
        <CardContent className="space-y-3">
          <Select value={props.symbol} onValueChange={props.onSelect}>
            <SelectTrigger><SelectValue placeholder="选择股票" /></SelectTrigger>
            <SelectContent>
              {props.watchlist.map((item) => (
                <SelectItem key={item.symbol} value={item.symbol}>{item.symbol} · {item.name}</SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Input value={question} onChange={(event) => setQuestion(event.target.value)} placeholder="问助手一个研究问题" />
          <Button className="w-full" onClick={() => props.onAsk(question)} disabled={props.loading}>
            {props.loading ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Bot className="mr-2 h-4 w-4" />}
            启动助手分析
          </Button>
          <p className="text-xs leading-5 text-zinc-500">
            助手会优先读取最新结构化报告；如没有报告，会触发一次轻量研究流水线。
          </p>
        </CardContent>
      </Card>
      <AgentAssistantCard messages={props.messages} loading={props.loading} onAsk={() => props.onAsk(question)} report={props.report} />
    </section>
  );
}

function StrategyTab({
  overview,
  runs,
  report,
  onSelect,
}: {
  overview: Overview;
  runs: RunSummary[];
  report: ResearchReport | null;
  onSelect: (symbol: string) => void;
}) {
  const ratingCounts = overview.ratings?.counts || {};
  return (
    <section className="grid gap-5 lg:grid-cols-[0.8fr_1.2fr]">
      <div className="space-y-5">
        <Card className="rounded-lg border-white/80 bg-white shadow-sm">
          <CardHeader><CardTitle className="flex items-center gap-2 text-base"><TrendingUp className="h-4 w-4" />投资评级分布</CardTitle></CardHeader>
          <CardContent className="grid grid-cols-3 gap-3">
            {["BUY", "HOLD", "SELL"].map((rating) => (
              <div key={rating} className="rounded-lg border bg-zinc-50 p-4">
                <RatingBadge rating={rating} />
                <p className="mt-3 text-2xl font-semibold">{ratingCounts[rating] || runs.filter((run) => run.rating === rating).length}</p>
              </div>
            ))}
          </CardContent>
        </Card>
        <Card className="rounded-lg border-white/80 bg-white shadow-sm">
          <CardHeader><CardTitle className="flex items-center gap-2 text-base"><Layers3 className="h-4 w-4" />板块分类</CardTitle></CardHeader>
          <CardContent className="space-y-3">
            {(overview.sectors || []).map((sector) => (
              <div key={sector.sector} className="rounded-lg border bg-zinc-50 p-3">
                <div className="flex items-center justify-between">
                  <p className="font-medium">{sector.sector}</p>
                  <Badge variant="secondary">{sector.count} 支</Badge>
                </div>
                <div className="mt-2 flex items-center justify-between text-xs text-zinc-500">
                  <span>上涨 {sector.positive} / 下跌 {sector.negative}</span>
                  <Pct value={sector.avg_change_pct} />
                </div>
              </div>
            ))}
          </CardContent>
        </Card>
      </div>
      <Card className="rounded-lg border-white/80 bg-white shadow-sm">
        <CardHeader>
          <CardTitle className="text-base">最新策略与评级股票</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          {report?.trading_strategy ? (
            <div className="rounded-lg border bg-zinc-50 p-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="font-mono text-sm font-semibold">{report.symbol}</p>
                  <p className="text-sm text-zinc-600">{report.company_name}</p>
                </div>
                <RatingBadge rating={report.rating} />
              </div>
              <div className="mt-4 grid grid-cols-2 gap-3 md:grid-cols-4">
                <MiniMetric label="动作" value={strategyLabel(report.trading_strategy.action)} />
                <MiniMetric label="仓位" value={`${report.trading_strategy.position_size_pct}%`} />
                <MiniMetric label="入场" value={report.trading_strategy.entry_zone} />
                <MiniMetric label="目标" value={formatNumber(report.trading_strategy.take_profit)} />
              </div>
            </div>
          ) : null}
          <div className="grid gap-3 md:grid-cols-2">
            {runs.slice(0, 12).map((run) => (
              <button
                key={run.id}
                onClick={() => onSelect(run.ticker)}
                className="rounded-lg border bg-white p-4 text-left shadow-sm hover:border-zinc-400"
              >
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <p className="font-mono text-sm font-semibold">{run.ticker}</p>
                    <p className="text-sm text-zinc-600">{run.company_name || "-"}</p>
                  </div>
                  <RatingBadge rating={run.rating || "HOLD"} />
                </div>
                <p className="mt-3 text-xs text-zinc-500">{new Date(run.created_at).toLocaleString()}</p>
              </button>
            ))}
          </div>
        </CardContent>
      </Card>
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

function strategyLabel(action: string) {
  return {
    accumulate: "分批买入",
    hold: "持有观察",
    reduce: "降低仓位",
    avoid: "暂时回避",
  }[action] || action;
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

function toNumber(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string" && value.trim()) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
}
