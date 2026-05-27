"""Data Access Layer with provider registry, fallback, and stale cache recovery."""

from datetime import datetime
from typing import Any, Callable

import pandas as pd
from loguru import logger

from src.data.cache import get_cache
from src.data.providers.akshare_provider import (
    AshareAkshareProvider,
    HkAkshareProvider,
    SinaAshareProvider,
    SinaHkProvider,
    UsAkshareProvider,
)
from src.data.providers.base import MarketDataProvider, ProviderResult
from src.data.providers.yfinance_provider import YahooChartProvider, YfinanceProvider


class DataAccessLayer:
    """Single entry point for market data.

    Every successful response carries source/as_of/stale/error metadata. Legacy
    helpers still return simple dict/list payloads so the old Streamlit pages
    continue to work.
    """

    def __init__(
        self,
        providers: dict[str, list[MarketDataProvider]] | None = None,
        cache: Any | None = None,
    ):
        self._cache = cache or get_cache()
        self._providers = providers or {
            "ashare": [AshareAkshareProvider(), SinaAshareProvider(), YahooChartProvider("ashare")],
            "hk": [HkAkshareProvider(), SinaHkProvider(), YahooChartProvider("hk")],
            "us": [UsAkshareProvider(), YahooChartProvider("us"), YfinanceProvider()],
        }

    def detect_exchange(self, symbol: str) -> str:
        return detect_market(symbol)

    def provider_names(self) -> dict[str, list[str]]:
        return {
            market: [provider.name for provider in providers]
            for market, providers in self._providers.items()
        }

    def get_quote_result(self, symbol: str) -> ProviderResult:
        market = self.detect_exchange(symbol)
        normalized = normalize_symbol(symbol, market)
        return self._fetch(
            market=market,
            cache_key=f"quote:{market}:{normalized}",
            ttl_seconds=900,
            method=lambda provider: provider.get_quotes([normalized]),
        )

    def get_history_result(self, symbol: str, period: str = "6mo") -> ProviderResult:
        market = self.detect_exchange(symbol)
        normalized = normalize_symbol(symbol, market)
        return self._fetch(
            market=market,
            cache_key=f"hist:{market}:{normalized}:{period}",
            ttl_seconds=900,
            method=lambda provider: provider.get_historical(normalized, period),
        )

    def get_fundamentals_result(self, symbol: str) -> ProviderResult:
        market = self.detect_exchange(symbol)
        normalized = normalize_symbol(symbol, market)
        return self._fetch(
            market=market,
            cache_key=f"fund:{market}:{normalized}",
            ttl_seconds=86400,
            method=lambda provider: provider.get_fundamentals(normalized),
        )

    def get_symbol_profile(self, symbol: str, period: str = "6mo") -> dict[str, Any]:
        market = self.detect_exchange(symbol)
        normalized = normalize_symbol(symbol, market)
        quote = self.get_quote_result(normalized)
        fundamentals = self.get_fundamentals_result(normalized)
        history = self.get_history_result(normalized, period)
        return {
            "symbol": normalized,
            "market": market,
            "quote": quote.to_dict(),
            "fundamentals": fundamentals.to_dict(),
            "history": history.to_dict(),
        }

    def get_quotes(self, symbol: str) -> dict[str, Any]:
        result = self.get_quote_result(symbol)
        if not result.ok:
            return {"error": result.error, "_meta": _meta(result)}
        payload = result.payload[0] if isinstance(result.payload, list) and result.payload else result.payload
        return {**payload, "_meta": _meta(result)}

    def get_historical(self, symbol: str, period: str = "6mo") -> list[dict[str, Any]]:
        result = self.get_history_result(symbol, period)
        return result.payload if result.ok and isinstance(result.payload, list) else []

    def get_fundamentals(self, symbol: str) -> dict[str, Any]:
        result = self.get_fundamentals_result(symbol)
        if not result.ok:
            return {"error": result.error, "_meta": _meta(result)}
        return {**(result.payload or {}), "_meta": _meta(result)}

    def get_historical_df(self, symbol: str, period: str = "6mo") -> pd.DataFrame:
        rows = self.get_historical(symbol, period)
        if not rows:
            return pd.DataFrame()
        df = pd.DataFrame(rows)
        if "date" in df.columns:
            df["date"] = pd.to_datetime(df["date"])
        return df

    def _fetch(
        self,
        *,
        market: str,
        cache_key: str,
        ttl_seconds: int,
        method: Callable[[MarketDataProvider], ProviderResult],
    ) -> ProviderResult:
        cached = self._cache.get(cache_key)
        if cached is not None:
            result = ProviderResult.from_dict(cached)
            result.source = f"{result.source}:cache"
            return result

        errors: list[str] = []
        for provider in self._providers.get(market, []):
            result = method(provider)
            if result.ok:
                self._cache.set(cache_key, result.to_dict(), ttl_seconds=ttl_seconds)
                return result
            errors.append(f"{provider.name}: {result.error}")

        stale = self._cache.get_stale(cache_key)
        if stale is not None:
            result = ProviderResult.from_dict(stale)
            result.stale = True
            result.error = "; ".join(errors) or "all providers failed"
            result.source = f"{result.source}:stale-cache"
            return result

        logger.warning(f"All providers failed for {cache_key}: {errors}")
        return ProviderResult.failure(
            source=f"{market}:provider_registry",
            error="; ".join(errors) if errors else f"No providers registered for {market}",
        )


def detect_market(symbol: str) -> str:
    symbol = symbol.strip().upper()
    if symbol.isdigit() and len(symbol) == 6:
        return "ashare"
    if symbol.isdigit() and len(symbol) == 5:
        return "hk"
    return "us"


def normalize_symbol(symbol: str, market: str | None = None) -> str:
    symbol = symbol.strip().upper()
    market = market or detect_market(symbol)
    if market == "ashare":
        return symbol.zfill(6)
    if market == "hk":
        return symbol.zfill(5)
    return symbol


def _meta(result: ProviderResult) -> dict[str, Any]:
    return {
        "source": result.source,
        "as_of": result.as_of,
        "stale": result.stale,
        "error": result.error,
        "received_at": datetime.now().isoformat(),
    }


_dal: DataAccessLayer | None = None


def get_dal() -> DataAccessLayer:
    global _dal
    if _dal is None:
        _dal = DataAccessLayer()
    return _dal
