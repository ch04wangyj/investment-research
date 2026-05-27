"""LangGraph multi-agent research pipeline.

The implementation borrows the shape of public trading-agent systems without
copying code: specialist analysts produce typed sections, then a research
director synthesizes a single Pydantic ResearchReport.
"""

import uuid
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
    ResearchReport,
    TradingStrategy,
)


class ResearchState(TypedDict, total=False):
    symbol: str
    market: str
    period: str
    run_id: str
    provider_id: str | None
    use_llm: bool
    quote: dict[str, Any]
    fundamentals: dict[str, Any]
    history: list[dict[str, Any]]
    sources: list[dict[str, Any]]
    information_summary: InformationSummary
    valuation: AnalystView
    financial_quality: AnalystView
    technical: AnalystView
    sentiment: AnalystView
    bull_case: list[str]
    bear_case: list[str]
    trading_strategy: TradingStrategy
    report: ResearchReport
    llm_status: str
    errors: list[str]


def build_research_graph():
    workflow = StateGraph(ResearchState)
    workflow.add_node("DataCollector", data_collector)
    workflow.add_node("InformationSummarizer", information_summarizer)
    workflow.add_node("FundamentalAnalyst", fundamental_analyst)
    workflow.add_node("TechnicalAnalyst", technical_analyst)
    workflow.add_node("NewsSentimentAnalyst", news_sentiment_analyst)
    workflow.add_node("BullResearcher", bull_researcher)
    workflow.add_node("BearResearcher", bear_researcher)
    workflow.add_node("TradingStrategist", trading_strategist)
    workflow.add_node("ResearchDirector", research_director)

    workflow.set_entry_point("DataCollector")
    workflow.add_edge("DataCollector", "InformationSummarizer")
    workflow.add_edge("InformationSummarizer", "FundamentalAnalyst")
    workflow.add_edge("FundamentalAnalyst", "TechnicalAnalyst")
    workflow.add_edge("TechnicalAnalyst", "NewsSentimentAnalyst")
    workflow.add_edge("NewsSentimentAnalyst", "BullResearcher")
    workflow.add_edge("BullResearcher", "BearResearcher")
    workflow.add_edge("BearResearcher", "TradingStrategist")
    workflow.add_edge("TradingStrategist", "ResearchDirector")
    workflow.add_edge("ResearchDirector", END)
    return workflow.compile(name="InstitutionalResearchPipeline")


def run_research_pipeline(
    symbol: str,
    *,
    period: str = "6mo",
    provider_id: str | None = None,
    use_llm: bool = False,
) -> ResearchReport:
    market = detect_market(symbol)
    normalized = normalize_symbol(symbol, market)
    graph = build_research_graph()
    state = graph.invoke({
        "symbol": normalized,
        "market": market,
        "period": period,
        "run_id": str(uuid.uuid4()),
        "provider_id": provider_id,
        "use_llm": use_llm,
        "errors": [],
    })
    return state["report"]


def data_collector(state: ResearchState) -> dict[str, Any]:
    dal = get_dal()
    symbol = state["symbol"]
    quote_result = dal.get_quote_result(symbol)
    fund_result = dal.get_fundamentals_result(symbol)
    history_result = dal.get_history_result(symbol, state.get("period", "6mo"))

    errors = list(state.get("errors", []))
    for label, result in [
        ("quote", quote_result),
        ("fundamentals", fund_result),
        ("history", history_result),
    ]:
        if result.error:
            errors.append(f"{label}: {result.error}")

    quote_payload = quote_result.payload
    quote = quote_payload[0] if isinstance(quote_payload, list) and quote_payload else {}
    fundamentals = fund_result.payload if isinstance(fund_result.payload, dict) else {}
    history = history_result.payload if isinstance(history_result.payload, list) else []
    sources = [
        quote_result.to_dict(),
        fund_result.to_dict(),
        history_result.to_dict(),
    ]
    return {
        "quote": quote,
        "fundamentals": fundamentals,
        "history": history,
        "sources": sources,
        "errors": errors,
    }


