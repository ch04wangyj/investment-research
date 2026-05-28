"""FastAPI application exposing market data, symbols, models, and research runs."""

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.encoders import jsonable_encoder
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel

from config.settings import get_settings
from src.agents.research.graph import run_research_pipeline
from src.core.llm import provider_catalog
from src.data.dal import detect_market, get_dal, normalize_symbol
from src.data.indices import fetch_all_indices
from src.data.news_fetcher import fetch_financial_news
from src.research.schemas import ResearchRequest
from src.research.daily_reads import collect_daily_reads
from src.research.strategy_research import collect_strategy_research
from src.research.workflow_blueprint import workflow_blueprint
from src.research.pdf_export import render_research_pdf
from src.risk.alerts import evaluate_market_risks, evaluate_symbol_risk, summarize_alerts
from src.storage.repository import AgentReportRepository, TrackedSymbolRepository

app = FastAPI(
    title="AI Investment Research API",
    version="0.2.0",
    description="Local-first API for multi-market AI investment research.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3001",
    ],
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1):\d+",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class SymbolCreate(BaseModel):
    symbol: str
    name: str | None = None
    exchange: str | None = None
    sector: str = ""


class ReportDeleteRequest(BaseModel):
    ids: list[int]


class AssistantRequest(BaseModel):
    provider_id: str | None = None
    use_llm: bool = False
    period: str = "6mo"
    question: str = ""
    language: str = "zh"


def _db_path() -> str:
    settings = get_settings()
    return settings.operational_db_path


def _symbol_repo() -> TrackedSymbolRepository:
    repo = TrackedSymbolRepository(_db_path())
    repo.create_tables()
    return repo


def _report_repo() -> AgentReportRepository:
    repo = AgentReportRepository(_db_path())
    repo.create_tables()
    return repo


@app.get("/api/health")
def health() -> dict[str, Any]:
    dal = get_dal()
    return {
        "status": "ok",
        "version": app.version,
        "providers": dal.provider_names(),
        "database": _db_path(),
    }


@app.get("/api/models")
def models() -> dict[str, Any]:
    return {"providers": [provider.public_dict() for provider in provider_catalog()]}


@app.get("/api/market/overview")
def market_overview() -> dict[str, Any]:
    repo = _symbol_repo()
    dal = get_dal()
    symbols = repo.get_active()
    quotes = []
    with ThreadPoolExecutor(max_workers=6) as executor:
        future_map = {
            executor.submit(dal.get_quotes, item.symbol): item.symbol
            for item in symbols[:12]
        }
        for future in as_completed(future_map):
            try:
                quotes.append(future.result())
            except Exception as exc:
                quotes.append({"symbol": future_map[future], "error": str(exc)})
    try:
        indices = fetch_all_indices()
    except Exception:
        indices = []
    try:
        news = fetch_financial_news(max_items=18)
    except Exception:
        news = []
    return {
        "indices": indices,
        "news": news,
        "watchlist": [serialize_symbol(item) for item in symbols],
        "quotes": quotes,
        "sectors": build_sector_summary(symbols, quotes),
        "ratings": build_rating_summary(),
    }


@app.get("/api/news")
def news(symbol: str | None = None, limit: int = 30) -> dict[str, Any]:
    return {
        "items": fetch_financial_news(symbol=symbol, max_items=max(1, min(limit, 80))),
        "symbol": symbol,
    }


@app.get("/api/strategy/research")
def strategy_research(limit: int = 6) -> dict[str, Any]:
    return collect_strategy_research(max_items_per_section=max(1, min(limit, 12)))


@app.get("/api/workflow/blueprint")
def workflow_design_blueprint() -> dict[str, Any]:
    return workflow_blueprint()


@app.get("/api/risk/alerts")
def risk_alerts(limit: int = 12, period: str = "6mo") -> dict[str, Any]:
    symbols = _symbol_repo().get_active()
    result = evaluate_market_risks(symbols, limit=max(1, min(limit, 50)), period=period)
    return jsonable_encoder(result)


