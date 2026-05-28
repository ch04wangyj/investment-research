"""Market data tools for agents.

Each tool wraps a DAL method. Agents call these via LangChain tool binding.
"""

from typing import Any

from langchain_core.tools import tool
from loguru import logger

from src.data.dal import get_dal


@tool
def get_stock_quotes(symbol: str) -> dict[str, Any]:
    """Get the latest stock quote for a single symbol.

    Returns open/high/low/close/volume/change_pct for the current trading day.
    Works for A-shares (6-digit code like '600519'), HK stocks ('00700'),
    and US stocks ('AAPL').

    Args:
        symbol: Stock ticker symbol
    """
    logger.info(f"Tool: get_stock_quotes({symbol})")
    dal = get_dal()
    return dal.get_quotes(symbol)


@tool
def get_historical_prices(symbol: str, period: str = "6mo") -> list[dict[str, Any]]:
    """Get historical OHLCV data for a stock.

    Returns a list of daily records with date/open/high/low/close/volume.

    Args:
        symbol: Stock ticker symbol
        period: Time period — '1mo', '3mo', '6mo', '1y', '2y', '5y', 'max'
    """
    logger.info(f"Tool: get_historical_prices({symbol}, {period})")
    dal = get_dal()
    data = dal.get_historical(symbol, period)
    # Return last 60 records max to avoid overwhelming the LLM
    if len(data) > 60:
        # Return first 5 + last 55 (show trend endpoints)
        return data[:5] + data[-55:]
    return data


@tool
def get_fundamentals(symbol: str) -> dict[str, Any]:
    """Get fundamental financial data for a stock.

    Returns PE ratio, PB ratio, market cap, revenue, net income, ROE,
    ROA, debt-to-equity, dividend yield, sector, industry, and growth metrics.

    Args:
        symbol: Stock ticker symbol
    """
    logger.info(f"Tool: get_fundamentals({symbol})")
    dal = get_dal()
    return dal.get_fundamentals(symbol)


@tool
def get_financial_news(symbol: str) -> str:
    """Get recent financial news headlines for a stock.

    Fetches symbol-specific news where available; falls back to general
    financial news headlines. Works for A-shares, HK, and US stocks.

    Args:
        symbol: Stock ticker symbol
    """
    logger.info(f"Tool: get_financial_news({symbol})")
    try:
        from src.data.news_fetcher import fetch_financial_news
        news = fetch_financial_news(symbol=symbol, max_items=5)
    except Exception:
        news = []

    if not news:
        return f"No recent news found for {symbol}. Try web_search for broader coverage."

    lines = [f"Recent news for {symbol}:"]
    for item in news:
        lines.append(
            f"- [{item.get('display_time', '')}] {item['title']}"
            f" ({item.get('source', '')})"
        )
    return "\n".join(lines)
