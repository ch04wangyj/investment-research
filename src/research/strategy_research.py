"""Value-investing and strategy-method research collector."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from src.data.cache import get_cache
from src.research.source_collector import _domain, _quality, _score, _search_web


STRATEGY_QUERIES: dict[str, list[str]] = {
    "value_investing": [
        "value investing quality compounder strategy research 2026",
        "value factor profitability investment strategy research 2026",
        "margin of safety value investing market outlook 2026",
    ],
    "frontier_papers": [
        "site:arxiv.org q-fin portfolio strategy machine learning 2026",
        "site:ssrn.com asset pricing factor investing strategy 2026",
        "site:nber.org asset pricing market anomalies 2026",
    ],
    "market_views": [
        "BlackRock investment institute market outlook 2026 valuation risks",
        "J.P. Morgan market outlook 2026 equity strategy valuation",
        "AQR capital market assumptions value momentum quality 2026",
    ],
}


def collect_strategy_research(max_items_per_section: int = 6) -> dict[str, Any]:
    """Collect recent method research and market views for a strategy library."""
    cache_key = f"strategy:research:v2:{max_items_per_section}"
    cache = get_cache()
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    sections = []
    for section_id, queries in STRATEGY_QUERIES.items():
        items = []
        for query in queries:
            for row in _search_web(query, max_results=3):
                url = str(row.get("url", ""))
                if not url or any(existing.get("url") == url for existing in items):
                    continue
                items.append({
                    "title": str(row.get("title", "")),
                    "summary": str(row.get("summary", ""))[:500],
                    "url": url,
                    "source": _domain(url),
                    "quality": _quality(url),
                    "query": query,
                    "score": _score(url, "channel_analysis"),
                    "as_of": datetime.now().isoformat(),
                        "method_tags": _method_tags(f"{row.get('title', '')} {row.get('summary', '')} {url}"),
                })
        if not items:
            items = _fallback_items(section_id, max_items_per_section)
        items = sorted(items, key=lambda item: item["score"], reverse=True)[:max_items_per_section]
        sections.append({
            "id": section_id,
            "title": _section_title(section_id),
            "description": _section_description(section_id),
            "items": items,
        })

    payload = {
        "generated_at": datetime.now().isoformat(),
        "sections": sections,
        "principles": [
            "先理解商业模式、资本回报和估值区间，再考虑交易策略。",
            "价值投资模块只提供方法研究和市场观点，不直接生成买卖点。",
            "前沿论文必须经过可解释性、样本外稳健性和交易成本三重审查。",
        ],
    }
    cache.set(cache_key, payload, ttl_seconds=12 * 60 * 60)
    return payload


def _section_title(section_id: str) -> str:
    return {
        "value_investing": "价值投资方法",
        "frontier_papers": "前沿论文与量化策略",
        "market_views": "市场观点与资产配置",
    }[section_id]


def _section_description(section_id: str) -> str:
    return {
        "value_investing": "关注护城河、现金流、资本回报、估值安全边际和长期复利。",
        "frontier_papers": "跟踪机器学习、因子、组合优化、市场异象等近期研究。",
        "market_views": "汇总大型资管、投行和策略团队对宏观、估值与风险溢价的观点。",
    }[section_id]


def _method_tags(text: str) -> list[str]:
    lower = text.lower()
    tags = []
    for key, label in [
        ("value", "value"),
        ("quality", "quality"),
        ("momentum", "momentum"),
        ("machine learning", "machine_learning"),
        ("portfolio", "portfolio"),
        ("factor", "factor"),
        ("macro", "macro"),
        ("risk", "risk"),
    ]:
        if key in lower:
            tags.append(label)
    return tags[:5]


def _fallback_items(section_id: str, limit: int) -> list[dict[str, Any]]:
    """Curated public-source fallback when live search is unavailable."""
    now = datetime.now().isoformat()
    rows = {
        "value_investing": [
            {
                "title": "AQR 2026 Capital Market Assumptions",
                "summary": "Uses long-horizon expected-return assumptions and valuation discipline as inputs for portfolio construction and margin-of-safety thinking.",
                "url": "https://www.aqr.com/insights/research/alternative-thinking/2026-capital-market-assumptions-for-major-asset-classes",
            },
            {
                "title": "Capital Group 2026 Capital Market Assumptions",
                "summary": "Frames long-term equity and fixed-income return expectations through valuation, earnings, inflation, and portfolio-construction assumptions.",
                "url": "https://www.capitalgroup.com/intermediaries/es/en/insights/topics/capital-market-assumptions.html",
            },
            {
                "title": "KKR Capital Market Assumptions",
                "summary": "Emphasizes quality, selectivity, manager dispersion, and disciplined implementation when broad beta becomes less forgiving.",
                "url": "https://www.kkr.com/wealth/insights/capital-market-assumptions",
            },
        ],
        "frontier_papers": [
            {
                "title": "Factor Investing in Emerging Markets: From Multi-Factor Industry Portfolios to a Market-Neutral Alpha Strategy",
                "summary": "A 2026 SSRN paper testing size, value, quality, momentum, volatility, and dividend-yield signals under temporal split validation.",
                "url": "https://papers.ssrn.com/sol3/papers.cfm?abstract_id=6584161",
            },
            {
                "title": "Don't Mix What Should Be Separated: Why Combining Value and Momentum Signals Destroys Alpha",
                "summary": "A 2026 SSRN study comparing combined ranking with separate value and momentum sleeves in a multi-strategy book.",
                "url": "https://papers.ssrn.com/sol3/papers.cfm?abstract_id=6255159",
            },
            {
                "title": "Machine Learning Enhanced Multi-Factor Quantitative Trading",
                "summary": "Recent arXiv work on factor engineering, cross-sectional neutralization, and portfolio optimization with explicit bias correction.",
                "url": "https://arxiv.org/abs/2507.07107",
            },
        ],
        "market_views": [
            {
                "title": "BlackRock Investment Institute 2026 Investment Outlook",
                "summary": "Summarizes tactical and strategic views on macro constraints, policy, rates, and asset-class risk premia.",
                "url": "https://www.blackrock.com/americas-offshore/en/insights/blackrock-investment-institute/outlook",
            },
            {
                "title": "AQR 2026 Capital Market Assumptions PDF",
                "summary": "Public asset-class return assumption note useful for cross-checking valuation, expected return, and portfolio risk assumptions.",
                "url": "https://www.aqr.com/-/media/AQR/Documents/Alternative-Thinking/AQR-Alternative-Thinking---2026-Capital-Market-Assumptions.pdf?sc_lang=en",
            },
            {
                "title": "Invesco 2026 Long-Term Capital Market Assumptions",
                "summary": "Uses a building-block approach for asset-class returns, risk, and correlations, with tactical notes on near-term opportunities.",
                "url": "https://www.invesco.com/apac/en/institutional/insights/multi-asset/long-term-capital-market-assumptions.html",
            },
        ],
    }.get(section_id, [])
    results = []
    for row in rows[:limit]:
        url = row["url"]
        results.append({
            "title": row["title"],
            "summary": row["summary"],
            "url": url,
            "source": _domain(url),
            "quality": _quality(url),
            "query": "curated_fallback",
            "score": _score(url, "channel_analysis"),
            "as_of": now,
            "method_tags": _method_tags(f"{row['title']} {row['summary']} {url}"),
        })
    return results
