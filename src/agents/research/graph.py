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
    ResearchReport,
    RiskAlert,
    TradingStrategy,
)
from src.risk.alerts import evaluate_symbol_risk_from_payload, risk_penalty


class ResearchState(TypedDict, total=False):
    symbol: str
    symbols: list[str]  # multi-symbol fan-out mode
    market: str
    period: str
    run_id: str
    provider_id: str | None
    use_llm: bool
    quote: dict[str, Any]
    fundamentals: dict[str, Any]
    history: list[dict[str, Any]]
    news: list[dict[str, Any]]
    sources: list[dict[str, Any]]
    information_summary: InformationSummary
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
        workflow.add_node("InformationSummarizer", information_summarizer)
        workflow.add_node("FundamentalAnalyst", fundamental_analyst)
        workflow.add_node("TechnicalAnalyst", technical_analyst)
        workflow.add_node("NewsSentimentAnalyst", news_sentiment_analyst)
        workflow.add_node("RiskMonitor", risk_monitor)
        workflow.add_node("BullResearcher", bull_researcher)
        workflow.add_node("BearResearcher", bear_researcher)
        workflow.add_node("TradingStrategist", trading_strategist)
        workflow.add_node("ResearchDirector", research_director)

        workflow.set_entry_point("ParallelDataCollector")
        workflow.add_conditional_edges(
            "ParallelDataCollector",
            _fan_out_send,
            ["CollectSingle"],
        )
        workflow.add_edge("CollectSingle", "AggregateData")
        workflow.add_edge("AggregateData", "InformationSummarizer")
    else:
        workflow.add_node("DataCollector", data_collector)
        workflow.add_node("InformationSummarizer", information_summarizer)
        workflow.add_node("FundamentalAnalyst", fundamental_analyst)
        workflow.add_node("TechnicalAnalyst", technical_analyst)
        workflow.add_node("NewsSentimentAnalyst", news_sentiment_analyst)
        workflow.add_node("RiskMonitor", risk_monitor)
        workflow.add_node("BullResearcher", bull_researcher)
        workflow.add_node("BearResearcher", bear_researcher)
        workflow.add_node("TradingStrategist", trading_strategist)
        workflow.add_node("ResearchDirector", research_director)

        workflow.set_entry_point("DataCollector")
        workflow.add_edge("DataCollector", "InformationSummarizer")

    workflow.add_edge("InformationSummarizer", "FundamentalAnalyst")
    workflow.add_edge("InformationSummarizer", "TechnicalAnalyst")
    workflow.add_edge("InformationSummarizer", "NewsSentimentAnalyst")
    workflow.add_edge("NewsSentimentAnalyst", "RiskMonitor")
    workflow.add_edge(["FundamentalAnalyst", "TechnicalAnalyst", "RiskMonitor"], "BullResearcher")
    workflow.add_edge(["FundamentalAnalyst", "TechnicalAnalyst", "RiskMonitor"], "BearResearcher")
    workflow.add_edge(["BullResearcher", "BearResearcher"], "TradingStrategist")
    workflow.add_edge("TradingStrategist", "ResearchDirector")
    workflow.add_edge("ResearchDirector", END)
    return workflow.compile(name="InstitutionalResearchPipeline")


