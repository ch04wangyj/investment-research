"""Financial news headline fetcher with multi-source fallback."""

from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError, as_completed
from datetime import datetime, timedelta
from typing import Any
from urllib.parse import quote_plus
import xml.etree.ElementTree as ET

from loguru import logger

from src.data.cache import get_cache

SINA_ROLL_URL = (
    "https://feed.mix.sina.com.cn/api/roll/get"
    "?pageid=153&lid=2509&k=&num={max_items}&page=1"
)
NEWS_FETCH_TIMEOUT_SECONDS = 12
COMPANY_NEWS_CHANNELS = {
    "akshare_stock_news_em",
    "finnhub_company_news",
    "yahoo_finance_rss",
    "google_news_rss",
}


def news_source_catalog() -> list[dict[str, str]]:
    """Describe live news channels exposed to the UI."""
    return [
        {"id": "akshare_stock_news_em", "name": "东方财富个股新闻", "region": "cn", "kind": "company"},
        {"id": "akshare_global_em", "name": "东方财富财经快讯", "region": "cn", "kind": "macro"},
        {"id": "akshare_global_ths", "name": "同花顺财经快讯", "region": "cn", "kind": "macro"},
        {"id": "akshare_global_sina", "name": "新浪财经直播", "region": "cn", "kind": "macro"},
        {"id": "sina_roll", "name": "新浪财经滚动", "region": "cn", "kind": "macro"},
        {"id": "finnhub_company_news", "name": "Finnhub Company News", "region": "global", "kind": "company"},
        {"id": "yahoo_finance_rss", "name": "Yahoo Finance RSS", "region": "global", "kind": "company"},
        {"id": "google_news_rss", "name": "Google News RSS", "region": "global", "kind": "search"},
    ]


def fetch_financial_news(
    symbol: str | None = None,
    max_items: int = 8,
) -> list[dict[str, Any]]:
    """Fetch financial news headlines from symbol and macro feeds."""
    results: list[dict[str, Any]] = []
    fetchers = [
        ("akshare_stock_news_em", lambda: _fetch_akshare_stock_news(symbol, max_items) if symbol else []),
        ("finnhub_company_news", lambda: _fetch_finnhub_company_news(symbol, max_items) if symbol else []),
        ("yahoo_finance_rss", lambda: _fetch_yahoo_finance_rss(symbol, max_items) if symbol else []),
        ("google_news_rss", lambda: _fetch_google_news_rss(symbol or "中国 财经 政策 市场", max_items)),
        ("akshare_global_em", lambda: _fetch_akshare_global_news("em", max_items)),
        ("akshare_global_ths", lambda: _fetch_akshare_global_news("ths", max_items)),
        ("akshare_global_sina", lambda: _fetch_akshare_global_news("sina", max_items)),
        ("sina_roll", lambda: _fetch_sina_roll_news(max_items)),
    ]
    executor = ThreadPoolExecutor(max_workers=len(fetchers), thread_name_prefix="news")
    futures = {executor.submit(fetcher): source for source, fetcher in fetchers}
    try:
        for future in as_completed(futures, timeout=NEWS_FETCH_TIMEOUT_SECONDS):
            try:
                results.extend(future.result())
            except Exception as exc:
                logger.debug(f"news source {futures[future]} failed: {exc}")
    except FuturesTimeoutError:
        pending = [source for future, source in futures.items() if not future.done()]
        logger.debug(f"news sources timed out: {', '.join(pending)}")
    finally:
        executor.shutdown(wait=False, cancel_futures=True)

    return sorted(
        _dedupe_news(results),
        key=lambda item: int(item.get("source_priority", 99)),
    )[:max_items]


