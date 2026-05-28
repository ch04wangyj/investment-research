"""Deterministic risk alert engine.

The alert engine is intentionally rules-first. It runs without an LLM so risk
warnings stay available when model credentials are missing or provider calls are
degraded.
"""

from __future__ import annotations

import hashlib
import math
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Any, Iterable

from src.data.dal import detect_market, get_dal, normalize_symbol
from src.data.news_fetcher import fetch_financial_news
from src.research.schemas import AlertSeverity, RiskAlert, RiskCategory


SEVERITY_RANK: dict[str, int] = {
    "critical": 0,
    "warning": 1,
    "watch": 2,
    "info": 3,
}

POLICY_KEYWORDS = [
    "政策",
    "监管",
    "利率",
    "降息",
    "加息",
    "关税",
    "制裁",
    "财政",
    "央行",
    "证监会",
    "国常会",
    "反垄断",
    "房地产",
    "出口管制",
    "芯片",
    "税",
    "policy",
    "regulation",
    "tariff",
    "sanction",
    "rate",
    "fed",
    "sec",
    "guidance",
]

HIGH_IMPACT_POLICY_KEYWORDS = [
    "监管",
    "关税",
    "制裁",
    "央行",
    "证监会",
    "出口管制",
    "降息",
    "加息",
    "tariff",
    "sanction",
    "fed",
    "sec",
]

EARNINGS_SEASON_MONTHS = {1, 2, 4, 5, 7, 8, 10, 11}


def evaluate_symbol_risk(
    symbol: str,
    *,
    period: str = "6mo",
    news_items: list[dict[str, Any]] | None = None,
    include_news: bool = True,
    dal: Any | None = None,
) -> list[RiskAlert]:
    """Fetch local market data and return risk alerts for a symbol."""

    market = detect_market(symbol)
    normalized = normalize_symbol(symbol, market)
    dal = dal or get_dal()
    sources: list[dict[str, Any]] = []
    quote: dict[str, Any] = {}
    fundamentals: dict[str, Any] = {}
    history: list[dict[str, Any]] = []

    quote_result = _safe_provider_call(lambda: dal.get_quote_result(normalized), "quote")
    fund_result = _safe_provider_call(lambda: dal.get_fundamentals_result(normalized), "fundamentals")
    history_result = _safe_provider_call(lambda: dal.get_history_result(normalized, period), "history")

    for result in [quote_result, fund_result, history_result]:
        sources.append(result)

    quote_payload = quote_result.get("payload")
    if isinstance(quote_payload, list) and quote_payload:
        quote = quote_payload[0] if isinstance(quote_payload[0], dict) else {}
    elif isinstance(quote_payload, dict):
        quote = quote_payload

    fund_payload = fund_result.get("payload")
    if isinstance(fund_payload, dict):
        fundamentals = fund_payload

    history_payload = history_result.get("payload")
    if isinstance(history_payload, list):
        history = [item for item in history_payload if isinstance(item, dict)]

    if news_items is None and include_news:
        try:
            news_items = fetch_financial_news(max_items=18)
        except Exception:
            news_items = []

    return evaluate_symbol_risk_from_payload(
        symbol=normalized,
        market=market,
        quote=quote,
        fundamentals=fundamentals,
        history=history,
        sources=sources,
        news=news_items or [],
    )


def evaluate_symbol_risk_from_payload(
    *,
    symbol: str,
    market: str,
    quote: dict[str, Any] | None = None,
    fundamentals: dict[str, Any] | None = None,
    history: list[dict[str, Any]] | None = None,
    sources: list[dict[str, Any]] | None = None,
    news: list[dict[str, Any]] | None = None,
    now: datetime | None = None,
) -> list[RiskAlert]:
    """Evaluate risk from already collected payloads."""

    quote = quote or {}
    fundamentals = fundamentals or {}
    history = history or []
    sources = sources or []
    news = news or []
    now = now or datetime.now()
    market_name = market if market in {"ashare", "hk", "us"} else detect_market(symbol)

    alerts: list[RiskAlert] = []
    alerts.extend(_drawdown_alerts(symbol, market_name, history, quote))
    alerts.extend(_cycle_alerts(symbol, market_name, history))
    alerts.extend(_policy_alerts(symbol, market_name, news))
    alerts.extend(_earnings_alerts(symbol, market_name, now, fundamentals))
    alerts.extend(_data_quality_alerts(symbol, market_name, history, sources))
    return _dedupe_and_sort(alerts)


