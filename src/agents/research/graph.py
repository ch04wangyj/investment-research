"""LangGraph multi-agent research pipeline.

The implementation borrows the shape of public trading-agent systems without
copying code: specialist analysts produce typed sections, then a research
director synthesizes a single Pydantic ResearchReport.
"""

import json
import re
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from langgraph.graph import END, StateGraph
from typing_extensions import TypedDict

from config.settings import get_settings
from src.analysis.technical import compute_technical_snapshot
from src.core.llm import create_chat_model
from src.data.dal import detect_market, get_dal, normalize_symbol
from src.data.news_fetcher import fetch_financial_news, is_company_news_item
from src.research.schemas import (
    AnalystView,
    DataSource,
    InformationSummary,
    InstitutionalNarrative,
    PipelineDiagnostics,
    ResearchEvidenceBook,
    ResearchReport,
    RiskAlert,
    TradingStrategy,
)
from src.research.source_collector import collect_research_evidence
from src.research.intelligence import retrieve_research_context
from src.risk.alerts import evaluate_symbol_risk_from_payload, risk_penalty


class ResearchState(TypedDict, total=False):
    symbol: str
    symbols: list[str]  # multi-symbol fan-out mode
    market: str
    period: str
    run_id: str
    provider_id: str | None
    use_llm: bool
    language: str
    quote: dict[str, Any]
    fundamentals: dict[str, Any]
    history: list[dict[str, Any]]
    news: list[dict[str, Any]]
    sources: list[dict[str, Any]]
    evidence_book: ResearchEvidenceBook
    information_summary: InformationSummary
    macro_context: AnalystView
    valuation: AnalystView
    financial_quality: AnalystView
    technical: AnalystView
    sentiment: AnalystView
    risk_alerts: list[RiskAlert]
    bull_case: list[str]
    bear_case: list[str]
    trading_strategy: TradingStrategy
    institutional_narrative: InstitutionalNarrative
    report: ResearchReport
    llm_status: str
    errors: list[str]
    # Fan-out internals
    _collected: dict[str, dict[str, Any]]  # symbol -> partial state


def build_research_graph(parallel: bool = False):
    workflow = StateGraph(ResearchState)

    if parallel:
        workflow.add_node("ParallelDataCollector", parallel_data_collector)
        # Sequential stages after aggregation
        workflow.add_node("ResearchSourceCollector", research_source_collector)
        workflow.add_node("InformationSummarizer", information_summarizer)
        workflow.add_node("MacroAnalyst", macro_analyst)
        workflow.add_node("FundamentalAnalyst", fundamental_analyst)
        workflow.add_node("TechnicalAnalyst", technical_analyst)
        workflow.add_node("NewsSentimentAnalyst", news_sentiment_analyst)
        workflow.add_node("RiskMonitor", risk_monitor)
        workflow.add_node("BullResearcher", bull_researcher)
        workflow.add_node("BearResearcher", bear_researcher)
        workflow.add_node("InstitutionalReportEditor", institutional_report_editor)
        workflow.add_node("ResearchDirector", research_director)

        workflow.set_entry_point("ParallelDataCollector")
        workflow.add_edge("ParallelDataCollector", "ResearchSourceCollector")
    else:
        workflow.add_node("DataCollector", data_collector)
        workflow.add_node("ResearchSourceCollector", research_source_collector)
        workflow.add_node("InformationSummarizer", information_summarizer)
        workflow.add_node("MacroAnalyst", macro_analyst)
        workflow.add_node("FundamentalAnalyst", fundamental_analyst)
        workflow.add_node("TechnicalAnalyst", technical_analyst)
        workflow.add_node("NewsSentimentAnalyst", news_sentiment_analyst)
        workflow.add_node("RiskMonitor", risk_monitor)
        workflow.add_node("BullResearcher", bull_researcher)
        workflow.add_node("BearResearcher", bear_researcher)
        workflow.add_node("InstitutionalReportEditor", institutional_report_editor)
        workflow.add_node("ResearchDirector", research_director)

        workflow.set_entry_point("DataCollector")
        workflow.add_edge("DataCollector", "ResearchSourceCollector")

    workflow.add_edge("ResearchSourceCollector", "InformationSummarizer")
    workflow.add_edge("InformationSummarizer", "FundamentalAnalyst")
    workflow.add_edge("InformationSummarizer", "MacroAnalyst")
    workflow.add_edge("InformationSummarizer", "TechnicalAnalyst")
    workflow.add_edge("InformationSummarizer", "NewsSentimentAnalyst")
    workflow.add_edge("NewsSentimentAnalyst", "RiskMonitor")
    workflow.add_edge(["FundamentalAnalyst", "TechnicalAnalyst", "MacroAnalyst", "RiskMonitor"], "BullResearcher")
    workflow.add_edge(["FundamentalAnalyst", "TechnicalAnalyst", "MacroAnalyst", "RiskMonitor"], "BearResearcher")
    workflow.add_edge(["BullResearcher", "BearResearcher"], "InstitutionalReportEditor")
    workflow.add_edge("InstitutionalReportEditor", "ResearchDirector")
    workflow.add_edge("ResearchDirector", END)
    return workflow.compile(name="InstitutionalResearchPipeline")


def run_research_pipeline(
    symbol: str,
    *,
    symbols: list[str] | None = None,
    period: str = "6mo",
    provider_id: str | None = None,
    use_llm: bool = False,
    language: str = "zh",
) -> ResearchReport:
    market = detect_market(symbol)
    normalized = normalize_symbol(symbol, market)
    use_parallel = symbols is not None and len(symbols) > 1
    graph = build_research_graph(parallel=use_parallel)
    initial_state: dict[str, Any] = {
        "symbol": normalized,
        "market": market,
        "period": period,
        "run_id": str(uuid.uuid4()),
        "provider_id": provider_id,
        "use_llm": use_llm,
        "language": "en" if language == "en" else "zh",
        "errors": [],
    }
    if use_parallel:
        initial_state["symbols"] = symbols
    state = graph.invoke(initial_state)
    return state["report"]


def data_collector(state: ResearchState) -> dict[str, Any]:
    bundle = _fetch_market_data_bundle(state["symbol"], state.get("period", "6mo"))
    return {
        **bundle,
        "errors": list(state.get("errors", [])) + bundle["errors"],
    }


def _fetch_market_data_bundle(symbol: str, period: str) -> dict[str, Any]:
    dal = get_dal()
    calls = {
        "quote": lambda: dal.get_quote_result(symbol),
        "fundamentals": lambda: dal.get_fundamentals_result(symbol),
        "history": lambda: dal.get_history_result(symbol, period),
    }
    results: dict[str, Any] = {}
    with ThreadPoolExecutor(max_workers=3) as executor:
        future_map = {executor.submit(call): label for label, call in calls.items()}
        for future, label in future_map.items():
            try:
                results[label] = future.result()
            except Exception as exc:
                from src.data.providers.base import ProviderResult

                results[label] = ProviderResult.failure(source=label, error=str(exc))

    errors = []
    for label in ["quote", "fundamentals", "history"]:
        result = results[label]
        if result.error:
            errors.append(f"{label}: {result.error}")

    quote_payload = results["quote"].payload
    quote = quote_payload[0] if isinstance(quote_payload, list) and quote_payload else {}
    fundamentals = results["fundamentals"].payload if isinstance(results["fundamentals"].payload, dict) else {}
    history = results["history"].payload if isinstance(results["history"].payload, list) else []
    sources = [
        results["quote"].to_dict(),
        results["fundamentals"].to_dict(),
        results["history"].to_dict(),
    ]
    return {
        "quote": quote,
        "fundamentals": fundamentals,
        "history": history,
        "sources": sources,
        "errors": errors,
    }


# ── Fan-out parallel data collection (Phase 4) ──

