"use client";

import { useEffect, useMemo, useState, type ReactNode } from "react";
import {
  Activity,
  AlertCircle,
  BarChart3,
  Brain,
  CheckCircle2,
  Database,
  FileText,
  Gauge,
  Loader2,
  RefreshCw,
  Search,
  Settings2,
  Sparkles,
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
import { apiGet, apiPost, API_BASE, type Provider, type Quote, type ResearchReport, type SymbolItem, type SymbolProfile } from "@/lib/api";

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
  const [report, setReport] = useState<ResearchReport | null>(null);
  const [profile, setProfile] = useState<SymbolProfile | null>(null);
  const [loading, setLoading] = useState(true);
  const [analyzing, setAnalyzing] = useState(false);
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

  async function runResearch() {
    const clean = symbol.trim().toUpperCase();
    if (!clean) return;
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

  const providerCount = useMemo(
    () => health ? Object.values(health.providers).flat().length : 0,
    [health],
  );

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
          <TabsList className="grid h-auto w-full grid-cols-2 rounded-lg bg-white p-1 shadow-sm md:w-[620px] md:grid-cols-4">
            <TabsTrigger value="overview">市场概览</TabsTrigger>
            <TabsTrigger value="research">单股研究</TabsTrigger>
            <TabsTrigger value="reports">报告历史</TabsTrigger>
            <TabsTrigger value="settings">模型设置</TabsTrigger>
          </TabsList>

          <TabsContent value="overview" className="space-y-5">
            <OverviewTab loading={loading} overview={overview} />
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
              report={report}
              profile={profile}
            />
          </TabsContent>

          <TabsContent value="reports">
            <ReportsTab runs={runs} />
          </TabsContent>

          <TabsContent value="settings">
            <SettingsTab health={health} providers={providers} />
          </TabsContent>
        </Tabs>
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
          <Button onClick={props.runResearch} disabled={props.analyzing} className="min-w-32">
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

function toNumber(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string" && value.trim()) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
}