def evaluate_market_risks(
    symbols: Iterable[Any],
    *,
    limit: int = 12,
    period: str = "6mo",
) -> dict[str, Any]:
    """Evaluate risk alerts for a symbol collection with shared news context."""

    symbol_values = [str(getattr(item, "symbol", item)).strip().upper() for item in symbols]
    symbol_values = [item for item in symbol_values if item][:limit]
    try:
        news_items = fetch_financial_news(max_items=18)
    except Exception:
        news_items = []

    alerts: list[RiskAlert] = []
    if symbol_values:
        with ThreadPoolExecutor(max_workers=min(6, len(symbol_values))) as executor:
            future_map = {
                executor.submit(
                    evaluate_symbol_risk,
                    symbol,
                    period=period,
                    news_items=news_items,
                    include_news=True,
                ): symbol
                for symbol in symbol_values
            }
            for future in as_completed(future_map):
                try:
                    alerts.extend(future.result())
                except Exception as exc:
                    symbol = future_map[future]
                    market = detect_market(symbol)
                    alerts.append(_make_alert(
                        symbol=normalize_symbol(symbol, market),
                        market=market,
                        severity="warning",
                        category="data_quality",
                        title="风险扫描失败",
                        message=f"无法完成该标的风险扫描：{exc}",
                        evidence=[],
                        action_hint="先查看数据源状态，再重新运行风险扫描。",
                    ))

    sorted_alerts = _dedupe_and_sort(alerts)
    return {
        "alerts": sorted_alerts,
        "summary": summarize_alerts(sorted_alerts),
    }


def summarize_alerts(alerts: list[RiskAlert]) -> dict[str, Any]:
    by_severity = {key: 0 for key in ["critical", "warning", "watch", "info"]}
    by_category = {
        key: 0
        for key in ["drawdown", "policy_event", "cycle_shift", "earnings_season", "data_quality"]
    }
    symbols: set[str] = set()
    for alert in alerts:
        by_severity[alert.severity] += 1
        by_category[alert.category] += 1
        symbols.add(alert.symbol)
    return {
        "total": len(alerts),
        "symbols": len(symbols),
        "by_severity": by_severity,
        "by_category": by_category,
        "highest": alerts[0].severity if alerts else "info",
    }


def risk_penalty(alerts: list[RiskAlert]) -> float:
    penalty = 0.0
    for alert in alerts:
        if alert.severity == "critical":
            penalty += 12
        elif alert.severity == "warning":
            penalty += 6
        elif alert.severity == "watch":
            penalty += 2
    return min(penalty, 24)


def _drawdown_alerts(
    symbol: str,
    market: str,
    history: list[dict[str, Any]],
    quote: dict[str, Any],
) -> list[RiskAlert]:
    prices = _close_series(history)
    alerts: list[RiskAlert] = []
    if len(prices) >= 5:
        peak_date, peak_price = max(prices, key=lambda item: item[1])
        current_date, current_price = prices[-1]
        if peak_price > 0:
            drawdown = (current_price / peak_price - 1) * 100
            severity: AlertSeverity | None = None
            if drawdown <= -20:
                severity = "critical"
            elif drawdown <= -12:
                severity = "warning"
            elif drawdown <= -8:
                severity = "watch"
            if severity:
                alerts.append(_make_alert(
                    symbol=symbol,
                    market=market,
                    severity=severity,
                    category="drawdown",
                    title="大幅回撤风险",
                    message=f"所选周期内从高点回撤 {drawdown:.1f}%，需要重新校验仓位和止损。",
                    evidence=[
                        f"peak {peak_price:.2f} on {peak_date}",
                        f"latest {current_price:.2f} on {current_date}",
                    ],
                    action_hint="若已有仓位，优先检查止损线、仓位上限和基本面是否发生变化。",
                ))

        if len(prices) >= 2 and prices[-2][1] > 0:
            daily_change = (prices[-1][1] / prices[-2][1] - 1) * 100
            if daily_change <= -7:
                severity = "critical"
            elif daily_change <= -5:
                severity = "warning"
            else:
                severity = None
            if severity:
                alerts.append(_make_alert(
                    symbol=symbol,
                    market=market,
                    severity=severity,
                    category="drawdown",
                    title="单日急跌提醒",
                    message=f"最近一个交易日下跌 {daily_change:.1f}%，可能触发事件驱动风险。",
                    evidence=[f"{prices[-2][0]} close {prices[-2][1]:.2f}", f"{prices[-1][0]} close {prices[-1][1]:.2f}"],
                    action_hint="查看新闻、公告和成交量是否同步放大，避免在信息未确认时追单。",
                ))

    change_pct = _num(quote.get("change_pct"))
    quote_close = _num(quote.get("close") or quote.get("price"))
    if change_pct is not None and quote_close is not None and quote_close > 0 and -80 < change_pct <= -5:
        alerts.append(_make_alert(
            symbol=symbol,
            market=market,
            severity="warning" if change_pct > -8 else "critical",
            category="drawdown",
            title="行情端急跌提醒",
            message=f"实时/近实时行情显示跌幅 {change_pct:.1f}%。",
            evidence=[f"quote change_pct {change_pct:.2f}%"],
            action_hint="优先确认报价来源和盘口状态，再决定是否触发交易纪律。",
        ))
    return alerts