def parallel_data_collector(state: ResearchState) -> dict[str, Any]:
    """Collect multiple symbols concurrently and keep the first as report anchor.

    Cross-symbol synthesis is intentionally delegated to the comparison engine.
    This node only fans out provider I/O while preserving a valid LangGraph
    state update for the single-report research pipeline.
    """
    symbols = state.get("symbols", [state.get("symbol", "")])
    normalized_symbols = [
        normalize_symbol(symbol, detect_market(symbol))
        for symbol in symbols
        if symbol
    ]
    if not normalized_symbols:
        normalized_symbols = [state["symbol"]]

    bundles: dict[str, dict[str, Any]] = {}
    with ThreadPoolExecutor(max_workers=min(6, len(normalized_symbols))) as executor:
        future_map = {
            executor.submit(_fetch_market_data_bundle, symbol, state.get("period", "6mo")): symbol
            for symbol in normalized_symbols
        }
        for future, symbol in future_map.items():
            try:
                bundles[symbol] = future.result()
            except Exception as exc:
                bundles[symbol] = {
                    "quote": {},
                    "fundamentals": {},
                    "history": [],
                    "sources": [],
                    "errors": [str(exc)],
                }

    primary = normalized_symbols[0]
    primary_bundle = bundles[primary]
    all_errors = [
        f"{symbol}/{error}"
        for symbol, bundle in bundles.items()
        for error in bundle.get("errors", [])
    ]
    all_sources = [
        source
        for bundle in bundles.values()
        for source in bundle.get("sources", [])
    ]
    return {
        "symbol": primary,
        "symbols": normalized_symbols,
        "market": detect_market(primary),
        "quote": primary_bundle["quote"],
        "fundamentals": primary_bundle["fundamentals"],
        "history": primary_bundle["history"],
        "sources": all_sources,
        "errors": list(state.get("errors", [])) + all_errors,
        "_collected": bundles,
    }


def _fan_out_send(state: ResearchState) -> list:
    """Conditional edge: fan out from ParallelDataCollector to N CollectSingle nodes."""
    return parallel_data_collector(state)


def _collect_single(state: ResearchState) -> dict[str, Any]:
    """Collect data for one symbol (extracted from data_collector logic)."""
    symbol = state["symbol"]
    bundle = _fetch_market_data_bundle(symbol, state.get("period", "6mo"))
    errors = list(state.get("errors", [])) + [f"{symbol}/{item}" for item in bundle["errors"]]
    return {
        "_collected": {
            symbol: {
                "quote": bundle["quote"],
                "fundamentals": bundle["fundamentals"],
                "history": bundle["history"],
                "sources": bundle["sources"],
                "errors": errors,
            }
        }
    }


def aggregate_collected_data(states: list[dict[str, Any]]) -> dict[str, Any]:
    """Merge per-symbol collected data back into ResearchState.

    When using Send, LangGraph passes accumulated state chunks.
    This function combines all _collected entries.
    """
    # states is a list of partial state dicts from each CollectSingle invocation
    combined_quote = {}
    combined_fundamentals = {}
    combined_history = {}
    all_sources = []
    all_errors = []

    all_symbols = []
    for partial in states:
        collected = partial.get("_collected", {})
        for sym, data in collected.items():
            all_symbols.append(sym)
            combined_quote[sym] = data.get("quote", {})
            combined_fundamentals[sym] = data.get("fundamentals", {})
            combined_history[sym] = data.get("history", [])
            all_sources.extend(data.get("sources", []))
            all_errors.extend(data.get("errors", []))

    # For single-symbol analysis (the rest of the pipeline),
    # use the first symbol's data as the primary
    symbols = all_symbols
    primary = symbols[0] if symbols else ""

    return {
        "quote": combined_quote.get(primary, {}),
        "fundamentals": combined_fundamentals.get(primary, {}),
        "history": combined_history.get(primary, []),
        "sources": all_sources,
        "errors": all_errors,
        "symbols": symbols,
        "symbol": primary,
        "market": detect_market(primary) if primary else "us",
    }


def research_source_collector(state: ResearchState) -> dict[str, Any]:
    """Collect public research evidence before synthesis.

    This is the core research-first step: public filings, existing report
    metadata, macro context, and cross-channel analysis are gathered in
    parallel and stored as typed evidence rather than being folded into a
    free-form prompt.
    """
    fundamentals = state.get("fundamentals", {})
    quote = state.get("quote", {})
    company_name = str(
        fundamentals.get("company_name")
        or quote.get("name")
        or state.get("symbol", "")
    )
    sector = str(fundamentals.get("sector") or quote.get("sector") or "")
    try:
        evidence_book = collect_research_evidence(
            state["symbol"],
            state["market"],
            company_name=company_name,
            sector=sector,
        )
        intelligence_items = retrieve_research_context(
            " ".join(item for item in [state["symbol"], company_name, sector] if item),
            limit=get_settings().intelligence_context_items,
        )
        if intelligence_items:
            evidence_book = evidence_book.model_copy(
                update={
                    "channel_analysis": [
                        *intelligence_items,
                        *evidence_book.channel_analysis,
                    ][:10],
                }
            )
        errors = list(state.get("errors", [])) + [
            f"evidence: {item}" for item in evidence_book.errors
        ]
    except Exception as exc:
        evidence_book = ResearchEvidenceBook(errors=[str(exc)])
        errors = list(state.get("errors", [])) + [f"evidence: {exc}"]
    return {"evidence_book": evidence_book, "errors": errors}


def information_summarizer(state: ResearchState) -> dict[str, Any]:
    """Collect structured facts and non-structured notes for downstream agents."""
    quote = state.get("quote", {})
    fundamentals = state.get("fundamentals", {})
    history = state.get("history", [])
    sources = state.get("sources", [])
    evidence_book = state.get("evidence_book") or ResearchEvidenceBook()

    facts = [
        f"Symbol: {state['symbol']}, Market: {state['market']}",
        f"Latest close: {quote.get('close')}" if quote.get("close") is not None else "Latest close: N/A",
        f"Change: {quote.get('change_pct'):.2f}%" if isinstance(quote.get("change_pct"), (int, float)) else "Change: N/A",
        f"History samples: {len(history)} bars",
    ]
    for key, label in [
        ("pe_ratio", "PE"),
        ("pb_ratio", "PB"),
        ("roe", "ROE"),
        ("market_cap", "Market Cap"),
        ("sector", "Sector"),
    ]:
        if fundamentals.get(key) is not None:
            facts.append(f"{label}: {fundamentals.get(key)}")
    facts.append(f"External research evidence: {evidence_book.total_items} public items")
    if evidence_book.filings:
        facts.append(f"Primary filing candidate: {evidence_book.filings[0].title}")
    if evidence_book.institutional_reports:
        facts.append(f"Institutional report candidate: {evidence_book.institutional_reports[0].title}")

    notes = []
    if history:
        first = _num(history[0].get("close"))
        last = _num(history[-1].get("close"))
        if first and last:
            notes.append(f"Period price change {(last / first - 1) * 100:.1f}% for momentum assessment.")
    if quote.get("name") or fundamentals.get("company_name"):
        notes.append(f"Company: {fundamentals.get('company_name') or quote.get('name')}")
    for item in evidence_book.channel_analysis[:3]:
        notes.append(f"Channel analysis: {item.title}")
    for item in evidence_book.macro[:3]:
        notes.append(f"Macro context: {item.title}")
    notes.append("Research-first workflow: evidence collection, macro/fundamental analysis, challenge review, director synthesis.")

    gaps = []
    if not quote:
        gaps.append("Quote data missing")
    if not fundamentals or not any(fundamentals.get(k) is not None for k in ["pe_ratio", "pb_ratio", "roe"]):
        gaps.append("Valuation or profitability indicators incomplete")
    if len(history) < 40:
        gaps.append(f"Historical price sample is short ({len(history)} bars)")
    if not evidence_book.filings:
        gaps.append("Primary filing or annual-report source not found")
    if not evidence_book.institutional_reports:
        gaps.append("Public institutional research report source not found")
    for item in sources:
        if item.get("error"):
            gaps.append(f"{item.get('source')}: {item.get('error')}")
    for item in evidence_book.errors:
        gaps.append(f"Evidence search: {item}")

    summary = "; ".join(facts[:4])
    return {
        "information_summary": InformationSummary(
            structured_facts=facts,
            unstructured_notes=notes,
            data_gaps=gaps[:6],
            source_count=len([item for item in sources if item.get("payload") is not None])
            + evidence_book.total_items,
            summary=summary,
        )
    }