def run_research_pipeline(
    symbol: str,
    *,
    symbols: list[str] | None = None,
    period: str = "6mo",
    provider_id: str | None = None,
    use_llm: bool = False,
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


def information_summarizer(state: ResearchState) -> dict[str, Any]:
    """Collect structured facts and non-structured notes for downstream agents."""
    quote = state.get("quote", {})
    fundamentals = state.get("fundamentals", {})
    history = state.get("history", [])
    sources = state.get("sources", [])

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

    notes = []
    if history:
        first = _num(history[0].get("close"))
        last = _num(history[-1].get("close"))
        if first and last:
            notes.append(f"Period price change {(last / first - 1) * 100:.1f}% for momentum assessment.")
    if quote.get("name") or fundamentals.get("company_name"):
        notes.append(f"Company: {fundamentals.get('company_name') or quote.get('name')}")
    notes.append("TradingAgents-style: collect facts first, then multi-role debate, then explainable strategy.")

    gaps = []
    if not quote:
        gaps.append("Quote data missing")
    if not fundamentals or not any(fundamentals.get(k) is not None for k in ["pe_ratio", "pb_ratio", "roe"]):
        gaps.append("Valuation or profitability indicators incomplete")
    if len(history) < 40:
        gaps.append(f"Historical price sample is short ({len(history)} bars)")
    for item in sources:
        if item.get("error"):
            gaps.append(f"{item.get('source')}: {item.get('error')}")

    summary = "; ".join(facts[:4])
    return {
        "information_summary": InformationSummary(
            structured_facts=facts,
            unstructured_notes=notes,
            data_gaps=gaps[:6],
            source_count=len([item for item in sources if item.get("payload") is not None]),
            summary=summary,
        )
    }


def fundamental_analyst(state: ResearchState) -> dict[str, Any]:
    from config.settings import get_settings
    cfg = get_settings().strategy

    fundamentals = state.get("fundamentals", {})
    pe = _num(fundamentals.get("pe_ratio"))
    pb = _num(fundamentals.get("pb_ratio"))
    roe = _normalize_roe(fundamentals.get("roe"))

    valuation_score = 50.0
    valuation_evidence = []
    if pe is not None:
        valuation_evidence.append(f"PE {pe:.1f}")
        valuation_score += (
            cfg.valuation_pe_bonus if 0 < pe < cfg.pe_low
            else (-cfg.valuation_pe_penalty if pe > cfg.pe_high else 0)
        )
    if pb is not None:
        valuation_evidence.append(f"PB {pb:.2f}")
        valuation_score += (
            cfg.valuation_pb_bonus if 0 < pb < cfg.pb_low
            else (-cfg.valuation_pb_penalty if pb > cfg.pb_high else 0)
        )
    valuation_score = _clamp(valuation_score)

    quality_score = 50.0
    quality_evidence = []
    if roe is not None:
        quality_evidence.append(f"ROE {roe * 100:.1f}%")
        quality_score += 20 if roe >= cfg.roe_high else (-15 if roe < cfg.roe_low else 0)
    if fundamentals.get("net_income") is not None:
        quality_evidence.append("net income data available")
        quality_score += 5
    quality_score = _clamp(quality_score)

    valuation = AnalystView(
        summary=_valuation_summary(pe, pb),
        score=valuation_score,
        evidence=valuation_evidence,
        data_quality="high" if valuation_evidence else "limited",
    )
    quality = AnalystView(
        summary=_quality_summary(roe),
        score=quality_score,
        evidence=quality_evidence,
        data_quality="high" if quality_evidence else "limited",
    )
    return {"valuation": valuation, "financial_quality": quality}


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
    try:
        symbol = state.get("symbol", "")
        news = fetch_financial_news(symbol=symbol, max_items=8)
    except Exception as exc:
        news = []
        state.setdefault("errors", []).append(f"news: {exc}")

    evidence = [item.get("title", "") for item in news if item.get("title")]
    summary = "Recent macro and market news is available." if evidence else "No fresh news feed available."
    score = 52.0 if evidence else 45.0
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
- Positive technical momentum (uptrend, constructive RSI, volume confirmation)
- Favorable sentiment or overlooked catalysts
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
- Negative technical momentum (downtrend, overbought RSI, bearish divergences)
- Poor sentiment, competitive threats, or regulatory headwinds
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
        ("Valuation", state.get("valuation")),
        ("Financial Quality", state.get("financial_quality")),
        ("Technical", state.get("technical")),
        ("Sentiment", state.get("sentiment")),
    ]:
        if view:
            parts.append(f"- {role}: {view.score:.0f}/100 — {view.summary}")
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
        if state["technical"].score >= 60:
            evidence.append("Technical setup is constructive.")
            score += 10
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
        if state["technical"].score <= 45:
            evidence.append("Technical setup is weak.")
            score -= 10
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
        state["valuation"].score,
        state["financial_quality"].score,
        state["technical"].score,
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
        state["valuation"],
        state["financial_quality"],
        state["technical"],
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
                polish_prompt = (
                    "Synthesize this bull/bear debate into one concise "
                    "institutional-style investment thesis paragraph. "
                    f"Current rating: {rating}. Data: {thesis}"
                )
            else:
                polish_prompt = (
                    "Rewrite this investment thesis in one concise "
                    "institutional-style paragraph without changing facts: "
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
            "pe_ratio": fundamentals.get("pe_ratio"),
            "pb_ratio": fundamentals.get("pb_ratio"),
            "roe": fundamentals.get("roe"),
            "market_cap": fundamentals.get("market_cap"),
            "latest_close": current_price,
        },
        valuation=state["valuation"],
        financial_quality=state["financial_quality"],
        technical=state["technical"],
        sentiment=state["sentiment"],
        information_summary=state["information_summary"],
        trading_strategy=state.get("trading_strategy"),
        risk_alerts=alerts,
        pipeline_diagnostics=_build_pipeline_diagnostics(state, alerts, penalty),
        bull_case=state.get("bull_case", []),
        bear_case=state.get("bear_case", []),
        catalysts=_build_catalysts(state),
        risks=_build_risks(state),
        sources=sources,
        llm_status=llm_status,
    )
    return {"report": report, "llm_status": llm_status}


