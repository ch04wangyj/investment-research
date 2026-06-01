"""Web search tool for agents.

Uses DuckDuckGo's static HTML endpoint with rate limiting.
Phase 2 can add Tavily/SerpAPI as alternative backends.
"""

import time

from langchain_core.tools import tool
from loguru import logger

from src.research.source_collector import _search_web

# Rate limit: 1 request per 3 seconds (DuckDuckGo is strict)
_LAST_SEARCH_TIME = 0.0


def _rate_limit():
    global _LAST_SEARCH_TIME
    now = time.time()
    elapsed = now - _LAST_SEARCH_TIME
    if elapsed < 3.0:
        time.sleep(3.0 - elapsed)
    _LAST_SEARCH_TIME = time.time()


@tool
def web_search(query: str) -> str:
    """Search the web for recent financial information, news, or analysis.

    Use this to find:
    - Recent news about a company or sector
    - Analyst reports and earnings call summaries
    - Macroeconomic data and policy changes
    - Market sentiment and trends

    Args:
        query: Search query string (be specific, include ticker or company name)
    """
    logger.info(f"Tool: web_search({query[:80]}...)")
    _rate_limit()

    try:
        results = [
            {
                "title": row.get("title", ""),
                "snippet": row.get("summary", ""),
                "url": row.get("url", ""),
            }
            for row in _search_web(query, max_results=5)
        ]

        if not results:
            return f"No search results found for: {query}"

        formatted = []
        for i, r in enumerate(results):
            formatted.append(
                f"[{i+1}] {r['title']}\n"
                f"    {r['snippet']}\n"
                f"    URL: {r['url']}"
            )
        return "\n\n".join(formatted)

    except Exception as e:
        logger.error(f"web_search failed: {e}")
        return f"Search failed: {e}. Try a different query."