def fundamental_analyst(state: ResearchState) -> dict[str, Any]:
    from config.settings import get_settings
    cfg = get_settings().strategy
    lang = "en" if state.get("language") == "en" else "zh"

    fundamentals = state.get("fundamentals", {})
    pe = _num(fundamentals.get("pe_ratio"))
    forward_pe = _num(fundamentals.get("forward_pe"))
    pb = _num(fundamentals.get("pb_ratio"))
    roe = _normalize_roe(fundamentals.get("roe"))
    roa = _normalize_roe(fundamentals.get("roa"))
    profit_margin = _normalize_roe(fundamentals.get("profit_margins"))
    revenue_growth = _normalize_roe(fundamentals.get("revenue_growth"))
    earnings_growth = _normalize_roe(fundamentals.get("earnings_growth"))

    valuation_score = 50.0
    valuation_evidence = []
    if pe is not None:
        valuation_evidence.append(f"PE {pe:.1f}")
        valuation_score += (
            cfg.valuation_pe_bonus if 0 < pe < cfg.pe_low
            else (-cfg.valuation_pe_penalty if pe > cfg.pe_high else 0)
        )
    if forward_pe is not None:
        valuation_evidence.append(f"Forward PE {forward_pe:.1f}")
        if pe is not None and 0 < forward_pe < pe:
            valuation_score += 4
    if pb is not None:
        valuation_evidence.append(f"PB {pb:.2f}")
        valuation_score += (
            cfg.valuation_pb_bonus if 0 < pb < cfg.pb_low
            else (-cfg.valuation_pb_penalty if pb > cfg.pb_high else 0)
        )
    if fundamentals.get("market_cap") is not None:
        valuation_evidence.append(f"Market cap {_compact_number(fundamentals.get('market_cap'))}")
    valuation_score = _clamp(valuation_score)

    quality_score = 50.0
    quality_evidence = []
    if roe is not None:
        quality_evidence.append(f"ROE {roe * 100:.1f}%")
        quality_score += 20 if roe >= cfg.roe_high else (-15 if roe < cfg.roe_low else 0)
    if roa is not None:
        quality_evidence.append(f"ROA {roa * 100:.1f}%")
        quality_score += 6 if roa >= 0.08 else 0
    if profit_margin is not None:
        quality_evidence.append(f"Net margin {profit_margin * 100:.1f}%")
        quality_score += 8 if profit_margin >= 0.15 else (-5 if profit_margin < 0.03 else 0)
    if revenue_growth is not None:
        quality_evidence.append(f"Revenue growth {revenue_growth * 100:.1f}%")
        quality_score += 6 if revenue_growth > 0.08 else (-4 if revenue_growth < 0 else 0)
    if earnings_growth is not None:
        quality_evidence.append(f"Earnings growth {earnings_growth * 100:.1f}%")
        quality_score += 6 if earnings_growth > 0.08 else (-4 if earnings_growth < 0 else 0)
    if fundamentals.get("net_income") is not None:
        quality_evidence.append(f"Net income {_compact_number(fundamentals.get('net_income'))}")
        quality_score += 5
    if fundamentals.get("revenue") is not None:
        quality_evidence.append(f"Revenue {_compact_number(fundamentals.get('revenue'))}")
    quality_score = _clamp(quality_score)

    valuation = AnalystView(
        summary=_valuation_summary(pe, pb, lang),
        score=valuation_score,
        evidence=valuation_evidence,
        data_quality="high" if valuation_evidence else "limited",
    )
    quality = AnalystView(
        summary=_quality_summary(roe, lang),
        score=quality_score,
        evidence=quality_evidence,
        data_quality="high" if quality_evidence else "limited",
    )
    return {"valuation": valuation, "financial_quality": quality}


def macro_analyst(state: ResearchState) -> dict[str, Any]:
    """Assess macro, policy, and cycle context from collected public evidence."""
    lang = "en" if state.get("language") == "en" else "zh"
    evidence_book = state.get("evidence_book") or ResearchEvidenceBook()
    evidence_items = evidence_book.macro[:4]
    news_items = [
        item for item in evidence_book.news
        if any(token in f"{item.title} {item.summary}".lower() for token in [
            "macro",
            "policy",
            "rates",
            "inflation",
            "gdp",
            "政策",
            "利率",
            "通胀",
            "财政",
            "周期",
        ])
    ][:3]
    all_items = evidence_items + news_items

    score = 50.0
    if len(evidence_items) >= 2:
        score += 8
    if any(item.quality == "primary" for item in evidence_items):
        score += 4
    risk_terms = ("recession", "slowdown", "tightening", "监管", "下行", "衰退", "收缩")
    if any(any(term in f"{item.title} {item.summary}".lower() for term in risk_terms) for item in all_items):
        score -= 6

    if evidence_items:
        summary = (
            f"Macro and policy context collected from {len(evidence_items)} public sources; "
            "treat this as directional background until primary macro data is added."
            if lang == "en"
            else f"已从 {len(evidence_items)} 条公开资料收集宏观与政策背景；在接入一手宏观数据前，该部分作为方向性背景。"
        )
    else:
        summary = (
            "Macro context is thin; director should lower confidence and rely more on company-level evidence."
            if lang == "en"
            else "宏观上下文证据偏薄，研究总监应下调置信度，并更多依赖公司层面证据。"
        )

    return {
        "macro_context": AnalystView(
            summary=summary,
            score=_clamp(score),
            evidence=[item.title for item in all_items[:6]],
            data_quality="high" if len(evidence_items) >= 4 else ("limited" if evidence_items else "missing"),
        )
    }


def technical_analyst(state: ResearchState) -> dict[str, Any]:
    from config.settings import get_settings
    cfg = get_settings().strategy

    snapshot = compute_technical_snapshot(state.get("history", []))
    indicators = snapshot.get("indicators", {})
    score = 50.0
    trend = indicators.get("trend")
    rsi = indicators.get("rsi_14")
    momentum = indicators.get("momentum_pct")
    if trend == "uptrend":
        score += cfg.trend_uptrend_bonus
    elif trend == "downtrend":
        score -= cfg.trend_downtrend_penalty
    if isinstance(rsi, (int, float)):
        if cfg.rsi_neutral_low <= rsi <= cfg.rsi_neutral_high:
            score += cfg.rsi_neutral_bonus
        elif rsi >= cfg.rsi_overbought:
            score -= cfg.rsi_overbought_penalty
        elif rsi <= cfg.rsi_oversold:
            score += cfg.rsi_oversold_bonus
    if isinstance(momentum, (int, float)):
        score += max(min(momentum / 2, 12), -12)

    view = AnalystView(
        summary=_technical_summary(snapshot, state.get("language", "zh")),
        score=_clamp(score),
        evidence=[f"{key}: {value}" for key, value in indicators.items() if value is not None],
        data_quality=snapshot["data_quality"],
    )
    return {"technical": view}