def _fetch_akshare_global_news(source: str, max_items: int) -> list[dict[str, Any]]:
    """Fetch mainland-accessible finance headlines exposed by AKShare."""
    import akshare as ak

    cache = get_cache()
    cache_key = f"news:akshare_global:v1:{source}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached[:max_items]
    config = {
        "em": ("stock_info_global_em", "东方财富财经", "akshare_global_em", 20),
        "ths": ("stock_info_global_ths", "同花顺财经", "akshare_global_ths", 22),
        "sina": ("stock_info_global_sina", "新浪财经", "akshare_global_sina", 24),
    }
    function_name, source_name, source_channel, priority = config[source]
    df = getattr(ak, function_name)()
    if df is None or df.empty:
        return []

    results = []
    for _, row in df.head(max(40, max_items)).iterrows():
        title = str(row.get("标题", row.get("内容", ""))).strip()
        summary = str(row.get("摘要", row.get("内容", ""))).strip()
        if source == "sina" and title == summary:
            title = summary[:72] + ("..." if len(summary) > 72 else "")
        if not title:
            continue
        results.append({
            "title": title,
            "display_time": str(row.get("发布时间", row.get("时间", ""))),
            "summary": summary[:300],
            "url": str(row.get("链接", "")),
            "source": source_name,
            "source_channel": source_channel,
            "source_region": "cn",
            "source_priority": priority,
            "category": _classify_news(title, summary),
        })
    cache.set(cache_key, results, ttl_seconds=3 * 60)
    return results[:max_items]


def _fetch_sina_roll_news(max_items: int) -> list[dict[str, Any]]:
    import json
    import urllib.request

    try:
        url = SINA_ROLL_URL.format(max_items=max_items)
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
                "Referer": "https://finance.sina.com.cn/",
            },
        )
        resp = urllib.request.urlopen(req, timeout=10)
        raw = resp.read().decode("utf-8")
        data = json.loads(raw)

        items = data.get("result", {}).get("data", [])
        results = []
        for item in items[:max_items]:
            ctime = item.get("ctime", "")
            try:
                ts = int(ctime)
                display_time = datetime.fromtimestamp(ts).strftime("%m-%d %H:%M")
            except (ValueError, TypeError):
                display_time = ctime

            results.append({
                "title": item.get("title", ""),
                "display_time": display_time,
                "summary": item.get("intro", ""),
                "url": item.get("url", ""),
                "source": item.get("media_name", "新浪财经"),
                "source_channel": "sina_roll",
                "source_region": "cn",
                "source_priority": 26,
                "category": _classify_news(item.get("title", ""), item.get("intro", "")),
            })

        return results

    except Exception:
        return []


def _fetch_finnhub_company_news(symbol: str | None, max_items: int) -> list[dict[str, Any]]:
    """Fetch optional company news from Finnhub when FINNHUB_API_KEY is configured."""
    if not symbol:
        return []
    from config.settings import get_settings
    import json
    import urllib.request

    api_key = get_settings().finnhub_api_key
    if not api_key or api_key.lower().startswith(("your-", "replace-", "example-")):
        return []

    today = datetime.utcnow().date()
    start = today - timedelta(days=14)
    url = (
        "https://finnhub.io/api/v1/company-news"
        f"?symbol={quote_plus(symbol.upper())}&from={start.isoformat()}"
        f"&to={today.isoformat()}&token={quote_plus(api_key)}"
    )
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    raw = urllib.request.urlopen(req, timeout=10).read().decode("utf-8", "ignore")
    rows = json.loads(raw)
    results = []
    for item in rows[:max_items]:
        title = str(item.get("headline", ""))
        published = item.get("datetime")
        try:
            display_time = datetime.fromtimestamp(int(published)).strftime("%m-%d %H:%M")
        except (TypeError, ValueError):
            display_time = ""
        summary = str(item.get("summary", ""))
        results.append({
            "title": title,
            "display_time": display_time,
            "summary": summary[:300],
            "url": str(item.get("url", "")),
            "source": str(item.get("source", "Finnhub")),
            "source_channel": "finnhub_company_news",
            "source_region": "global",
            "source_priority": 34,
            "category": _classify_news(title, summary),
        })
    return results