def _valuation_summary(pe: float | None, pb: float | None) -> str:
    if pe is None and pb is None:
        return "Valuation data is incomplete."
    parts = []
    if pe is not None:
        parts.append(f"PE is {pe:.1f}")
    if pb is not None:
        parts.append(f"PB is {pb:.2f}")
    return "; ".join(parts) + "."


def _quality_summary(roe: float | None) -> str:
    if roe is None:
        return "Profitability data is incomplete."
    if roe >= 0.18:
        return f"ROE of {roe * 100:.1f}% indicates strong profitability."
    if roe >= 0.08:
        return f"ROE of {roe * 100:.1f}% indicates acceptable profitability."
    return f"ROE of {roe * 100:.1f}% is below preferred quality thresholds."


def _thesis(state: ResearchState, rating: str, composite: float) -> str:
    return (
        f"{state['symbol']} receives a {rating} rating with a composite score of "
        f"{composite:.1f}. The conclusion balances valuation ({state['valuation'].score:.0f}), "
        f"financial quality ({state['financial_quality'].score:.0f}), technical setup "
        f"({state['technical'].score:.0f}), and sentiment ({state['sentiment'].score:.0f})."
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
    return numeric / 100 if abs(numeric) > 1 else numeric


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
    tech = state.get("technical")
    val = state.get("valuation")
    quality = state.get("financial_quality")
    sentiment = state.get("sentiment")
    info = state.get("information_summary")

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
    if tech and tech.score >= 60:
        catalysts.append(
            f"Constructive technical setup with positive momentum "
            f"(score: {tech.score:.0f}/100)"
        )
    if sentiment and sentiment.evidence:
        first = sentiment.evidence[0]
        catalysts.append(f"Market sentiment: {first[:120]}")
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
    tech = state.get("technical")
    val = state.get("valuation")
    quality = state.get("financial_quality")
    sentiment = state.get("sentiment")
    info = state.get("information_summary")

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
    if tech and tech.score < 45:
        risks.append(
            f"Weak technical setup or deteriorating indicators "
            f"(score: {tech.score:.0f}/100)"
        )
    if sentiment and sentiment.data_quality != "high":
        risks.append("Incomplete sentiment coverage reduces confidence")
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
        "Bull and Bear researchers receive the same evidence and produce opposing cases.",
        "ResearchDirector caps BUY ratings when critical deterministic risk alerts exist.",
        "Provider source/as_of/stale/error metadata is carried into the final report.",
    ]
    if state.get("use_llm"):
        controls.append("LLM output is constrained by typed Pydantic report sections and deterministic scores.")
    return PipelineDiagnostics(
        topology="guarded_dag",
        latency_strategy=[
            "Quote, fundamentals, and history are fetched concurrently in DataCollector.",
            "Fundamental, technical, and sentiment analysis branch after fact collection.",
            "RiskMonitor is deterministic and reuses collected payloads instead of another LLM call.",
        ],
        hallucination_controls=controls,
        validation_checks=[
            "Data gaps are surfaced before synthesis.",
            "Risk alerts impose a numeric penalty before rating and strategy selection.",
            "Final report stores all data sources for auditability.",
        ],
        confidence_adjustments=[
            f"Risk penalty applied: {penalty:.0f} points.",
            f"Active risk alerts: {len(alerts)}.",
            f"Provider errors: {len(state.get('errors', []))}.",
        ],
    )


def _extract_indicator(evidence: list[str], key: str) -> float | None:
    prefix = f"{key}: "
    for item in evidence:
        if item.startswith(prefix):
            return _num(item.removeprefix(prefix))
    return None
