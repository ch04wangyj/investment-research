"""LangGraph multi-agent research pipeline.

The implementation borrows the shape of public trading-agent systems without
copying code: specialist analysts produce typed sections, then a research
director synthesizes a single Pydantic ResearchReport.
"""

import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from langgraph.graph import END, StateGraph
from typing_extensions import TypedDict

from src.analysis.technical import compute_technical_snapshot
from src.core.llm import create_chat_model
from src.data.dal import detect_market, get_dal, normalize_symbol
from src.data.news_fetcher import fetch_financial_news
from src.research.schemas import (
    AnalystView,
    DataSource,
    InformationSummary,
    PipelineDiagnostics,
    ResearchEvidenceBook,
    ResearchReport,
    RiskAlert,
    TradingStrategy,
)
from src.research.source_collector import collect_research_evidence
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
    report: ResearchReport
    llm_status: str
    errors: list[str]
    # Fan-out internals
    _collected: dict[str, dict[str, Any]]  # symbol -> partial state


def build_research_graph(parallel: bool = False):
    workflow = StateGraph(ResearchState)

    if parallel:
        workflow.add_node("ParallelDataCollector", parallel_data_collector)
        workflow.add_node("CollectSingle", _collect_single)
        workflow.add_node("AggregateData", aggregate_collected_data)
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
        workflow.add_node("ResearchDirector", research_director)

        workflow.set_entry_point("ParallelDataCollector")
        workflow.add_conditional_edges(
            "ParallelDataCollector",
            _fan_out_send,
            ["CollectSingle"],
        )
        workflow.add_edge("CollectSingle", "AggregateData")
        workflow.add_edge("AggregateData", "ResearchSourceCollector")
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
    workflow.add_edge(["BullResearcher", "BearResearcher"], "ResearchDirector")
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

def parallel_data_collector(state: ResearchState) -> list:
    """Fan-out entry: returns Send objects, one per symbol."""
    from langgraph.types import Send

    symbols = state.get("symbols", [state.get("symbol", "")])
    if not symbols:
        symbols = [state["symbol"]]
    return [
        Send("CollectSingle", {
            "symbol": sym,
            "market": state.get("market", ""),
            "period": state.get("period", "6mo"),
            "run_id": state.get("run_id", ""),
            "errors": list(state.get("errors", [])),
        })
        for sym in symbols
    ]


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
        summary=snapshot["summary"],
        score=_clamp(score),
        evidence=[f"{key}: {value}" for key, value in indicators.items() if value is not None],
        data_quality=snapshot["data_quality"],
    )
    return {"technical": view}


def news_sentiment_analyst(state: ResearchState) -> dict[str, Any]:
    lang = "en" if state.get("language") == "en" else "zh"
    evidence_book = state.get("evidence_book") or ResearchEvidenceBook()
    try:
        symbol = state.get("symbol", "")
        news = fetch_financial_news(symbol=symbol, max_items=8)
    except Exception as exc:
        news = []
        state.setdefault("errors", []).append(f"news: {exc}")

    evidence = [item.get("title", "") for item in news if item.get("title")]
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
        "news": news,
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
- Undervaluation signals (low multiples relative to peers/growth)
- Improving fundamentals (rising ROE, margin expansion, revenue acceleration)
- Supportive macro, policy, or industry-cycle context
- Favorable public research, filings, sentiment, or overlooked catalysts
- Hidden assets, growth optionality, or turnaround potential

