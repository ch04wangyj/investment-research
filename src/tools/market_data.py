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
    """Search for recent financial news about a stock.

    Currently uses web search; in Phase 2 this will integrate Finnhub/news APIs.

    Args:
        symbol: Stock ticker symbol (add company name for better results)
    """
    logger.info(f"Tool: get_financial_news({symbol})")
    # Placeholder — Phase 2 will integrate Finnhub/SerpAPI
    # For now, returns a note that the LLM should use web_search instead
    return (
        f"News data for {symbol} is not yet available via direct API. "
        f"Use the web_search tool to find recent news about {symbol}. "
        f"In Phase 2, this will integrate Finnhub and RSS feeds."
    )
