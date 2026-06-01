"""Daily public research reading list.

The collector stores only public metadata, summaries, and source links. It is
designed for a daily reading queue, not for copying paid research content.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from src.data.cache import get_cache
from src.research.source_collector import _domain, _quality, _score, _search_web


DAILY_READ_QUERIES: dict[str, list[str]] = {
    "macro_strategy": [
        "site:pdf.dfcfw.com 宏观 策略 研报 PDF 2026",
        "中金 宏观 策略 研报 2026 市场",
        "site:pbc.gov.cn 货币政策执行报告 2026",
        "site:gov.cn 国务院 金融 资本市场 政策 2026",
        "site:stats.gov.cn 国民经济 运行情况 2026",
        "BlackRock Investment Institute 2026 outlook market policy rates",
    ],
    "company_industry": [
        "site:pdf.dfcfw.com 行业研究 研报 PDF 2026",
        "A股 公司 深度 研报 PDF 2026 券商",
        "site:research.cicc.com 行业 策略 研报 2026",
        "US equity research outlook valuation sector 2026 PDF",
    ],
    "filings_earnings": [
        "site:cninfo.com.cn 年度报告 财报 2026 PDF",
        "site:sse.com.cn 上市公司 公告 2026",
        "site:szse.cn 上市公司 公告 2026",
        "site:hkexnews.hk annual results annual report 2026",
        "site:sec.gov 10-K annual report 2026 Apple Microsoft Nvidia",
    ],
}


def collect_daily_reads(max_items_per_section: int = 5) -> dict[str, Any]:
    """Collect a compact, high-signal daily reading list."""
    limit = max(1, min(max_items_per_section, 10))
    cache_key = f"research:daily_reads:v3:{limit}"
    cache = get_cache()
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    sections = []
    for section_id, queries in DAILY_READ_QUERIES.items():
        items = []
        for query in queries:
            for row in _search_web(query, max_results=3):
                url = str(row.get("url", "")).strip()
                title = str(row.get("title", "")).strip()
                if not url or not title or any(existing["url"] == url for existing in items):
                    continue
                item = _to_daily_item(section_id, query, row)
                if _is_useful_daily_read(item):
                    items.append(item)
        if not items:
            items = _fallback_items(section_id, limit)
        sections.append({
            "id": section_id,
            "title": _section_title(section_id),
            "description": _section_description(section_id),
            "items": sorted(items, key=lambda item: item["score"], reverse=True)[:limit],
        })

    payload = {
        "generated_at": datetime.now().isoformat(),
        "reading_protocol": [
            "先读宏观策略，确认利率、政策和风险偏好背景。",
            "再读行业/公司深度，记录核心假设、估值锚和反身性风险。",
            "最后抽查公告和财报原文，用一手披露校验二手观点。",
            "只保存摘要和链接；付费研报不复制正文。",
        ],
        "sections": sections,
    }
    cache.set(cache_key, payload, ttl_seconds=6 * 60 * 60)
    return payload


def _to_daily_item(section_id: str, query: str, row: dict[str, Any]) -> dict[str, Any]:
    url = str(row.get("url", "")).strip()
    title = str(row.get("title", "")).strip()[:260]
    summary = str(row.get("summary", "")).strip()[:620]
    text = f"{title} {summary} {url}"
    tags = _tags(text)
    return {
        "title": title,
        "summary": summary,
        "url": url,
        "source": _domain(url),
        "quality": _quality(url),
        "query": query,
        "score": _daily_score(url, section_id, text),
        "as_of": datetime.now().isoformat(),
        "tags": tags,
        "reading_time_min": _reading_time(summary),
        "why_read": _why_read(section_id, tags),
    }


def _daily_score(url: str, section_id: str, text: str) -> float:
    channel = "filing" if section_id == "filings_earnings" else "institutional_report"
    score = _score(url, channel)
    lower = text.lower()
    for keyword in ["pdf", "annual report", "10-k", "outlook", "策略", "研报", "年度报告", "深度"]:
        if keyword in lower:
            score += 2.0
    if any(domain in _domain(url) for domain in [
        "cicc.com",
        "dfcfw.com",
        "sec.gov",
        "cninfo.com.cn",
        "hkexnews.hk",
        "pbc.gov.cn",
        "gov.cn",
        "stats.gov.cn",
        "csrc.gov.cn",
        "sse.com.cn",
        "szse.cn",
    ]):
        score += 4.0
    return min(score, 100.0)


def _is_useful_daily_read(item: dict[str, Any]) -> bool:
    url = str(item.get("url", ""))
    title = str(item.get("title", ""))
    if not url.startswith("http") or len(title) < 8:
        return False
    return True


def _tags(text: str) -> list[str]:
    lower = text.lower()
    tags = []
    for key, label in [
        ("macro", "macro"),
        ("policy", "policy"),
        ("rates", "rates"),
        ("earnings", "earnings"),
        ("valuation", "valuation"),
        ("factor", "factor"),
        ("annual report", "filing"),
        ("10-k", "filing"),
        ("宏观", "macro"),
        ("政策", "policy"),
        ("财报", "earnings"),
        ("估值", "valuation"),
        ("行业", "sector"),
        ("年报", "filing"),
    ]:
        if key in lower and label not in tags:
            tags.append(label)
    return tags[:5] or ["research"]


def _reading_time(summary: str) -> int:
    words = max(80, len(summary.split()) + len(summary) // 3)
    return max(3, min(18, round(words / 140)))


def _why_read(section_id: str, tags: list[str]) -> str:
    if section_id == "macro_strategy":
        return "用于每日开盘前确认宏观约束、政策变量和市场风险偏好。"
    if section_id == "company_industry":
        return "用于寻找公司基本面、行业景气度和估值假设的外部参照。"
    if "filing" in tags:
        return "用于用一手披露核对研报和新闻中的关键事实。"
    return "用于补充财报季、公告和监管披露的事实底稿。"


def _section_title(section_id: str) -> str:
    return {
        "macro_strategy": "每日宏观与策略必读",
        "company_industry": "公司与行业深度线索",
        "filings_earnings": "公告、财报与一手披露",
    }[section_id]


def _section_description(section_id: str) -> str:
    return {
        "macro_strategy": "聚合公开宏观、政策、资产配置和策略观点，适合每日开盘前阅读。",
        "company_industry": "优先收集行业深度、公司深度和估值线索，用于后续个股研报交叉验证。",
        "filings_earnings": "聚合 A/H/美股公告、年报、财报和监管披露入口，作为事实校验底稿。",
    }[section_id]


def _fallback_items(section_id: str, limit: int) -> list[dict[str, Any]]:
    now = datetime.now().isoformat()
    rows = {
        "macro_strategy": [
            {
                "title": "中国人民银行货币政策栏目",
                "summary": "中国人民银行（央行）货币政策、政策工具、执行报告和金融市场运行信息的一手入口。",
                "url": "https://www.pbc.gov.cn/zhengcehuobisi/125207/125227/index.html",
            },
            {
                "title": "国家统计局国民经济运行数据",
                "summary": "用于核对增长、价格、工业、消费和投资等中国宏观变量的一手统计入口。",
                "url": "https://www.stats.gov.cn/sj/",
            },
            {
                "title": "中国证监会新闻发布与政策信息",
                "summary": "资本市场监管政策、新闻发布和制度调整的一手入口。",
                "url": "http://www.csrc.gov.cn/csrc/c100028/common_list.shtml",
            },
            {
                "title": "BlackRock Investment Institute 2026 Investment Outlook",
                "summary": "Global outlook page covering policy, rates, growth constraints, and asset-class risk premia.",
                "url": "https://www.blackrock.com/americas-offshore/en/insights/blackrock-investment-institute/outlook",
            },
            {
                "title": "AQR 2026 Capital Market Assumptions",
                "summary": "Long-horizon assumptions note useful for expected return, valuation, and portfolio risk checks.",
                "url": "https://www.aqr.com/insights/research/alternative-thinking/2026-capital-market-assumptions-for-major-asset-classes",
            },
            {
                "title": "KKR Capital Market Assumptions",
                "summary": "Public asset-allocation note on long-run return expectations, risk, selectivity, and portfolio construction.",
                "url": "https://www.kkr.com/wealth/insights/capital-market-assumptions",
            },
        ],
        "company_industry": [
            {
                "title": "东方财富研报中心",
                "summary": "Public China research report index for broker strategy, industry, and company report discovery.",
                "url": "https://data.eastmoney.com/report/",
            },
            {
                "title": "上海证券交易所披露入口",
                "summary": "上海证券交易所上市公司公告、定期报告和监管信息的一手检索入口。",
                "url": "https://www.sse.com.cn/disclosure/listedinfo/announcement/",
            },
            {
                "title": "深圳证券交易所信息披露入口",
                "summary": "深圳证券交易所上市公司公告、定期报告和监管信息的一手检索入口。",
                "url": "https://www.szse.cn/disclosure/listed/notice/index.html",
            },
            {
                "title": "SEC Company Search",
                "summary": "Primary source entry for US listed-company filings, annual reports, 10-K, 10-Q, and 8-K documents.",
                "url": "https://www.sec.gov/edgar/search/",
            },
            {
                "title": "HKEXnews Listed Company Information",
                "summary": "Primary source entry for Hong Kong listed-company announcements, annual results, and reports.",
                "url": "https://www.hkexnews.hk/index.htm",
            },
        ],
        "filings_earnings": [
            {
                "title": "巨潮资讯公告查询",
                "summary": "Primary China disclosure portal for listed-company announcements, annual reports, and earnings documents.",
                "url": "https://www.cninfo.com.cn/new/disclosure",
            },
            {
                "title": "上海证券交易所上市公司公告",
                "summary": "上海市场公告、定期报告和监管披露的一手入口。",
                "url": "https://www.sse.com.cn/disclosure/listedinfo/announcement/",
            },
            {
                "title": "深圳证券交易所上市公司公告",
                "summary": "深圳市场公告、定期报告和监管披露的一手入口。",
                "url": "https://www.szse.cn/disclosure/listed/notice/index.html",
            },
            {
                "title": "HKEXnews Issuer Documents",
                "summary": "Hong Kong primary disclosure source for announcements, annual reports, circulars, and results.",
                "url": "https://www.hkexnews.hk/",
            },
            {
                "title": "SEC EDGAR Latest Filings",
                "summary": "US primary filing feed for 10-K, 10-Q, 8-K, proxy statements, and other company disclosures.",
                "url": "https://www.sec.gov/edgar/search-and-access",
            },
        ],
    }[section_id]
    results = []
    for row in rows[:limit]:
        url = row["url"]
        tags = _tags(f"{row['title']} {row['summary']} {url}")
        results.append({
            "title": row["title"],
            "summary": row["summary"],
            "url": url,
            "source": _domain(url),
            "quality": _quality(url),
            "query": "curated_fallback",
            "score": _daily_score(url, section_id, row["title"] + row["summary"]),
            "as_of": now,
            "tags": tags,
            "reading_time_min": _reading_time(row["summary"]),
            "why_read": _why_read(section_id, tags),
        })
    return results