def _technical_summary(snapshot: dict[str, Any], language: str) -> str:
    if language == "en":
        return str(snapshot["summary"])
    indicators = snapshot.get("indicators", {})
    if not indicators:
        return "历史价格数据不足，暂无法形成完整价格背景判断。"
    trend = {
        "uptrend": "上升趋势",
        "downtrend": "下降趋势",
        "neutral": "中性趋势",
    }.get(indicators.get("trend"), "趋势未明")
    parts = [f"当前处于{trend}"]
    if indicators.get("momentum_pct") is not None:
        parts.append(f"所选周期动量 {float(indicators['momentum_pct']):.1f}%")
    if indicators.get("rsi_14") is not None:
        parts.append(f"RSI 为 {float(indicators['rsi_14']):.1f}")
    if indicators.get("annualized_volatility_pct") is not None:
        parts.append(f"年化波动率 {float(indicators['annualized_volatility_pct']):.1f}%")
    return "；".join(parts) + "。"


def news_sentiment_analyst(state: ResearchState) -> dict[str, Any]:
    lang = "en" if state.get("language") == "en" else "zh"
    evidence_book = state.get("evidence_book") or ResearchEvidenceBook()
    try:
        symbol = state.get("symbol", "")
        news = fetch_financial_news(symbol=symbol, max_items=8)
    except Exception as exc:
        news = []
        state.setdefault("errors", []).append(f"news: {exc}")

    company_news = [item for item in news if is_company_news_item(item)]
    evidence = [item.get("title", "") for item in company_news if item.get("title")]
    evidence.extend(item.title for item in evidence_book.channel_analysis[:4])
    evidence.extend(item.title for item in evidence_book.institutional_reports[:3])
    if evidence:
        summary = (
            f"Collected {len(evidence)} news, channel, and institutional-analysis signals."
            if lang == "en"
            else f"已收集 {len(evidence)} 条新闻、渠道观点和机构分析线索。"
        )
    else:
        summary = (
            "No fresh news or channel-analysis feed available."
            if lang == "en"
            else "暂未获取到新的新闻或渠道分析信号。"
        )
    score = min(62.0, 48.0 + len(evidence) * 2.0) if evidence else 43.0
    return {
        "sentiment": AnalystView(
            summary=summary,
            score=score,
            evidence=evidence[:5],
            data_quality="limited" if evidence else "missing",
        ),
        "news": company_news,
    }


def risk_monitor(state: ResearchState) -> dict[str, Any]:
    alerts = evaluate_symbol_risk_from_payload(
        symbol=state["symbol"],
        market=state["market"],
        quote=state.get("quote", {}),
        fundamentals=state.get("fundamentals", {}),
        history=state.get("history", []),
        sources=state.get("sources", []),
        news=state.get("news", []),
    )
    return {"risk_alerts": alerts}


BULL_SYSTEM_PROMPT = """You are an OPTIMISTIC senior investment analyst. Your job is to build the strongest possible BULL case.

Given the same data the research team has collected, identify upside potential:
- Undervaluation signals supported by collected multiples
- Improving fundamentals (rising ROE, margin expansion, revenue acceleration)
- Supportive macro, policy, or industry-cycle context
- Favorable public research, filings, sentiment, or overlooked catalysts
- Hidden assets, growth optionality, or turnaround potential

Rules:
- Base every argument on the supplied structured facts and evidence titles only
- Do NOT fabricate historical averages, peer comparisons, growth rates, forecasts, or causal claims
- Treat search-result titles as leads, not as verified full-text findings
- Quantify only with numbers explicitly present in the supplied context
- Acknowledge risks briefly but reframe as potential opportunities
- Output 2-4 concise evidence bullet points
- Rate your conviction from 0-100 based on data quality and signal strength

Return your analysis as a JSON object:
{"summary": "One-sentence bull thesis", "score": <0-100>, "evidence": ["point 1", "point 2", ...], "data_quality": "high"|"limited"|"missing"}"""

BEAR_SYSTEM_PROMPT = """You are a SKEPTICAL senior investment analyst. Your job is to build the strongest possible BEAR case.

Given the same data the research team has collected, identify downside risks:
- Overvaluation signals (high multiples, deteriorating growth supporting the premium)
- Weakening fundamentals (declining ROE, margin compression, rising leverage)
- Unfavorable macro, policy, or industry-cycle context
- Poor sentiment, competitive threats, regulatory headwinds, or weak public research support
- Hidden liabilities, execution risk, or structural decline

Rules:
- Base every argument on the supplied structured facts and evidence titles only
- Do NOT fabricate historical averages, peer comparisons, growth rates, forecasts, or causal claims
- Treat search-result titles as leads, not as verified full-text findings
- Quantify only with numbers explicitly present in the supplied context
- Acknowledge positive factors but explain why they may not materialize
- Output 2-4 concise evidence bullet points
- Rate your conviction from 0-100 based on data quality and signal strength

Return your analysis as a JSON object:
{"summary": "One-sentence bear thesis", "score": <0-100>, "evidence": ["point 1", "point 2", ...], "data_quality": "high"|"limited"|"missing"}"""


def _build_data_context(state: ResearchState) -> str:
    """Assemble a structured data context string for LLM analysts."""
    info = state.get("information_summary")
    evidence_book = state.get("evidence_book") or ResearchEvidenceBook()
    facts = info.structured_facts if info else []
    notes = info.unstructured_notes if info else []
    gaps = info.data_gaps if info else []

    parts = [
        f"## Stock: {state['symbol']} ({state['market']})",
        "",
        "### Structured Facts",
    ]
    parts.extend(f"- {f}" for f in facts)
    parts.extend(["", "### Analysis Scores"])
    for role, view in [
        ("Macro Context", state.get("macro_context")),
        ("Valuation", state.get("valuation")),
        ("Financial Quality", state.get("financial_quality")),
        ("Price Context", state.get("technical")),
        ("Sentiment", state.get("sentiment")),
    ]:
        if view:
            parts.append(f"- {role}: {view.score:.0f}/100 — {view.summary}")
    parts.extend(["", "### Public Research Evidence"])
    for label, items in [
        ("Macro", evidence_book.macro),
        ("Filings", evidence_book.filings),
        ("Institutional Reports", evidence_book.institutional_reports),
        ("Channel Analysis", evidence_book.channel_analysis),
        ("News", evidence_book.news),
    ]:
        if items:
            parts.append(f"{label}:")
            parts.extend(
                f"- {item.title} ({item.quality}, {item.source}) {item.url}"
                for item in items[:4]
            )
    if notes:
        parts.extend(["", "### Additional Notes"])
        parts.extend(f"- {n}" for n in notes)
    if gaps:
        parts.extend(["", "### Data Gaps"])
        parts.extend(f"- {g}" for g in gaps)
    if state.get("errors"):
        parts.extend(["", "### Provider Errors"])
        parts.extend(f"- {e}" for e in state["errors"])
    if state.get("risk_alerts"):
        parts.extend(["", "### Deterministic Risk Alerts"])
        parts.extend(
            f"- {alert.severity.upper()} / {alert.category}: {alert.title} — {alert.message}"
            for alert in state["risk_alerts"][:6]
        )

    return "\n".join(parts)