def _cycle_alerts(symbol: str, market: str, history: list[dict[str, Any]]) -> list[RiskAlert]:
    prices = _close_series(history)
    closes = [price for _, price in prices]
    alerts: list[RiskAlert] = []
    if len(closes) >= 60:
        current = closes[-1]
        sma20 = sum(closes[-20:]) / 20
        sma60 = sum(closes[-60:]) / 60
        momentum20 = (current / closes[-21] - 1) * 100 if closes[-21] > 0 else 0
        if current < sma20 < sma60:
            alerts.append(_make_alert(
                symbol=symbol,
                market=market,
                severity="warning",
                category="cycle_shift",
                title="周期转弱提醒",
                message="价格低于 20 日均线且 20 日均线低于 60 日均线，趋势结构偏弱。",
                evidence=[
                    f"latest {current:.2f}",
                    f"SMA20 {sma20:.2f}",
                    f"SMA60 {sma60:.2f}",
                ],
                action_hint="降低趋势交易仓位，等待重新站上关键均线或基本面催化确认。",
            ))
        elif current < sma20 and momentum20 < -5:
            alerts.append(_make_alert(
                symbol=symbol,
                market=market,
                severity="watch",
                category="cycle_shift",
                title="短周期动量转弱",
                message=f"价格跌破 20 日均线，20 日动量 {momentum20:.1f}%。",
                evidence=[f"latest {current:.2f}", f"SMA20 {sma20:.2f}"],
                action_hint="观察是否出现连续放量下跌或板块同步走弱。",
            ))

    returns = _returns(closes)
    if len(returns) >= 45:
        latest_vol = _std(returns[-10:])
        base_vol = _std(returns[-40:-10])
        if base_vol > 0 and latest_vol / base_vol >= 1.8 and latest_vol >= 0.02:
            alerts.append(_make_alert(
                symbol=symbol,
                market=market,
                severity="warning",
                category="cycle_shift",
                title="波动率抬升提醒",
                message=f"近 10 日波动率约为前期 {latest_vol / base_vol:.1f} 倍，风险预算需要下调。",
                evidence=[f"latest daily vol {latest_vol * 100:.2f}%", f"baseline daily vol {base_vol * 100:.2f}%"],
                action_hint="降低单笔头寸，避免把短期波动误判为趋势确认。",
            ))
    return alerts


def _policy_alerts(symbol: str, market: str, news: list[dict[str, Any]]) -> list[RiskAlert]:
    matches: list[dict[str, Any]] = []
    high_impact = False
    for item in news:
        title = str(item.get("title") or "")
        summary = str(item.get("summary") or "")
        text = f"{title} {summary}".lower()
        if any(keyword.lower() in text for keyword in POLICY_KEYWORDS):
            matches.append(item)
            high_impact = high_impact or any(
                keyword.lower() in text for keyword in HIGH_IMPACT_POLICY_KEYWORDS
            )
    if not matches:
        return []

    severity: AlertSeverity = "warning" if high_impact else "watch"
    evidence = [
        str(item.get("title") or item.get("summary") or "policy headline")[:120]
        for item in matches[:4]
    ]
    return [_make_alert(
        symbol=symbol,
        market=market,
        severity=severity,
        category="policy_event",
        title="突发政策/宏观事件需跟踪",
        message="近期新闻流出现政策、监管、利率或贸易相关关键词，可能影响估值和风险偏好。",
        evidence=evidence,
        action_hint="展开新闻目录，确认事件是否与标的行业、上市地或收入区域直接相关。",
    )]


def _earnings_alerts(
    symbol: str,
    market: str,
    now: datetime,
    fundamentals: dict[str, Any],
) -> list[RiskAlert]:
    if now.month not in EARNINGS_SEASON_MONTHS:
        return []
    evidence = [f"calendar month {now.strftime('%Y-%m')}"]
    for key in ["earnings_date", "report_date", "next_earnings_date"]:
        if fundamentals.get(key):
            evidence.append(f"{key}: {fundamentals[key]}")
    label = {
        "ashare": "A 股定期报告/业绩说明窗口",
        "hk": "港股业绩公告窗口",
        "us": "美股财报季窗口",
    }.get(market, "财报季窗口")
    return [_make_alert(
        symbol=symbol,
        market=market,
        severity="info",
        category="earnings_season",
        title="财报季/业绩窗口提醒",
        message=f"当前处于{label}，盈利指引、费用率和现金流披露可能改变研究假设。",
        evidence=evidence,
        action_hint="在财报发布前后降低对旧指标的依赖，并重新运行基本面和策略 Agent。",
    )]


