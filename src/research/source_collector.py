"""Open research source discovery for evidence-backed reports.

This module intentionally collects only public metadata and excerpts. It does
not bypass paywalls or copy proprietary research content; the report stores
source links, snippets, and provenance so the final thesis can be audited.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
import html
import re
from threading import Lock
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse
import urllib.request

from loguru import logger

from src.data.cache import get_cache
from src.data.news_fetcher import fetch_financial_news
from src.research.schemas import EvidenceItem, ResearchEvidenceBook


PRIMARY_DOMAINS = (
    "sec.gov",
    "data.sec.gov",
    "cninfo.com.cn",
    "static.cninfo.com.cn",
    "sse.com.cn",
    "szse.cn",
    "hkexnews.hk",
    "hkex.com.hk",
    "pbc.gov.cn",
    "stats.gov.cn",
    "csrc.gov.cn",
    "gov.cn",
)
INSTITUTIONAL_DOMAINS = (
    "pdf.dfcfw.com",
    "eastmoney.com",
    "choice.eastmoney.com",
    "research.cicc.com",
    "cmschina.com",
    "htsc.com.cn",
    "citics.com",
)
MEDIA_DOMAINS = (
    "reuters.com",
    "bloomberg.com",
    "cnbc.com",
    "wsj.com",
    "yicai.com",
    "caixin.com",
    "wallstreetcn.com",
    "sina.com.cn",
    "eastmoney.com",
    "10jqka.com.cn",
    "stcn.com",
    "cnstock.com",
    "cs.com.cn",
)
_DDGS_LOCK = Lock()
_DDGS_CLS: Any | None = None
_DDGS_IMPORT_ERROR: str | None = None


def collect_research_evidence(
    symbol: str,
    market: str,
    *,
    company_name: str = "",
    sector: str = "",
    max_per_channel: int = 6,
) -> ResearchEvidenceBook:
    """Collect public research evidence across macro, filings, reports, and news."""
    cache_key = f"research:evidence:v2:{market}:{symbol}:{company_name}:{sector}:{max_per_channel}"
    cache = get_cache()
    cached = cache.get(cache_key)
    if cached is not None:
        return ResearchEvidenceBook.model_validate(cached)

    queries = build_research_queries(symbol, market, company_name=company_name, sector=sector)
    errors: list[str] = []
    grouped: dict[str, list[EvidenceItem]] = {
        "macro": [],
        "filing": [],
        "institutional_report": [],
        "channel_analysis": [],
    }

    with ThreadPoolExecutor(max_workers=4) as executor:
        future_map = {
            executor.submit(_search_web, query, 4): (channel, query)
            for channel, channel_queries in queries.items()
            for query in channel_queries
        }
        for future in as_completed(future_map):
            channel, query = future_map[future]
            try:
                rows = future.result()
            except Exception as exc:
                errors.append(f"{channel}: {exc}")
                continue
            for row in rows:
                item = _to_evidence_item(channel, query, row)
                if item.url and any(existing.url == item.url for existing in grouped[channel]):
                    continue
                grouped[channel].append(item)

    news_items = _collect_news(symbol, max_per_channel)
    book = ResearchEvidenceBook(
        macro=sorted(grouped["macro"], key=lambda item: item.score, reverse=True)[:max_per_channel],
        filings=sorted(grouped["filing"], key=lambda item: item.score, reverse=True)[:max_per_channel],
        institutional_reports=sorted(
            grouped["institutional_report"],
            key=lambda item: item.score,
            reverse=True,
        )[:max_per_channel],
        channel_analysis=sorted(
            grouped["channel_analysis"],
            key=lambda item: item.score,
            reverse=True,
        )[:max_per_channel],
        news=news_items[:max_per_channel],
        errors=errors,
    )
    cache.set(cache_key, book.model_dump(mode="json"), ttl_seconds=6 * 60 * 60)
    return book


def build_research_queries(
    symbol: str,
    market: str,
    *,
    company_name: str = "",
    sector: str = "",
) -> dict[str, list[str]]:
    """Build a compact query set optimized for fast public-source discovery."""
    term = " ".join(part for part in [symbol, company_name] if part).strip() or symbol
    industry = sector or company_name or symbol
    year = datetime.now().year

    if market == "ashare":
        filing = [
            f"{symbol} {company_name} 年报 PDF site:cninfo.com.cn",
            f"{symbol} {company_name} 年度报告 site:static.cninfo.com.cn",
        ]
        institutional = [
            f"{term} 研报 PDF 券商",
            f"{term} 研究报告 site:pdf.dfcfw.com",
        ]
        macro = [
            f"{industry} 行业 政策 景气度 宏观 {year}",
            f"中国 宏观 利率 财政 政策 {industry}",
        ]
        channel = [
            f"{term} 机构观点 投资逻辑 风险",
            f"{term} 业绩解读 行业分析",
        ]
    elif market == "hk":
        hk_symbol = symbol.zfill(5) if symbol.isdigit() else symbol
        filing = [
            f"{hk_symbol} {company_name} annual report site:hkexnews.hk",
            f"{hk_symbol} {company_name} annual results HKEXnews",
        ]
        institutional = [
            f"{term} equity research report PDF Hong Kong",
            f"{term} 研报 港股 券商",
        ]
        macro = [
            f"Hong Kong China macro policy rates {industry} {year}",
            f"{industry} sector outlook Hong Kong China {year}",
        ]
        channel = [
            f"{term} analyst outlook risks",
            f"{term} results review consensus",
        ]
    else:
        filing = [
            f"{symbol} {company_name} 10-K annual report site:sec.gov",
            f"{term} investor relations annual report PDF",
        ]
        institutional = [
            f"{term} equity research report outlook PDF",
            f"{term} analyst report valuation risks",
        ]
        macro = [
            f"US macro rates inflation sector outlook {industry} {year}",
            f"{industry} industry outlook policy demand cycle {year}",
        ]
        channel = [
            f"{term} earnings call analysis consensus risks",
            f"{term} analyst outlook valuation catalysts",
        ]

    return {
        "macro": macro,
        "filing": filing,
        "institutional_report": institutional,
        "channel_analysis": channel,
    }


def _search_web(query: str, max_results: int) -> list[dict[str, str]]:
    ddgs_cls = _get_ddgs_cls()
    if ddgs_cls is None:
        return []

    try:
        results: list[dict[str, str]] = []
        with ddgs_cls(timeout=8) as ddgs:
            for row in ddgs.text(query, max_results=max_results):
                results.append({
                    "title": str(row.get("title", "")),
                    "summary": str(row.get("body", "")),
                    "url": str(row.get("href", "")),
                })
        return results
    except Exception as exc:
        logger.debug(f"Research search fallback for {query}: {exc}")
        return _search_duckduckgo_html(query, max_results)


def _search_duckduckgo_html(query: str, max_results: int) -> list[dict[str, str]]:
    """Fallback search path using DuckDuckGo's static HTML endpoint."""
    try:
        url = "https://html.duckduckgo.com/html/?" + urlencode({"q": query})
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"
                )
            },
        )
        raw = urllib.request.urlopen(req, timeout=12).read().decode("utf-8", "ignore")
    except Exception as exc:
        logger.warning(f"Static search failed for {query}: {exc}")
        return []

    rows: list[dict[str, str]] = []
    blocks = re.findall(r'<div class="result results_links.*?</div>\s*</div>', raw, re.S)
    if not blocks:
        blocks = raw.split('<div class="result')
    for block in blocks:
        link_match = re.search(
            r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>',
            block,
            re.S,
        )
        if not link_match:
            continue
        href = _clean_duckduckgo_href(html.unescape(link_match.group(1)))
        title = _strip_html(link_match.group(2))
        snippet_match = re.search(r'<a[^>]+class="result__snippet"[^>]*>(.*?)</a>', block, re.S)
        snippet = _strip_html(snippet_match.group(1)) if snippet_match else ""
        rows.append({"title": title, "summary": snippet, "url": href})
        if len(rows) >= max_results:
            break
    return rows


