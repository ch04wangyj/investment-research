"""FastAPI application exposing market data, symbols, models, and research runs."""

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.encoders import jsonable_encoder
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from config.settings import get_settings
from src.agents.research.graph import run_research_pipeline
from src.core.llm import provider_catalog
from src.data.dal import get_dal, normalize_symbol
from src.data.indices import fetch_all_indices
from src.data.news_fetcher import fetch_financial_news
from src.research.schemas import ResearchRequest
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
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class SymbolCreate(BaseModel):
    symbol: str
    name: str | None = None
    exchange: str | None = None
    sector: str = ""


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
        news = fetch_financial_news(max_items=8)
    except Exception:
        news = []
    return {
        "indices": indices,
        "news": news,
        "watchlist": [serialize_symbol(item) for item in symbols],
        "quotes": quotes,
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


@app.get("/api/research/{symbol}")
def latest_research(symbol: str) -> dict[str, Any]:
    normalized = normalize_symbol(symbol)
    rows = _report_repo().get_latest(normalized, limit=1)
    if not rows:
        raise HTTPException(status_code=404, detail="No research report found")
    return serialize_report(rows[0])


@app.post("/api/research/{symbol}")
def run_research(symbol: str, request: ResearchRequest | None = None) -> dict[str, Any]:
    request = request or ResearchRequest()
    normalized = normalize_symbol(symbol)
    report = run_research_pipeline(
        normalized,
        period=request.period,
        provider_id=request.provider_id,
        use_llm=request.use_llm,
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


def _detect_exchange_for_symbol(symbol: str, exchange: str | None) -> str:
    if exchange:
        return exchange
    if symbol.isdigit() and len(symbol) == 6:
        return "ashare"
    if symbol.isdigit() and len(symbol) == 5:
        return "hk"
    return "us"