def _call_llm_analyst(
    state: ResearchState,
    system_prompt: str,
    role_name: str,
) -> AnalystView:
    """Call an LLM to produce an AnalystView from a specific perspective.

    Falls back to heuristic scoring if the LLM is unavailable or fails.
    """
    import json

    try:
        from src.core.llm import create_chat_model

        llm = create_chat_model(
            state.get("provider_id"), tier="quick", temperature=0.7
        )
        data_context = _build_data_context(state)
        language_rule = (
            "Write every prose field in concise professional English."
            if state.get("language") == "en"
            else "所有 prose 字段必须使用专业、克制的简体中文。"
        )
        response = llm.invoke([
            {"role": "system", "content": f"{system_prompt}\n\nLanguage rule: {language_rule}"},
            {"role": "user", "content": data_context},
        ])
        content = str(response.content)

        # Extract JSON from response
        json_match = None
        import re
        m = re.search(r"```json\s*(.*?)\s*```", content, re.DOTALL)
        if m:
            json_match = m.group(1)
        else:
            # Brace-depth tracking for bare JSON
            depth = 0
            start = None
            for i, ch in enumerate(content):
                if ch == "{":
                    if depth == 0:
                        start = i
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0 and start is not None:
                        json_match = content[start : i + 1]
                        break

        if json_match:
            parsed = json.loads(json_match)
            return AnalystView(
                summary=str(parsed.get("summary", "")),
                score=_clamp(float(parsed.get("score", 50))),
                evidence=[str(e) for e in parsed.get("evidence", [])[:4]],
                data_quality=parsed.get("data_quality", "limited"),
            )

    except Exception:
        from loguru import logger
        logger.warning(f"LLM {role_name} failed, falling back to heuristic")

    # Heuristic fallback
    return _analyst_heuristic(state, role_name)


def _analyst_heuristic(state: ResearchState, role: str) -> AnalystView:
    """Rule-based fallback when LLM is unavailable."""
    zh = state.get("language") != "en"
    if role == "BullResearcher":
        score = 50.0
        evidence = []
        if state["financial_quality"].score >= 60:
            evidence.append("财务质量筛查高于中性水平。" if zh else "Financial quality screens above neutral.")
            score += 10
        if state["valuation"].score >= 60:
            evidence.append("当前估值筛查结果相对合理。" if zh else "Valuation appears reasonable.")
            score += 10
        if state.get("macro_context") and state["macro_context"].score >= 58:
            evidence.append("宏观和政策背景未呈现明显逆风。" if zh else "Macro and policy context is not obviously hostile.")
            score += 8
        if state.get("evidence_book") and state["evidence_book"].institutional_reports:
            evidence.append("已有公开机构研报线索可供交叉核验。" if zh else "Public institutional report candidates are available for cross-checking.")
            score += 6
        if not evidence:
            evidence.append("上行空间依赖经营执行和情绪改善。" if zh else "Upside depends on execution and sentiment improvement.")
        return AnalystView(
            summary="基于现有资料形成看多论点。" if zh else "Bull case based on available data.",
            score=_clamp(score),
            evidence=evidence[:4],
            data_quality="limited",
        )
    else:  # BearResearcher
        score = 50.0
        evidence = []
        if state["valuation"].score <= 45:
            evidence.append("估值安全边际有限。" if zh else "Valuation leaves limited margin of safety.")
            score -= 10
        if state.get("macro_context") and state["macro_context"].score <= 45:
            evidence.append("宏观或政策背景偏弱，或证据支持不足。" if zh else "Macro or policy context is weak or insufficiently supported.")
            score -= 8
        if state["sentiment"].data_quality != "high":
            evidence.append("情绪资料覆盖仍不完整。" if zh else "Sentiment coverage is incomplete.")
            score -= 5
        if state.get("errors"):
            evidence.append("数据源错误降低了结论可靠性。" if zh else "Provider errors reduce reliability.")
            score -= 5
        severe_alerts = [
            alert for alert in state.get("risk_alerts", [])
            if alert.severity in {"critical", "warning"}
        ]
        for alert in severe_alerts[:2]:
            evidence.append(f"{alert.title}: {alert.message}")
            score -= 4 if alert.severity == "warning" else 8
        if not evidence:
            evidence.append("看空论点主要聚焦宏观与经营执行风险。" if zh else "Bear case centers on macro and execution risk.")
        return AnalystView(
            summary="基于现有资料形成看空论点。" if zh else "Bear case based on available data.",
            score=_clamp(score),
            evidence=evidence[:4],
            data_quality="limited",
        )


def bull_researcher(state: ResearchState) -> dict[str, Any]:
    if state.get("use_llm"):
        view = _call_llm_analyst(state, BULL_SYSTEM_PROMPT, "BullResearcher")
    else:
        view = _analyst_heuristic(state, "BullResearcher")
    view = view.model_copy(update={"evidence": _label_unverified_hypotheses(view.evidence, state.get("language", "zh"))})
    return {"bull_case": view.evidence, "_bull_view": view}


def bear_researcher(state: ResearchState) -> dict[str, Any]:
    if state.get("use_llm"):
        view = _call_llm_analyst(state, BEAR_SYSTEM_PROMPT, "BearResearcher")
    else:
        view = _analyst_heuristic(state, "BearResearcher")
    view = view.model_copy(update={"evidence": _label_unverified_hypotheses(view.evidence, state.get("language", "zh"))})
    return {"bear_case": view.evidence, "_bear_view": view}


def _label_unverified_hypotheses(arguments: list[str], language: str) -> list[str]:
    prefix = "[Unverified hypothesis] " if language == "en" else "[待验证假设] "
    return [argument if argument.startswith(prefix) else f"{prefix}{argument}" for argument in arguments]


def institutional_report_editor(state: ResearchState) -> dict[str, Any]:
    """Draft evidence-bounded narrative sections for the publication renderer."""

    fallback = _institutional_narrative_fallback(state)
    if not state.get("use_llm"):
        return {"institutional_narrative": fallback}

    language_instruction = (
        "Write in concise professional English. "
        if state.get("language") == "en"
        else "请使用专业、克制、清晰的简体中文，风格接近机构内部研报。"
    )
    prompt = f"""You are the InstitutionalReportEditor in a guarded multi-agent equity research workflow.
{language_instruction}
Use only the supplied facts, source leads, analyst scores, risk alerts, and Bull/Bear arguments.
Do not invent financial forecasts, policy events, target-price models, peer data, or source verification.
Treat Bull/Bear arguments as unverified hypotheses. Repeat them only when independently supported by supplied structured facts or evidence titles.
Never introduce historical averages, peer comparisons, profitability baselines, or causal claims unless explicitly present in the supplied context.
If evidence is thin, explicitly state the limitation. Distinguish verified structured data from public-search leads.
Write substantive paragraphs suitable for an institutional research archive. Return JSON only with these keys:
executive_summary, company_analysis, macro_analysis, valuation_analysis, technical_analysis,
catalyst_analysis, risk_analysis, evidence_notes.

{_build_data_context(state)}

### Bull Case
{json.dumps(state.get("bull_case", []), ensure_ascii=False)}

### Bear Case
{json.dumps(state.get("bear_case", []), ensure_ascii=False)}
"""
    try:
        llm = create_chat_model(state.get("provider_id"), tier="deep", temperature=0.2)
        response = llm.invoke(prompt)
        parsed = _extract_json_object(str(response.content))
        narrative = InstitutionalNarrative.model_validate(parsed)
        return {
            "institutional_narrative": _sanitize_institutional_narrative(
                narrative,
                fallback=fallback,
                language=state.get("language", "zh"),
            )
        }
    except Exception:
        from loguru import logger
        logger.warning("InstitutionalReportEditor failed, using deterministic narrative fallback")
        return {"institutional_narrative": fallback}


def _institutional_narrative_fallback(state: ResearchState) -> InstitutionalNarrative:
    info = state.get("information_summary") or InformationSummary()
    evidence_book = state.get("evidence_book") or ResearchEvidenceBook()
    alerts = state.get("risk_alerts", [])
    return InstitutionalNarrative(
        executive_summary=info.summary or "结构化资料已完成采集，仍需结合数据缺口审慎阅读。",
        company_analysis=(
            f"{state['financial_quality'].summary} {state['valuation'].summary} "
            f"当前公司层面判断基于 {len(evidence_book.filings)} 条披露线索和 "
            f"{len(evidence_book.institutional_reports)} 条公开机构研报线索。"
        ),
        macro_analysis=state["macro_context"].summary,
        valuation_analysis=(
            f"{state['valuation'].summary} 当前估值结论用于筛查和情景锚定；"
            "在盈利预测、自由现金流和可比公司数据未独立核验前，不输出 DCF 结论。"
        ),
        technical_analysis=state["technical"].summary,
        catalyst_analysis="；".join(_build_catalysts(state)[:5]),
        risk_analysis="；".join(_build_risks(state)[:6]),
        evidence_notes=(
            f"共收集 {evidence_book.total_items} 条外部资料线索。"
            f"数据缺口：{'；'.join(info.data_gaps[:5]) or '未识别额外缺口'}。"
            f"当前风险告警 {len(alerts)} 条。"
        ),
    )