def _data_quality_alerts(
    symbol: str,
    market: str,
    history: list[dict[str, Any]],
    sources: list[dict[str, Any]],
) -> list[RiskAlert]:
    alerts: list[RiskAlert] = []
    errors = [str(item.get("error")) for item in sources if item.get("error")]
    stale_sources = [str(item.get("source")) for item in sources if item.get("stale")]
    if not history:
        alerts.append(_make_alert(
            symbol=symbol,
            market=market,
            severity="warning",
            category="data_quality",
            title="历史行情缺失",
            message="没有可用历史行情，无法可靠判断回撤、趋势和波动率。",
            evidence=errors[:3],
            action_hint="切换数据源或缩短周期后重新扫描风险。",
        ))
    if len(errors) >= 2:
        alerts.append(_make_alert(
            symbol=symbol,
            market=market,
            severity="warning",
            category="data_quality",
            title="多数据源异常",
            message="多个 provider 返回错误，当前分析可信度需要下调。",
            evidence=errors[:4],
            action_hint="先确认网络和 provider 状态，避免用残缺数据做方向性判断。",
        ))
    elif errors:
        alerts.append(_make_alert(
            symbol=symbol,
            market=market,
            severity="watch",
            category="data_quality",
            title="数据源降级",
            message="至少一个 provider 返回错误，系统可能已使用 fallback 或缓存数据。",
            evidence=errors[:3],
            action_hint="查看数据来源和 as_of 时间，必要时手动刷新。",
        ))
    if stale_sources:
        alerts.append(_make_alert(
            symbol=symbol,
            market=market,
            severity="watch",
            category="data_quality",
            title="缓存数据提醒",
            message="风险扫描使用了过期缓存，实时性不足。",
            evidence=stale_sources[:4],
            action_hint="等待 provider 恢复后重新扫描。",
        ))
    return alerts


def _safe_provider_call(call: Any, label: str) -> dict[str, Any]:
    try:
        result = call()
        if hasattr(result, "to_dict"):
            return result.to_dict()
        return result if isinstance(result, dict) else {"source": label, "payload": result}
    except Exception as exc:
        return {
            "source": label,
            "payload": None,
            "as_of": datetime.now().isoformat(),
            "stale": False,
            "error": str(exc),
        }


def _close_series(history: list[dict[str, Any]]) -> list[tuple[str, float]]:
    values: list[tuple[str, float]] = []
    for index, row in enumerate(history):
        close = _num(row.get("close"))
        if close is None or close <= 0:
            continue
        date = str(row.get("date") or index)
        values.append((date, close))
    return values


def _returns(closes: list[float]) -> list[float]:
    result: list[float] = []
    for previous, current in zip(closes, closes[1:]):
        if previous > 0:
            result.append(current / previous - 1)
    return result


def _std(values: list[float]) -> float:
    clean = [value for value in values if math.isfinite(value)]
    if len(clean) < 2:
        return 0.0
    mean = sum(clean) / len(clean)
    variance = sum((value - mean) ** 2 for value in clean) / (len(clean) - 1)
    return math.sqrt(max(variance, 0.0))


def _num(value: Any) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except (TypeError, ValueError):
        return None


def _make_alert(
    *,
    symbol: str,
    market: str,
    severity: AlertSeverity,
    category: RiskCategory,
    title: str,
    message: str,
    evidence: list[str],
    action_hint: str,
) -> RiskAlert:
    normalized_market = market if market in {"ashare", "hk", "us"} else detect_market(symbol)
    fingerprint = hashlib.sha1(
        f"{symbol}|{normalized_market}|{severity}|{category}|{title}|{message}".encode("utf-8")
    ).hexdigest()[:10]
    return RiskAlert(
        id=f"{symbol}:{category}:{fingerprint}",
        symbol=symbol,
        market=normalized_market,  # type: ignore[arg-type]
        severity=severity,
        category=category,
        title=title,
        message=message,
        evidence=evidence,
        action_hint=action_hint,
    )


def _dedupe_and_sort(alerts: list[RiskAlert]) -> list[RiskAlert]:
    seen: set[str] = set()
    unique: list[RiskAlert] = []
    for alert in alerts:
        if alert.id in seen:
            continue
        seen.add(alert.id)
        unique.append(alert)
    return sorted(unique, key=lambda item: (SEVERITY_RANK[item.severity], item.symbol, item.category, item.title))