def _clean_duckduckgo_href(href: str) -> str:
    if href.startswith("//"):
        href = "https:" + href
    parsed = urlparse(href)
    params = parse_qs(parsed.query)
    if "uddg" in params and params["uddg"]:
        return params["uddg"][0]
    return href


def _strip_html(value: str) -> str:
    without_tags = re.sub(r"<.*?>", "", value, flags=re.S)
    return html.unescape(without_tags).strip()


def _get_ddgs_cls():
    global _DDGS_CLS, _DDGS_IMPORT_ERROR
    if _DDGS_CLS is not None:
        return _DDGS_CLS
    if _DDGS_IMPORT_ERROR is not None:
        return None
    with _DDGS_LOCK:
        if _DDGS_CLS is not None:
            return _DDGS_CLS
        if _DDGS_IMPORT_ERROR is not None:
            return None
        try:
            from duckduckgo_search import DDGS

            _DDGS_CLS = DDGS
            return _DDGS_CLS
        except Exception as exc:
            _DDGS_IMPORT_ERROR = str(exc)
            logger.warning(f"duckduckgo-search unavailable: {_DDGS_IMPORT_ERROR}")
            return None


def _collect_news(symbol: str, max_items: int) -> list[EvidenceItem]:
    try:
        rows = fetch_financial_news(symbol=symbol, max_items=max_items)
    except Exception:
        rows = []
    items = []
    for row in rows:
        title = str(row.get("title", "")).strip()
        if not title:
            continue
        url = str(row.get("url", ""))
        items.append(
            EvidenceItem(
                channel="news",
                title=title,
                summary=str(row.get("summary", "")),
                url=url,
                source=str(row.get("source", "")) or _domain(url),
                quality=_quality(url),
                query="symbol_news",
                as_of=str(row.get("display_time", "")) or datetime.now().isoformat(),
                score=_score(url, "news"),
            )
        )
    return items


def _to_evidence_item(channel: str, query: str, row: dict[str, Any]) -> EvidenceItem:
    url = str(row.get("url", "")).strip()
    return EvidenceItem(
        channel=channel,  # type: ignore[arg-type]
        title=str(row.get("title", "")).strip()[:240],
        summary=str(row.get("summary", "")).strip()[:500],
        url=url,
        source=_domain(url),
        quality=_quality(url),
        query=query,
        as_of=datetime.now().isoformat(),
        score=_score(url, channel),
    )


def _domain(url: str) -> str:
    if not url:
        return ""
    domain = urlparse(url).netloc.lower()
    return domain.removeprefix("www.")


def _quality(url: str) -> str:
    domain = _domain(url)
    if any(domain.endswith(item) for item in PRIMARY_DOMAINS):
        return "primary"
    if any(domain.endswith(item) for item in INSTITUTIONAL_DOMAINS):
        return "institutional"
    if any(domain.endswith(item) for item in MEDIA_DOMAINS):
        return "media"
    return "search" if domain else "unknown"


def _score(url: str, channel: str) -> float:
    quality = _quality(url)
    base = {
        "primary": 92.0,
        "institutional": 82.0,
        "media": 72.0,
        "search": 58.0,
        "unknown": 40.0,
    }[quality]
    if channel == "filing" and quality == "primary":
        base += 5
    if channel == "institutional_report" and quality == "institutional":
        base += 5
    if url.lower().endswith(".pdf"):
        base += 3
    return min(base, 100.0)