_UNVERIFIED_EDITOR_CLAIM = re.compile(
    r"(?:"
    r"历史(?:均值|中枢|分位|低位|高位|心理)"
    r"|长期(?:均值|中枢)"
    r"|心理(?:低位|高位)"
    r"|同行(?:比较|对比|估值)"
    r"|同业(?:比较|对比|估值)"
    r"|行业平均"
    r"|已定价"
    r"|具备修复弹性"
    r"|必然"
    r"|确定性"
    r"|historical\s+(?:average|range|low|high|percentile)"
    r"|peer\s+(?:comparison|multiple|valuation)"
    r"|sector\s+average"
    r"|priced\s+in"
    r")",
    flags=re.IGNORECASE,
)
_EDITOR_CAVEAT = re.compile(
    r"(?:"
    r"缺少|尚缺|未(?:获得|接入|引入|核验|覆盖|识别|提供|披露)|无法|不能"
    r"|仅(?:能|作|作为|呈现)|需要|有待|仍待|若|可能|线索|标题|假设|不输出"
    r"|missing|without|not\s+available|cannot|could|may|if\s|lead|hypothesis|unverified"
    r")",
    flags=re.IGNORECASE,
)


def _sanitize_institutional_narrative(
    narrative: InstitutionalNarrative,
    *,
    fallback: InstitutionalNarrative,
    language: str,
) -> InstitutionalNarrative:
    """Drop unsupported comparative claims before they enter the publication archive."""

    clean: dict[str, str] = {}
    fallback_data = fallback.model_dump()
    removed = False
    for field, text in narrative.model_dump().items():
        kept = []
        for sentence in re.split(r"(?<=[。！？!?])\s*", str(text).strip()):
            if not sentence:
                continue
            if _UNVERIFIED_EDITOR_CLAIM.search(sentence) and not _EDITOR_CAVEAT.search(sentence):
                removed = True
                continue
            kept.append(sentence)
        clean[field] = "".join(kept).strip() or str(fallback_data.get(field, ""))

    if removed:
        note = (
            "Claim guard removed comparative or predictive statements that lacked independently verified evidence."
            if language == "en"
            else "证据约束层已过滤缺乏独立核验的历史比较、同行比较或预测性表述。"
        )
        clean["evidence_notes"] = f"{clean['evidence_notes']} {note}".strip()
    return InstitutionalNarrative.model_validate(clean)


def _extract_json_object(content: str) -> dict[str, Any]:
    """Extract one JSON object without trusting surrounding model prose."""

    fenced = content.strip()
    if fenced.startswith("```"):
        fenced = fenced.removeprefix("```json").removeprefix("```").strip()
        fenced = fenced.removesuffix("```").strip()
    try:
        parsed = json.loads(fenced)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    depth = 0
    start = None
    for index, char in enumerate(content):
        if char == "{":
            if depth == 0:
                start = index
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0 and start is not None:
                parsed = json.loads(content[start : index + 1])
                if isinstance(parsed, dict):
                    return parsed
    raise ValueError("LLM response did not contain a JSON object")


def trading_strategist(state: ResearchState) -> dict[str, Any]:
    from config.settings import get_settings
    cfg = get_settings().strategy

    composite = sum([
        state["valuation"].score,
        state["financial_quality"].score,
        state["technical"].score,
        state["sentiment"].score,
    ]) / 4
    alerts = state.get("risk_alerts", [])
    penalty = risk_penalty(alerts)
    composite = max(0.0, composite - penalty)
    quote = state.get("quote", {})
    current_price = _num(quote.get("close") or state.get("fundamentals", {}).get("current_price"))
    volatility = _extract_indicator(state["technical"].evidence, "annualized_volatility_pct")
    trend = "uptrend" if "trend: uptrend" in state["technical"].evidence else (
        "downtrend" if "trend: downtrend" in state["technical"].evidence else "neutral"
    )

    if composite >= cfg.accumulate_threshold and trend != "downtrend":
        action = "accumulate"
        position = cfg.accumulate_position_pct
    elif composite <= cfg.reduce_threshold_high or trend == "downtrend":
        action = "reduce"
        position = (
            cfg.reduce_min_position_pct
            if composite <= cfg.reduce_threshold_low
            else cfg.reduce_position_pct
        )
    elif composite < cfg.avoid_threshold:
        action = "avoid"
        position = 0.0
    else:
        action = "hold"
        position = cfg.hold_position_pct

    if any(alert.severity == "critical" for alert in alerts):
        action = "avoid" if action in {"accumulate", "hold"} else action
        position = min(position, cfg.reduce_position_pct)
    elif any(alert.severity == "warning" for alert in alerts):
        position = min(position, cfg.hold_position_pct)

    stop_loss = None
    take_profit = None
    entry_zone = "Wait for price to return to key MA or breakout with volume"
    if current_price is not None:
        risk_band = (
            cfg.risk_band_default if volatility is None
            else max(min(volatility / 300, cfg.risk_band_max), cfg.risk_band_min)
        )
        stop_loss = round(current_price * (1 - risk_band), 2)
        take_profit = round(current_price * (1 + risk_band * cfg.take_profit_multiplier), 2)
        low_entry = round(current_price * 0.98, 2)
        high_entry = round(current_price * 1.02, 2)
        entry_zone = f"{low_entry} - {high_entry}"

    rationale = [
        f"Composite score: {composite:.1f}",
        f"Technical trend: {trend}",
        f"Valuation/Quality/Technical/Sentiment: {state['valuation'].score:.0f}/{state['financial_quality'].score:.0f}/{state['technical'].score:.0f}/{state['sentiment'].score:.0f}",
    ]
    if penalty:
        rationale.append(f"Risk alert penalty: -{penalty:.0f} points")
    invalidation = [
        "Data sources fail consecutively or key financial indicators become incomplete",
        "Price breaks below stop-loss without fundamental improvement evidence",
        "Major policy, earnings, or liquidity events change original assumptions",
    ]
    invalidation.extend(alert.title for alert in alerts[:3])
    return {
        "trading_strategy": TradingStrategy(
            action=action,
            horizon="position",
            entry_zone=entry_zone,
            stop_loss=stop_loss,
            take_profit=take_profit,
            position_size_pct=position,
            rationale=rationale,
            invalidation=invalidation,
        )
    }