def information_summarizer(state: ResearchState) -> dict[str, Any]:
    """Collect structured facts and non-structured notes for downstream agents."""
    quote = state.get("quote", {})
    fundamentals = state.get("fundamentals", {})
    history = state.get("history", [])
    sources = state.get("sources", [])

    facts = [
        f"标的 {state['symbol']}，市场 {state['market']}",
        f"最新价 {quote.get('close')}" if quote.get("close") is not None else "最新价缺失",
        f"涨跌幅 {quote.get('change_pct'):.2f}%" if isinstance(quote.get("change_pct"), (int, float)) else "涨跌幅缺失",
        f"历史样本 {len(history)} 条",
    ]
    for key, label in [
        ("pe_ratio", "PE"),
        ("pb_ratio", "PB"),
        ("roe", "ROE"),
        ("market_cap", "市值"),
        ("sector", "板块"),
    ]:
        if fundamentals.get(key) is not None:
            facts.append(f"{label}: {fundamentals.get(key)}")

    notes = []
    if history:
        first = _num(history[0].get("close"))
        last = _num(history[-1].get("close"))
        if first and last:
            notes.append(f"所选周期价格变化 {(last / first - 1) * 100:.1f}%，用于判断动量而非预测收益。")
    if quote.get("name") or fundamentals.get("company_name"):
        notes.append(f"公司/简称：{fundamentals.get('company_name') or quote.get('name')}")
    notes.append("TradingAgents-CN 风格参考：先收集事实，再由多角色分工辩证，最后形成可解释策略。")

    gaps = []
    if not quote:
        gaps.append("行情数据缺失")
    if not fundamentals or not any(fundamentals.get(k) is not None for k in ["pe_ratio", "pb_ratio", "roe"]):
        gaps.append("估值或盈利指标不完整")
    if len(history) < 40:
        gaps.append("历史价格样本偏短")
    for item in sources:
        if item.get("error"):
            gaps.append(f"{item.get('source')}: {item.get('error')}")

    summary = "；".join(facts[:4])
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
    fundamentals = state.get("fundamentals", {})
    pe = _num(fundamentals.get("pe_ratio"))
    pb = _num(fundamentals.get("pb_ratio"))
    roe = _normalize_roe(fundamentals.get("roe"))

    valuation_score = 50.0
    valuation_evidence = []
    if pe is not None:
        valuation_evidence.append(f"PE {pe:.1f}")
        valuation_score += 15 if 0 < pe < 18 else (-15 if pe > 45 else 0)
    if pb is not None:
        valuation_evidence.append(f"PB {pb:.2f}")
        valuation_score += 10 if 0 < pb < 2.5 else (-10 if pb > 8 else 0)
    valuation_score = _clamp(valuation_score)

    quality_score = 50.0
    quality_evidence = []
    if roe is not None:
        quality_evidence.append(f"ROE {roe * 100:.1f}%")
        quality_score += 20 if roe >= 0.18 else (-15 if roe < 0.06 else 0)
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
    snapshot = compute_technical_snapshot(state.get("history", []))
    indicators = snapshot.get("indicators", {})
    score = 50.0
    trend = indicators.get("trend")
    rsi = indicators.get("rsi_14")
    momentum = indicators.get("momentum_pct")
    if trend == "uptrend":
        score += 18
    elif trend == "downtrend":
        score -= 18
    if isinstance(rsi, (int, float)):
        if 45 <= rsi <= 65:
            score += 6
        elif rsi >= 75:
            score -= 8
        elif rsi <= 25:
            score += 4
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
        news = fetch_financial_news(max_items=5)
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
        )
    }


def bull_researcher(state: ResearchState) -> dict[str, Any]:
    bull = []
    if state["financial_quality"].score >= 60:
        bull.append("Financial quality screens above neutral based on available profitability data.")
    if state["valuation"].score >= 60:
        bull.append("Valuation appears reasonable relative to available PE/PB data.")
    if state["technical"].score >= 60:
        bull.append("Price action and momentum are constructive over the selected period.")
    if not bull:
        bull.append("Upside case depends on operational execution and improved market sentiment.")
    return {"bull_case": bull[:4]}