@app.get("/api/risk/alerts/{symbol}")
def symbol_risk_alerts(symbol: str, period: str = "6mo") -> dict[str, Any]:
    normalized = normalize_symbol(symbol)
    alerts = evaluate_symbol_risk(normalized, period=period)
    return {
        "symbol": normalized,
        "market": detect_market(normalized),
        "alerts": jsonable_encoder(alerts),
        "summary": summarize_alerts(alerts),
    }


@app.get("/api/symbols")
def list_symbols() -> dict[str, Any]:
    return {"symbols": [serialize_symbol(item) for item in _symbol_repo().get_active()]}


@app.post("/api/symbols")
def add_symbol(payload: SymbolCreate) -> dict[str, Any]:
    symbol = payload.symbol.strip().upper()
    if not symbol:
        raise HTTPException(status_code=400, detail="symbol is required")
    market = _detect_exchange_for_symbol(symbol, payload.exchange)
    normalized = normalize_symbol(symbol, "ashare" if market in {"SSE", "SZSE", "ashare"} else market)
    _symbol_repo().add(
        symbol=normalized,
        name=payload.name or normalized,
        exchange=market,
        sector=payload.sector,
    )
    return {"symbol": normalized, "status": "active"}


@app.get("/api/symbols/compare")
def compare_symbols(symbols: str, period: str = "6mo") -> dict[str, Any]:
    raw_symbols = [
        part.strip().upper()
        for chunk in symbols.splitlines()
        for part in chunk.replace("，", ",").replace("、", ",").replace(";", ",").split(",")
        if part.strip()
    ]
    normalized_symbols = []
    for item in raw_symbols:
        normalized = normalize_symbol(item)
        if normalized not in normalized_symbols:
            normalized_symbols.append(normalized)
    normalized_symbols = normalized_symbols[:10]
    if len(normalized_symbols) < 2:
        raise HTTPException(status_code=400, detail="At least two symbols are required")

    dal = get_dal()
    profiles: dict[str, dict[str, Any]] = {}
    with ThreadPoolExecutor(max_workers=min(6, len(normalized_symbols))) as executor:
        future_map = {
            executor.submit(dal.get_symbol_profile, symbol, period): symbol
            for symbol in normalized_symbols
        }
        for future in as_completed(future_map):
            symbol = future_map[future]
            try:
                profiles[symbol] = future.result()
            except Exception as exc:
                profiles[symbol] = {
                    "symbol": symbol,
                    "market": detect_market(symbol),
                    "quote": {"error": str(exc), "payload": []},
                    "fundamentals": {"error": str(exc), "payload": {}},
                    "history": {"error": str(exc), "payload": []},
                }

    report_repo = _report_repo()
    items = []
    for symbol in normalized_symbols:
        latest_rows = report_repo.get_latest(symbol, limit=1)
        latest_report = latest_rows[0] if latest_rows else None
        items.append(build_compare_item(profiles[symbol], latest_report))

    return {
        "generated_at": datetime.now().isoformat(),
        "period": period,
        "symbols": normalized_symbols,
        "items": items,
    }


@app.get("/api/symbols/{symbol}")
def symbol_profile(symbol: str, period: str = "6mo") -> dict[str, Any]:
    normalized = normalize_symbol(symbol)
    profile = get_dal().get_symbol_profile(normalized, period=period)
    if (
        profile["quote"].get("error")
        and profile["fundamentals"].get("error")
        and profile["history"].get("error")
    ):
        raise HTTPException(status_code=404, detail="No provider data available for symbol")
    return profile


@app.delete("/api/symbols/{symbol}")
def remove_symbol(symbol: str) -> dict[str, Any]:
    _symbol_repo().remove(normalize_symbol(symbol))
    return {"status": "removed", "symbol": normalize_symbol(symbol)}