def research_director(state: ResearchState) -> dict[str, Any]:
    scores = [
        state["macro_context"].score,
        state["valuation"].score,
        state["financial_quality"].score,
        state["sentiment"].score,
    ]
    from config.settings import get_settings
    cfg = get_settings().strategy

    alerts = state.get("risk_alerts", [])
    penalty = risk_penalty(alerts)
    composite = max(0.0, sum(scores) / len(scores) - penalty)
    rating = "BUY" if composite >= cfg.buy_threshold else ("SELL" if composite <= cfg.sell_threshold else "HOLD")
    if any(alert.severity == "critical" for alert in alerts) and rating == "BUY":
        rating = "HOLD"
    confidence = "high" if not state.get("errors") and min(scores) >= 45 else "medium"
    if state.get("errors") or any(view.data_quality == "missing" for view in [
        state["macro_context"],
        state["valuation"],
        state["financial_quality"],
        state["sentiment"],
    ]):
        confidence = "low"
    if any(alert.severity == "critical" for alert in alerts):
        confidence = "low"
    elif any(alert.severity == "warning" for alert in alerts) and confidence == "high":
        confidence = "medium"

    quote = state.get("quote", {})
    fundamentals = state.get("fundamentals", {})
    current_price = _num(quote.get("close") or fundamentals.get("current_price"))
    price_target = _target_price(current_price, composite)
    company_name = (
        fundamentals.get("company_name")
        or quote.get("name")
        or state["symbol"]
    )
    thesis = _thesis(state, rating, composite)
    llm_status = "not_used"
    evidence_book = state.get("evidence_book") or ResearchEvidenceBook()

    # Synthesize LLM debate if bull/bear views exist
    bull_view = state.get("_bull_view")
    bear_view = state.get("_bear_view")
    if bull_view and bear_view:
        debate_summary = (
            f"Bull case ({bull_view.score:.0f}/100): {bull_view.summary} "
            f"Bear case ({bear_view.score:.0f}/100): {bear_view.summary}"
        )
        thesis = f"{thesis} {debate_summary}"

    if state.get("use_llm"):
        try:
            llm = create_chat_model(state.get("provider_id"), tier="deep", temperature=0.2)
            if bull_view and bear_view:
                language_instruction = (
                    "Write the final paragraph in fluent English. "
                    if state.get("language") == "en"
                    else "请用简体中文输出，语气对齐中金等卖方研报的专业摘要。"
                )
                polish_prompt = (
                    language_instruction
                    +
                    "Synthesize this bull/bear debate into one concise "
                    "institutional-style investment thesis paragraph. Focus on macro, "
                    "company fundamentals, filings, public research evidence, and risks. "
                    "Do not give trading tactics. "
                    f"Current rating: {rating}. Data: {thesis}"
                )
            else:
                language_instruction = (
                    "Write the final paragraph in fluent English. "
                    if state.get("language") == "en"
                    else "请用简体中文输出，语气对齐中金等卖方研报的专业摘要。"
                )
                polish_prompt = (
                    language_instruction
                    +
                    "Rewrite this investment thesis in one concise "
                    "institutional-style paragraph without changing facts. Focus on macro, "
                    "company fundamentals, filings, public research evidence, and risks. "
                    "Do not give trading tactics: "
                    f"{thesis}"
                )
            response = llm.invoke(polish_prompt)
            thesis = str(response.content).strip() or thesis
            llm_status = "used"
        except Exception as exc:
            llm_status = f"not_configured_or_failed: {exc}"

    sources = [
        DataSource(
            name=str(item.get("source", "unknown")),
            as_of=item.get("as_of"),
            stale=bool(item.get("stale", False)),
            error=item.get("error"),
        )
        for item in state.get("sources", [])
    ]
    for item in _flatten_evidence(evidence_book):
        sources.append(
            DataSource(
                name=item.source or item.quality,
                as_of=item.as_of,
                stale=False,
                error=None,
                url=item.url,
                channel=item.channel,
                quality=item.quality,
            )
        )

    report = ResearchReport(
        run_id=state["run_id"],
        symbol=state["symbol"],
        market=state["market"],
        company_name=str(company_name),
        rating=rating,
        confidence=confidence,
        current_price=current_price,
        price_target_6m=price_target,
        thesis=thesis,
        key_metrics={
            "composite_score": round(composite, 2),
            "risk_penalty": round(penalty, 2),
            "external_sources": evidence_book.total_items,
            "primary_sources": len([item for item in _flatten_evidence(evidence_book) if item.quality == "primary"]),
            "institutional_reports": len(evidence_book.institutional_reports),
            "pe_ratio": fundamentals.get("pe_ratio"),
            "forward_pe": fundamentals.get("forward_pe"),
            "pb_ratio": fundamentals.get("pb_ratio"),
            "roe": fundamentals.get("roe"),
            "roa": fundamentals.get("roa"),
            "market_cap": fundamentals.get("market_cap"),
            "revenue": fundamentals.get("revenue"),
            "net_income": fundamentals.get("net_income"),
            "profit_margins": fundamentals.get("profit_margins"),
            "revenue_growth": fundamentals.get("revenue_growth"),
            "earnings_growth": fundamentals.get("earnings_growth"),
            "sector": fundamentals.get("sector"),
            "industry": fundamentals.get("industry"),
            "latest_close": current_price,
        },
        valuation=state["valuation"],
        financial_quality=state["financial_quality"],
        macro_context=state["macro_context"],
        technical=state["technical"],
        sentiment=state["sentiment"],
        information_summary=state["information_summary"],
        research_evidence=evidence_book,
        trading_strategy=None,
        risk_alerts=alerts,
        pipeline_diagnostics=_build_pipeline_diagnostics(state, alerts, penalty),
        institutional_narrative=state.get("institutional_narrative", InstitutionalNarrative()),
        bull_case=state.get("bull_case", []),
        bear_case=state.get("bear_case", []),
        catalysts=_build_catalysts(state),
        risks=_build_risks(state),
        sources=sources,
        llm_status=llm_status,
        disclaimer=(
            "本报告由 AI 系统基于公开资料与本地数据生成，仅供个人研究使用，不构成任何投资建议。"
            if state.get("language") != "en"
            else "This report is generated for personal research only and is not investment advice."
        ),
        archive_history=state.get("history", []),
    )
    return {"report": report, "llm_status": llm_status}


def _valuation_summary(pe: float | None, pb: float | None, lang: str = "en") -> str:
    if pe is None and pb is None:
        return "Valuation data is incomplete." if lang == "en" else "估值数据不完整。"
    parts = []
    if pe is not None:
        parts.append(f"PE is {pe:.1f}" if lang == "en" else f"PE 为 {pe:.1f} 倍")
    if pb is not None:
        parts.append(f"PB is {pb:.2f}" if lang == "en" else f"PB 为 {pb:.2f} 倍")
    return ("; ".join(parts) + ".") if lang == "en" else "；".join(parts) + "。"


def _compact_number(value: Any) -> str:
    number = _num(value)
    if number is None:
        return "-"
    abs_number = abs(number)
    if abs_number >= 1_000_000_000_000:
        return f"{number / 1_000_000_000_000:.2f}T"
    if abs_number >= 1_000_000_000:
        return f"{number / 1_000_000_000:.2f}B"
    if abs_number >= 1_000_000:
        return f"{number / 1_000_000:.2f}M"
    return f"{number:,.2f}"


def _quality_summary(roe: float | None, lang: str = "en") -> str:
    if roe is None:
        return "Profitability data is incomplete." if lang == "en" else "盈利能力数据不完整。"
    if roe >= 0.18:
        return (
            f"ROE of {roe * 100:.1f}% indicates strong profitability."
            if lang == "en"
            else f"ROE 为 {roe * 100:.1f}%，盈利能力较强。"
        )
    if roe >= 0.08:
        return (
            f"ROE of {roe * 100:.1f}% indicates acceptable profitability."
            if lang == "en"
            else f"ROE 为 {roe * 100:.1f}%，盈利能力处于可接受区间。"
        )
    return (
        f"ROE of {roe * 100:.1f}% is below preferred quality thresholds."
        if lang == "en"
        else f"ROE 为 {roe * 100:.1f}%，低于偏好的财务质量阈值。"
    )