def bear_researcher(state: ResearchState) -> dict[str, Any]:
    bear = []
    if state["valuation"].score <= 45:
        bear.append("Valuation leaves limited margin of safety based on available multiples.")
    if state["technical"].score <= 45:
        bear.append("Technical setup is weak or lacks confirmation from trend indicators.")
    if state["sentiment"].data_quality != "high":
        bear.append("News and sentiment coverage is incomplete, limiting confidence.")
    if state.get("errors"):
        bear.append("Provider errors or stale data reduce reliability of the conclusion.")
    if not bear:
        bear.append("Bear case centers on macro pressure, execution risk, and forecast uncertainty.")
    return {"bear_case": bear[:4]}


def trading_strategist(state: ResearchState) -> dict[str, Any]:
    composite = sum([
        state["valuation"].score,
        state["financial_quality"].score,
        state["technical"].score,
        state["sentiment"].score,
    ]) / 4
    quote = state.get("quote", {})
    current_price = _num(quote.get("close") or state.get("fundamentals", {}).get("current_price"))
    volatility = _extract_indicator(state["technical"].evidence, "annualized_volatility_pct")
    trend = "uptrend" if "trend: uptrend" in state["technical"].evidence else (
        "downtrend" if "trend: downtrend" in state["technical"].evidence else "neutral"
    )

    if composite >= 65 and trend != "downtrend":
        action = "accumulate"
        position = 12.0
    elif composite <= 42 or trend == "downtrend":
        action = "reduce"
        position = 0.0 if composite <= 35 else 4.0
    elif composite < 48:
        action = "avoid"
        position = 0.0
    else:
        action = "hold"
        position = 8.0

    stop_loss = None
    take_profit = None
    entry_zone = "等待价格回到关键均线或放量突破后再评估"
    if current_price is not None:
        risk_band = 0.07 if volatility is None else max(min(volatility / 300, 0.14), 0.05)
        stop_loss = round(current_price * (1 - risk_band), 2)
        take_profit = round(current_price * (1 + risk_band * 1.8), 2)
        low_entry = round(current_price * 0.98, 2)
        high_entry = round(current_price * 1.02, 2)
        entry_zone = f"{low_entry} - {high_entry}"

    rationale = [
        f"综合评分 {composite:.1f}",
        f"技术状态 {trend}",
        f"估值/质量/技术/情绪分数分别为 {state['valuation'].score:.0f}/{state['financial_quality'].score:.0f}/{state['technical'].score:.0f}/{state['sentiment'].score:.0f}",
    ]
    invalidation = [
        "数据源连续失败或关键财务指标缺失扩大",
        "价格跌破止损区间且没有基本面改善证据",
        "重大政策、财报或流动性事件改变原始假设",
    ]
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
    composite = sum(scores) / len(scores)
    rating = "BUY" if composite >= 62 else ("SELL" if composite <= 42 else "HOLD")
    confidence = "high" if not state.get("errors") and min(scores) >= 45 else "medium"
    if state.get("errors") or any(view.data_quality == "missing" for view in [
        state["valuation"],
        state["financial_quality"],
        state["technical"],
        state["sentiment"],
    ]):
        confidence = "low"

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

    if state.get("use_llm"):
        try:
            llm = create_chat_model(state.get("provider_id"), tier="deep", temperature=0.2)
            response = llm.invoke(
                "Rewrite this investment thesis in one concise institutional-style "
                f"paragraph without changing facts: {thesis}"
            )
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
        bull_case=state.get("bull_case", []),
        bear_case=state.get("bear_case", []),
        catalysts=[
            "Upcoming earnings or operating updates",
            "Sector policy and liquidity conditions",
            "Re-rating if data quality and trend confirmation improve",
        ],
        risks=[
            "Data availability or provider instability",
            "Macro and rates volatility",
            "Company-specific execution and guidance risk",
        ],
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


def _extract_indicator(evidence: list[str], key: str) -> float | None:
    prefix = f"{key}: "
    for item in evidence:
        if item.startswith(prefix):
            return _num(item.removeprefix(prefix))
    return None