@app.get("/api/research/runs")
def research_runs(limit: int = 50) -> dict[str, Any]:
    rows = _report_repo().list_recent(limit=limit)
    return {"runs": [serialize_report_summary(row) for row in rows]}


@app.delete("/api/research/runs/{report_id}")
def delete_research_run(report_id: int) -> dict[str, Any]:
    deleted = _report_repo().delete_by_id(report_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Research report not found")
    return {"status": "deleted", "id": report_id}


@app.post("/api/research/runs/delete")
def delete_research_runs(payload: ReportDeleteRequest) -> dict[str, Any]:
    ids = sorted({int(report_id) for report_id in payload.ids if int(report_id) > 0})
    if not ids:
        raise HTTPException(status_code=400, detail="ids are required")
    deleted = _report_repo().delete_many(ids)
    return {"status": "deleted", "requested": len(ids), "deleted": deleted, "ids": ids}


@app.get("/api/research/daily-reads")
def research_daily_reads(limit: int = 5) -> dict[str, Any]:
    return collect_daily_reads(max_items_per_section=max(1, min(limit, 10)))


@app.get("/api/research/{symbol}")
def latest_research(symbol: str) -> dict[str, Any]:
    normalized = normalize_symbol(symbol)
    rows = _report_repo().get_latest(normalized, limit=1)
    if not rows:
        raise HTTPException(status_code=404, detail="No research report found")
    return serialize_report(rows[0])


@app.get("/api/research/{symbol}/pdf")
def research_pdf(symbol: str, lang: str = "zh") -> Response:
    normalized = normalize_symbol(symbol)
    rows = _report_repo().get_latest(normalized, limit=1)
    if not rows:
        raise HTTPException(status_code=404, detail="No research report found")
    report = rows[0].content or {}
    pdf_bytes = render_research_pdf(report, lang="en" if lang == "en" else "zh")
    filename = f"{normalized}_research_report.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.post("/api/research/{symbol}")
def run_research(symbol: str, request: ResearchRequest | None = None) -> dict[str, Any]:
    request = request or ResearchRequest()
    normalized = normalize_symbol(symbol)
    report = run_research_pipeline(
        normalized,
        period=request.period,
        provider_id=request.provider_id,
        use_llm=request.use_llm,
        language=request.language,
    )
    content = report.model_dump(mode="json")
    repo = _report_repo()
    repo.save({
        "agent_name": "ResearchDirector",
        "run_id": report.run_id,
        "ticker": report.symbol,
        "report_type": "institutional_research",
        "content": content,
        "trigger_type": "manual",
    })
    return {"report": content}


@app.post("/api/assistant/{symbol}")
def assistant_analysis(symbol: str, request: AssistantRequest | None = None) -> dict[str, Any]:
    request = request or AssistantRequest()
    normalized = normalize_symbol(symbol)
    latest = _report_repo().get_latest(normalized, limit=1)
    if latest:
        content = latest[0].content or {}
    else:
        report = run_research_pipeline(
            normalized,
            period=request.period,
            provider_id=request.provider_id,
            use_llm=request.use_llm,
            language="en" if request.language == "en" else "zh",
        )
        content = report.model_dump(mode="json")
        _report_repo().save({
            "agent_name": "AgentAssistant",
            "run_id": report.run_id,
            "ticker": report.symbol,
            "report_type": "assistant_research",
            "content": content,
            "trigger_type": "assistant",
        })

    info = content.get("information_summary", {}) or {}
    evidence = content.get("research_evidence", {}) or {}
    macro = content.get("macro_context", {}) or {}
    risk_items = content.get("risk_alerts", []) or []
    rating = content.get("rating", "HOLD")
    evidence_count = sum(
        len(evidence.get(key, []) or [])
        for key in ["macro", "filings", "institutional_reports", "channel_analysis", "news"]
    )
    response = [
        f"信息收集员：{info.get('summary') or '已完成行情、基本面、公告/研报线索与新闻扫描。'}",
        "非结构观察：" + "；".join((info.get("unstructured_notes") or [])[:3]),
        f"宏观研究员：{macro.get('summary') or '宏观上下文仍需补充。'}",
        f"资料目录：本次收集 {evidence_count} 条公开证据，覆盖公告/年报、机构研报线索、宏观与渠道分析。",
        (
            "风险提醒员："
            + "；".join(
                f"{item.get('severity', 'info')} {item.get('title', '')}"
                for item in risk_items[:3]
                if isinstance(item, dict)
            )
        ),
        f"研究总监：当前研报评级 {rating}；本阶段不输出交易策略，先保证信息覆盖、证据链和基本面结论可靠。",
    ]
    if request.question:
        response.append(f"针对你的问题：{request.question}。以上判断优先基于当前结构化报告，不构成投资建议。")
    return {
        "symbol": normalized,
        "market": detect_market(normalized),
        "messages": [item for item in response if item and not item.endswith("：")],
        "report": content,
    }


def serialize_symbol(item) -> dict[str, Any]:
    return {
        "id": item.id,
        "symbol": item.symbol,
        "name": item.name,
        "exchange": item.exchange,
        "sector": item.sector,
        "active": bool(item.active),
        "added_at": item.added_at.isoformat() if item.added_at else None,
    }


def serialize_report(row) -> dict[str, Any]:
    return {
        "id": row.id,
        "agent_name": row.agent_name,
        "run_id": row.run_id,
        "ticker": row.ticker,
        "report_type": row.report_type,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "trigger_type": row.trigger_type,
        "content": jsonable_encoder(row.content),
    }


def serialize_report_summary(row) -> dict[str, Any]:
    content = row.content or {}
    rating = content.get("rating")
    confidence = content.get("confidence")
    return {
        "id": row.id,
        "run_id": row.run_id,
        "ticker": row.ticker,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "rating": rating,
        "confidence": confidence,
        "report_type": row.report_type,
        "trigger_type": row.trigger_type,
        "company_name": content.get("company_name"),
    }


def build_compare_item(profile: dict[str, Any], latest_report) -> dict[str, Any]:
    symbol = str(profile.get("symbol") or "")
    quote_result = profile.get("quote", {}) or {}
    fundamentals_result = profile.get("fundamentals", {}) or {}
    history_result = profile.get("history", {}) or {}
    quote = _first_payload(quote_result.get("payload"))
    fundamentals = fundamentals_result.get("payload") or {}
    if not isinstance(fundamentals, dict):
        fundamentals = {}
    raw_content = latest_report.content if latest_report else {}
    content = raw_content if isinstance(raw_content, dict) else {}
    key_metrics = content.get("key_metrics", {})
    company_name = (
        content.get("company_name")
        or quote.get("name")
        or fundamentals.get("name")
        or fundamentals.get("shortName")
        or symbol
    )
    errors = [
        str(result.get("error"))
        for result in [quote_result, fundamentals_result, history_result]
        if result.get("error")
    ]
    return {
        "symbol": symbol,
        "market": profile.get("market") or detect_market(symbol),
        "company_name": company_name,
        "currency": quote.get("currency") or fundamentals.get("currency"),
        "price": _first_number(quote.get("close"), quote.get("price"), key_metrics.get("current_price")),
        "change_pct": _first_number(quote.get("change_pct"), quote.get("pct_chg")),
        "volume": _first_number(quote.get("volume")),
        "market_cap": _first_number(
            key_metrics.get("market_cap"),
            fundamentals.get("market_cap"),
            fundamentals.get("marketCap"),
            fundamentals.get("总市值"),
        ),
        "pe_ratio": _first_number(
            key_metrics.get("pe_ratio"),
            fundamentals.get("pe_ratio"),
            fundamentals.get("trailingPE"),
            fundamentals.get("市盈率"),
        ),
        "pb_ratio": _first_number(
            key_metrics.get("pb_ratio"),
            fundamentals.get("pb_ratio"),
            fundamentals.get("priceToBook"),
            fundamentals.get("市净率"),
        ),
        "roe": _first_number(key_metrics.get("roe"), fundamentals.get("roe"), fundamentals.get("returnOnEquity")),
        "roa": _first_number(key_metrics.get("roa"), fundamentals.get("roa"), fundamentals.get("returnOnAssets")),
        "revenue_growth": _first_number(
            key_metrics.get("revenue_growth"),
            fundamentals.get("revenue_growth"),
            fundamentals.get("revenueGrowth"),
        ),
        "rating": content.get("rating") if isinstance(content, dict) else None,
        "confidence": content.get("confidence") if isinstance(content, dict) else None,
        "thesis": content.get("thesis") if isinstance(content, dict) else None,
        "latest_report_at": latest_report.created_at.isoformat() if latest_report and latest_report.created_at else None,
        "data_sources": {
            "quote": quote_result.get("source"),
            "fundamentals": fundamentals_result.get("source"),
            "history": history_result.get("source"),
            "report": latest_report.agent_name if latest_report else None,
        },
        "stale": bool(quote_result.get("stale") or fundamentals_result.get("stale") or history_result.get("stale")),
        "errors": errors,
    }


def _first_payload(payload: Any) -> dict[str, Any]:
    if isinstance(payload, list):
        for row in payload:
            if isinstance(row, dict):
                return row
        return {}
    return payload if isinstance(payload, dict) else {}


def _first_number(*values: Any) -> float | None:
    for value in values:
        if isinstance(value, bool) or value is None:
            continue
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            normalized = value.replace(",", "").replace("%", "").strip()
            if not normalized or normalized in {"-", "--", "None", "nan"}:
                continue
            try:
                return float(normalized)
            except ValueError:
                continue
    return None


def build_sector_summary(symbols, quotes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    quote_map = {str(item.get("symbol")): item for item in quotes if item.get("symbol")}
    groups: dict[str, dict[str, Any]] = {}
    for item in symbols:
        sector = item.sector or "未分类"
        group = groups.setdefault(sector, {
            "sector": sector,
            "count": 0,
            "symbols": [],
            "avg_change_pct": None,
            "positive": 0,
            "negative": 0,
        })
        group["count"] += 1
        quote = quote_map.get(item.symbol, {})
        change = quote.get("change_pct")
        group["symbols"].append({
            "symbol": item.symbol,
            "name": item.name,
            "exchange": item.exchange,
            "change_pct": change,
        })
        if isinstance(change, (int, float)):
            group.setdefault("_changes", []).append(float(change))
            if change >= 0:
                group["positive"] += 1
            else:
                group["negative"] += 1
    for group in groups.values():
        changes = group.pop("_changes", [])
        if changes:
            group["avg_change_pct"] = round(sum(changes) / len(changes), 2)
    return sorted(groups.values(), key=lambda value: (-value["count"], value["sector"]))


def build_rating_summary() -> dict[str, Any]:
    rows = _report_repo().list_recent(limit=200)
    latest_by_symbol: dict[str, dict[str, Any]] = {}
    for row in rows:
        if row.ticker in latest_by_symbol:
            continue
        content = row.content or {}
        latest_by_symbol[row.ticker] = {
            "symbol": row.ticker,
            "company_name": content.get("company_name"),
            "rating": content.get("rating", "HOLD"),
            "confidence": content.get("confidence", "low"),
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }
    buckets = {"BUY": [], "HOLD": [], "SELL": []}
    for item in latest_by_symbol.values():
        buckets.setdefault(item["rating"], []).append(item)
    return {
        "buckets": buckets,
        "counts": {key: len(value) for key, value in buckets.items()},
    }


def _detect_exchange_for_symbol(symbol: str, exchange: str | None) -> str:
    if exchange:
        return exchange
    if symbol.isdigit() and len(symbol) == 6:
        return "ashare"
    if symbol.isdigit() and len(symbol) == 5:
        return "hk"
    return "us"