def _fetch_akshare_stock_news(
    symbol: str | None, max_items: int
) -> list[dict[str, Any]]:
    """Fetch stock-specific news via AKShare."""
    if not symbol:
        return []
    import akshare as ak

    df = ak.stock_news_em(symbol=symbol)
    if df is None or df.empty:
        return []

    results = []
    for _, row in df.head(max_items).iterrows():
        title = str(row.get("标题", row.iloc[1] if len(row) > 1 else ""))
        results.append({
            "title": title,
            "display_time": str(row.get("发布时间", "")),
            "summary": str(row.get("摘要", row.get("内容", "")))[:200],
            "url": str(row.get("新闻链接", row.get("链接", ""))),
            "source": str(row.get("来源", "东方财富")),
            "source_channel": "akshare_stock_news_em",
            "source_region": "cn",
            "source_priority": 10,
            "category": _classify_news(title, str(row.get("摘要", row.get("内容", "")))),
        })
    return results


def _fetch_yahoo_finance_rss(symbol: str | None, max_items: int) -> list[dict[str, Any]]:
    if not symbol:
        return []
    url = (
        "https://feeds.finance.yahoo.com/rss/2.0/headline?"
        f"s={quote_plus(symbol.upper())}&region=US&lang=en-US"
    )
    return _fetch_rss(url, "Yahoo Finance", "yahoo_finance_rss", max_items, region="global", priority=36)


def _fetch_google_news_rss(query: str, max_items: int) -> list[dict[str, Any]]:
    q = f"{query} stock finance earnings macro policy"
    url = (
        "https://news.google.com/rss/search?"
        f"q={quote_plus(q)}&hl=en-US&gl=US&ceid=US:en"
    )
    return _fetch_rss(url, "Google News", "google_news_rss", max_items, region="global", priority=38)


def _fetch_rss(
    url: str,
    source_name: str,
    source_channel: str,
    max_items: int,
    *,
    region: str = "global",
    priority: int = 50,
) -> list[dict[str, Any]]:
    import urllib.request

    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0"},
    )
    raw = urllib.request.urlopen(req, timeout=10).read()
    root = ET.fromstring(raw)
    rows = []
    for item in root.findall(".//item")[:max_items]:
        title = (item.findtext("title") or "").strip()
        summary = (item.findtext("description") or "").strip()
        link = (item.findtext("link") or "").strip()
        published = (item.findtext("pubDate") or "").strip()
        if not title:
            continue
        rows.append({
            "title": title,
            "display_time": published,
            "summary": summary[:300],
            "url": link,
            "source": source_name,
            "source_channel": source_channel,
            "source_region": region,
            "source_priority": priority,
            "category": _classify_news(title, summary),
        })
    return rows


def _dedupe_news(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen = set()
    results = []
    for item in items:
        title = str(item.get("title", "")).strip()
        url = str(item.get("url", "")).strip()
        key = (title.lower(), url)
        if not title or key in seen:
            continue
        seen.add(key)
        results.append(item)
    return results


def is_company_news_item(item: dict[str, Any]) -> bool:
    """Return whether a normalized item is suitable for single-symbol analysis."""

    channel = str(item.get("source_channel", "")).strip()
    return not channel or channel in COMPANY_NEWS_CHANNELS


def _classify_news(title: str, summary: str = "") -> str:
    text = f"{title} {summary}".lower()
    if any(token in text for token in ["policy", "regulation", "tariff", "sanction", "fed", "sec", "政策", "监管", "关税", "制裁", "央行"]):
        return "policy"
    if any(token in text for token in ["earnings", "revenue", "guidance", "财报", "业绩", "利润", "营收"]):
        return "earnings"
    if any(token in text for token in ["inflation", "rates", "gdp", "macro", "通胀", "利率", "财政", "经济", "宏观"]):
        return "macro"
    return "market"