Rules:
- Base every argument on the data provided — do NOT fabricate numbers
- Quantify when possible ("PE of 12x is a 30% discount to sector average")
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
- Base every argument on the data provided — do NOT fabricate numbers
- Quantify when possible
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
        response = llm.invoke([
            {"role": "system", "content": system_prompt},
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
    if role == "BullResearcher":
        score = 50.0
        evidence = []
        if state["financial_quality"].score >= 60:
            evidence.append("Financial quality screens above neutral.")
            score += 10
        if state["valuation"].score >= 60:
            evidence.append("Valuation appears reasonable.")
            score += 10
        if state.get("macro_context") and state["macro_context"].score >= 58:
            evidence.append("Macro and policy context is not obviously hostile.")
            score += 8
        if state.get("evidence_book") and state["evidence_book"].institutional_reports:
            evidence.append("Public institutional report candidates are available for cross-checking.")
            score += 6
        if not evidence:
            evidence.append("Upside depends on execution and sentiment improvement.")
        return AnalystView(
            summary="Bull case based on available data.",
            score=_clamp(score),
            evidence=evidence[:4],
            data_quality="limited",
        )
    else:  # BearResearcher
        score = 50.0
        evidence = []
        if state["valuation"].score <= 45:
            evidence.append("Valuation leaves limited margin of safety.")
            score -= 10
        if state.get("macro_context") and state["macro_context"].score <= 45:
            evidence.append("Macro or policy context is weak or insufficiently supported.")
            score -= 8
        if state["sentiment"].data_quality != "high":
            evidence.append("Sentiment coverage is incomplete.")
            score -= 5
        if state.get("errors"):
            evidence.append("Provider errors reduce reliability.")
            score -= 5
        severe_alerts = [
            alert for alert in state.get("risk_alerts", [])
            if alert.severity in {"critical", "warning"}
        ]
        for alert in severe_alerts[:2]:
            evidence.append(f"{alert.title}: {alert.message}")
            score -= 4 if alert.severity == "warning" else 8
        if not evidence:
            evidence.append("Bear case centers on macro and execution risk.")
        return AnalystView(
            summary="Bear case based on available data.",
            score=_clamp(score),
            evidence=evidence[:4],
            data_quality="limited",
        )


def bull_researcher(state: ResearchState) -> dict[str, Any]:
    if state.get("use_llm"):
        view = _call_llm_analyst(state, BULL_SYSTEM_PROMPT, "BullResearcher")
    else:
        view = _analyst_heuristic(state, "BullResearcher")
    return {"bull_case": view.evidence, "_bull_view": view}


def bear_researcher(state: ResearchState) -> dict[str, Any]:
    if state.get("use_llm"):
        view = _call_llm_analyst(state, BEAR_SYSTEM_PROMPT, "BearResearcher")
    else:
        view = _analyst_heuristic(state, "BearResearcher")
    return {"bear_case": view.evidence, "_bear_view": view}


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
    macro = state.get("macro_context")
    val = state.get("valuation")
    quality = state.get("financial_quality")
    sentiment = state.get("sentiment")
    info = state.get("information_summary")
    evidence_book = state.get("evidence_book") or ResearchEvidenceBook()

    if macro and macro.score >= 58:
        catalysts.append(
            f"Macro/policy context is at least supportive "
            f"(score: {macro.score:.0f}/100)"
        )
    if val and val.score >= 60:
        catalysts.append(
            f"Favorable valuation (score: {val.score:.0f}/100) "
            f"supports upside potential"
        )
    if quality and quality.score >= 60:
        catalysts.append(
            f"Financial quality metrics above threshold "
            f"(score: {quality.score:.0f}/100)"
        )
    if sentiment and sentiment.evidence:
        first = sentiment.evidence[0]
        catalysts.append(f"Market sentiment: {first[:120]}")
    if evidence_book.filings:
        catalysts.append(f"Primary filing to review: {evidence_book.filings[0].title[:120]}")
    if evidence_book.institutional_reports:
        catalysts.append(f"External report lead: {evidence_book.institutional_reports[0].title[:120]}")
    if info and info.data_gaps:
        catalysts.append(
            "Improved data coverage could reveal additional upside signals"
        )
    if not catalysts:
        catalysts.append(
            "Earnings or operating updates are the primary catalyst to monitor"
        )
    return catalysts


def _build_risks(state: ResearchState) -> list[str]:
    """Generate dynamic risks based on actual analysis results."""
    risks = []
    macro = state.get("macro_context")
    val = state.get("valuation")
    quality = state.get("financial_quality")
    sentiment = state.get("sentiment")
    info = state.get("information_summary")
    evidence_book = state.get("evidence_book") or ResearchEvidenceBook()

    if macro and macro.score < 45:
        risks.append(
            f"Macro, policy, or cycle context is weak or poorly evidenced "
            f"(score: {macro.score:.0f}/100)"
        )
    if val and val.score < 45:
        risks.append(
            f"Elevated valuation leaves limited margin of safety "
            f"(score: {val.score:.0f}/100)"
        )
    if quality and quality.score < 45:
        risks.append(
            f"Below-average profitability or financial quality "
            f"(score: {quality.score:.0f}/100)"
        )
    if sentiment and sentiment.data_quality != "high":
        risks.append("Incomplete sentiment coverage reduces confidence")
    if not evidence_book.filings:
        risks.append("No primary filing or annual-report source was found in public search")
    if not evidence_book.institutional_reports:
        risks.append("No public institutional research report source was found")
    if info and info.data_gaps:
        gaps_text = ", ".join(info.data_gaps[:3])
        risks.append(f"Data gaps: {gaps_text}")
    if state.get("errors"):
        risks.append(
            f"Provider errors in {len(state['errors'])} data source(s) "
            f"reduce reliability"
        )
    for alert in state.get("risk_alerts", [])[:5]:
        risks.append(f"{alert.title}: {alert.message}")
    if not risks:
        risks.append("Macro and rates volatility is the primary external risk")
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
