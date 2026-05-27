"""Financial news headline fetcher.

Uses Sina Finance roll API since AKShare news functions (news_cctv, stock_news_em,
news_economic_baidu) are either too slow, broken, or return stale data.

The Sina roll API returns current financial/policy news with ~200ms latency.
"""

from datetime import datetime
from typing import Any

import streamlit as st

SINA_ROLL_URL = (
    "https://feed.mix.sina.com.cn/api/roll/get"
    "?pageid=153&lid=2509&k=&num={max_items}&page=1"
)


@st.cache_data(ttl=600, show_spinner=False)
def fetch_financial_news(max_items: int = 8) -> list[dict[str, Any]]:
    """Fetch recent financial/policy news headlines from Sina Finance.

    Args:
        max_items: Maximum number of news items to return (default 8).

    Returns:
        List of dicts with keys: title, display_time, summary, url, source.
        Empty list on any error.
    """
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
            })

        return results

    except Exception:
        return []