def _thesis(state: ResearchState, rating: str, composite: float) -> str:
    evidence_book = state.get("evidence_book") or ResearchEvidenceBook()
    if state.get("language") != "en":
        return (
            f"{state['symbol']} 当前评级为 {rating}，综合评分 {composite:.1f}。"
            f"结论综合考虑宏观周期（{state['macro_context'].score:.0f}）、估值（{state['valuation'].score:.0f}）、"
            f"财务质量（{state['financial_quality'].score:.0f}）和公开资料情绪（{state['sentiment'].score:.0f}）。"
            f"本次共收集 {evidence_book.total_items} 条外部证据用于审计，未覆盖项将下调置信度。"
        )
    return (
        f"{state['symbol']} receives a {rating} rating with a composite score of "
        f"{composite:.1f}. The conclusion balances macro context "
        f"({state['macro_context'].score:.0f}), valuation ({state['valuation'].score:.0f}), "
        f"financial quality ({state['financial_quality'].score:.0f}), and public-source "
        f"sentiment ({state['sentiment'].score:.0f}), with {evidence_book.total_items} "
        "external evidence items collected for audit."
    )


def _target_price(current_price: float | None, composite: float) -> float | None:
    if current_price is None:
        return None
    adjustment = max(min((composite - 50) / 100, 0.18), -0.18)
    return round(current_price * (1 + adjustment), 2)


def _normalize_roe(value: Any) -> float | None:
    numeric = _num(value)
    if numeric is None:
        return None
    return numeric / 100 if abs(numeric) > 10 else numeric


def _num(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _clamp(value: float) -> float:
    return max(0.0, min(100.0, round(value, 2)))


def _build_catalysts(state: ResearchState) -> list[str]:
    """Generate dynamic catalysts based on actual analysis results."""
    catalysts = []
    zh = state.get("language") != "en"
    macro = state.get("macro_context")
    val = state.get("valuation")
    quality = state.get("financial_quality")
    sentiment = state.get("sentiment")
    info = state.get("information_summary")
    evidence_book = state.get("evidence_book") or ResearchEvidenceBook()

    if macro and macro.score >= 58:
        catalysts.append(
            f"宏观和政策背景至少未形成明显逆风（评分：{macro.score:.0f}/100）"
            if zh
            else f"Macro/policy context is at least supportive (score: {macro.score:.0f}/100)"
        )
    if val and val.score >= 60:
        catalysts.append(
            f"估值筛查相对有利（评分：{val.score:.0f}/100），可继续核验潜在上行空间"
            if zh
            else f"Favorable valuation (score: {val.score:.0f}/100) supports upside potential"
        )
    if quality and quality.score >= 60:
        catalysts.append(
            f"财务质量指标高于阈值（评分：{quality.score:.0f}/100）"
            if zh
            else f"Financial quality metrics above threshold (score: {quality.score:.0f}/100)"
        )
    if sentiment and sentiment.evidence:
        first = sentiment.evidence[0]
        catalysts.append(f"市场情绪线索：{first[:120]}" if zh else f"Market sentiment: {first[:120]}")
    if evidence_book.filings:
        catalysts.append(
            f"待复核一手披露：{evidence_book.filings[0].title[:120]}"
            if zh
            else f"Primary filing to review: {evidence_book.filings[0].title[:120]}"
        )
    if evidence_book.institutional_reports:
        catalysts.append(
            f"待复核外部研报：{evidence_book.institutional_reports[0].title[:120]}"
            if zh
            else f"External report lead: {evidence_book.institutional_reports[0].title[:120]}"
        )
    if info and info.data_gaps:
        catalysts.append(
            "补齐数据覆盖后，可能识别更多上行信号"
            if zh
            else "Improved data coverage could reveal additional upside signals"
        )
    if not catalysts:
        catalysts.append(
            "财报或经营更新是当前需要跟踪的主要催化剂"
            if zh
            else "Earnings or operating updates are the primary catalyst to monitor"
        )
    return catalysts


def _build_risks(state: ResearchState) -> list[str]:
    """Generate dynamic risks based on actual analysis results."""
    risks = []
    zh = state.get("language") != "en"
    macro = state.get("macro_context")
    val = state.get("valuation")
    quality = state.get("financial_quality")
    sentiment = state.get("sentiment")
    info = state.get("information_summary")
    evidence_book = state.get("evidence_book") or ResearchEvidenceBook()

    if macro and macro.score < 45:
        risks.append(
            f"宏观、政策或周期背景偏弱，或证据不足（评分：{macro.score:.0f}/100）"
            if zh
            else f"Macro, policy, or cycle context is weak or poorly evidenced (score: {macro.score:.0f}/100)"
        )
    if val and val.score < 45:
        risks.append(
            f"估值偏高，安全边际有限（评分：{val.score:.0f}/100）"
            if zh
            else f"Elevated valuation leaves limited margin of safety (score: {val.score:.0f}/100)"
        )
    if quality and quality.score < 45:
        risks.append(
            f"盈利能力或财务质量低于平均水平（评分：{quality.score:.0f}/100）"
            if zh
            else f"Below-average profitability or financial quality (score: {quality.score:.0f}/100)"
        )
    if sentiment and sentiment.data_quality != "high":
        risks.append("情绪资料覆盖不完整，结论置信度需要下调" if zh else "Incomplete sentiment coverage reduces confidence")
    if not evidence_book.filings:
        risks.append("公开搜索未找到一手披露或年报来源" if zh else "No primary filing or annual-report source was found in public search")
    if not evidence_book.institutional_reports:
        risks.append("未找到公开机构研报来源" if zh else "No public institutional research report source was found")
    if info and info.data_gaps:
        gaps_text = ", ".join(info.data_gaps[:3])
        risks.append(f"数据缺口：{gaps_text}" if zh else f"Data gaps: {gaps_text}")
    if state.get("errors"):
        risks.append(
            f"{len(state['errors'])} 个数据源出现错误，结论可靠性下降"
            if zh
            else f"Provider errors in {len(state['errors'])} data source(s) reduce reliability"
        )
    for alert in state.get("risk_alerts", [])[:5]:
        risks.append(f"{alert.title}: {alert.message}")
    if not risks:
        risks.append("宏观与利率波动是主要外部风险" if zh else "Macro and rates volatility is the primary external risk")
    return risks


def _build_pipeline_diagnostics(
    state: ResearchState,
    alerts: list[RiskAlert],
    penalty: float,
) -> PipelineDiagnostics:
    controls = [
        "Bull and Bear researchers receive the same evidence book and produce opposing cases.",
        "ResearchDirector caps BUY ratings when critical deterministic risk alerts exist.",
        "Provider and public-source metadata, URLs, quality labels, and gaps are carried into the final report.",
        "Trading tactics are intentionally deferred; the current output is a research report, not a strategy signal.",
    ]
    if state.get("use_llm"):
        controls.append("LLM output is constrained by typed Pydantic report sections and deterministic scores.")
    return PipelineDiagnostics(
        topology="guarded_dag",
        latency_strategy=[
            "Quote, fundamentals, and history are fetched concurrently in DataCollector.",
            "Public filing, macro, report, and channel-analysis searches run in parallel and are cached for 6 hours.",
            "Macro, fundamental, price-context, and sentiment analysis branch after fact collection.",
            "RiskMonitor is deterministic and reuses collected payloads instead of another LLM call.",
        ],
        hallucination_controls=controls,
        validation_checks=[
            "Data gaps are surfaced before synthesis.",
            "Risk alerts impose a numeric penalty before rating.",
            "Final report stores market-data sources and public evidence links for auditability.",
        ],
        confidence_adjustments=[
            f"Risk penalty applied: {penalty:.0f} points.",
            f"Active risk alerts: {len(alerts)}.",
            f"Provider errors: {len(state.get('errors', []))}.",
        ],
    )


def _flatten_evidence(evidence_book: ResearchEvidenceBook) -> list:
    return [
        *evidence_book.macro,
        *evidence_book.filings,
        *evidence_book.institutional_reports,
        *evidence_book.channel_analysis,
        *evidence_book.news,
    ]


def _extract_indicator(evidence: list[str], key: str) -> float | None:
    prefix = f"{key}: "
    for item in evidence:
        if item.startswith(prefix):
            return _num(item.removeprefix(prefix))
    return None
