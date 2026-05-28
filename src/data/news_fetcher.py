"""Financial news headline fetcher.

Uses AKShare stock_news_em for A-share stock-specific news, falling back to
Sina Finance roll API for general financial/policy news.

The Sina roll API returns current financial/policy news with ~200ms latency.
"""

from datetime import datetime
from typing import Any

from loguru import logger

SINA_ROLL_URL = (
    "https://feed.mix.sina.com.cn/api/roll/get"
    "?pageid=153&lid=2509&k=&num={max_items}&page=1"
)


def fetch_financial_news(
    symbol: str | None = None,
    max_items: int = 8,
) -> list[dict[str, Any]]:
    """Fetch financial news headlines, optionally symbol-specific.

    For A-share symbols, tries AKShare's stock_news_em first.
    Falls back to Sina Finance general roll API.

    Args:
        symbol: Optional stock ticker for symbol-specific news.
        max_items: Maximum number of news items to return (default 8).

    Returns:
        List of dicts with keys: title, display_time, summary, url, source.
        Empty list on any error.
    """
    import json
    import urllib.request

    # Try symbol-specific news via AKShare first
    if symbol:
        try:
            news = _fetch_akshare_stock_news(symbol, max_items)
            if news:
                return news
        except Exception:
            logger.debug(f"AKShare news failed for {symbol}, falling back to Sina")

    # Fall back to Sina general financial news
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
            })

        return results

    except Exception:
        return []


def _fetch_akshare_stock_news(
    symbol: str, max_items: int
) -> list[dict[str, Any]]:
    """Fetch stock-specific news via AKShare."""
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
        })
    return results
