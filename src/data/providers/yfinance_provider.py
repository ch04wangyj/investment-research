"""Yahoo Finance fallback provider for US stocks."""

import time
from datetime import datetime, timezone
from typing import Any

from loguru import logger

from src.data.providers.base import MarketDataProvider, ProviderResult, utc_now_iso

_RATE_LIMIT_SECONDS = 1.2
_LAST_REQUEST_TIME = 0.0


def _rate_limit():
    global _LAST_REQUEST_TIME
    now = time.time()
    elapsed = now - _LAST_REQUEST_TIME
    if elapsed < _RATE_LIMIT_SECONDS:
        time.sleep(_RATE_LIMIT_SECONDS - elapsed)
    _LAST_REQUEST_TIME = time.time()


class YfinanceProvider(MarketDataProvider):
    """US stock fallback via Yahoo Finance.

    It is intentionally not the primary US provider because Yahoo endpoints are
    unreliable from some mainland China networks.
    """

    def __init__(self):
        super().__init__(
            name="yfinance",
            market="us",
            currency="USD",
            timezone_name="America/New_York",
        )

    def get_quotes(self, symbols: list[str]) -> ProviderResult:
        try:
            import yfinance as yf

            _rate_limit()
            rows: list[dict[str, Any]] = []
            for sym in symbols:
                ticker = yf.Ticker(sym)
                info = {}
                try:
                    info = ticker.info or {}
                except Exception:
                    info = {}
                fi = ticker.fast_info
                rows.append({
                    "symbol": sym.upper(),
                    "name": info.get("shortName") or info.get("longName") or sym.upper(),
                    "market": self.market,
                    "currency": getattr(fi, "currency", "USD"),
                    "open": _value(getattr(fi, "open", None)),
                    "high": _value(getattr(fi, "day_high", None)),
                    "low": _value(getattr(fi, "day_low", None)),
                    "close": _value(getattr(fi, "last_price", None)),
                    "prev_close": _value(getattr(fi, "previous_close", None)),
                    "volume": _value(getattr(fi, "last_volume", None)),
                    "change_pct": None,
                    "timestamp": utc_now_iso(),
                })
            if not rows:
                return ProviderResult.failure(self.name, f"No Yahoo quote for {symbols}")
            return ProviderResult(source=self.name, payload=rows)
        except Exception as exc:
            logger.warning(f"{self.name}.get_quotes failed: {exc}")
            return ProviderResult.failure(self.name, str(exc))

    def get_historical(self, symbol: str, period: str = "6mo") -> ProviderResult:
        try:
            import pandas as pd
            import yfinance as yf

            _rate_limit()
            df = yf.Ticker(symbol).history(period=period)
            if df is None or df.empty:
                return ProviderResult.failure(self.name, f"No Yahoo history for {symbol}")
            df = df.reset_index()
            records = []
            for _, row in df.iterrows():
                date_value = row.get("Date")
                records.append({
                    "date": pd.to_datetime(date_value).strftime("%Y-%m-%d"),
                    "open": _value(row.get("Open")),
                    "high": _value(row.get("High")),
                    "low": _value(row.get("Low")),
                    "close": _value(row.get("Close")),
                    "volume": _value(row.get("Volume")),
                })
            return ProviderResult(source=self.name, payload=records)
        except Exception as exc:
            logger.warning(f"{self.name}.get_historical({symbol}) failed: {exc}")
            return ProviderResult.failure(self.name, str(exc))

    def get_fundamentals(self, symbol: str) -> ProviderResult:
        try:
            import yfinance as yf

            _rate_limit()
            ticker = yf.Ticker(symbol)
            info = {}
            try:
                info = ticker.info or {}
            except Exception:
                info = {}

            fi = ticker.fast_info
            payload = {
                "symbol": symbol.upper(),
                "market": self.market,
                "currency": getattr(fi, "currency", "USD"),
                "company_name": info.get("shortName") or info.get("longName") or symbol.upper(),
                "pe_ratio": info.get("trailingPE"),
                "forward_pe": info.get("forwardPE"),
                "pb_ratio": info.get("priceToBook"),
                "market_cap": info.get("marketCap") or _value(getattr(fi, "market_cap", None)),
                "revenue": info.get("totalRevenue"),
                "net_income": info.get("netIncomeToCommon"),
                "roe": info.get("returnOnEquity"),
                "roa": info.get("returnOnAssets"),
                "debt_to_equity": info.get("debtToEquity"),
                "dividend_yield": info.get("dividendYield"),
                "sector": info.get("sector"),
                "industry": info.get("industry"),
                "beta": info.get("beta"),
                "fifty_two_week_high": info.get("fiftyTwoWeekHigh")
                or _value(getattr(fi, "year_high", None)),
                "fifty_two_week_low": info.get("fiftyTwoWeekLow")
                or _value(getattr(fi, "year_low", None)),
                "profit_margins": info.get("profitMargins"),
                "revenue_growth": info.get("revenueGrowth"),
                "earnings_growth": info.get("earningsGrowth"),
            }
            return ProviderResult(source=self.name, payload=payload)
        except Exception as exc:
            logger.warning(f"{self.name}.get_fundamentals({symbol}) failed: {exc}")
            return ProviderResult.failure(self.name, str(exc))


def _value(value: Any) -> float | int | None:
    try:
        import pandas as pd

        if value is None or pd.isna(value):
            return None
    except Exception:
        if value is None:
            return None
    try:
        as_float = float(value)
    except (TypeError, ValueError):
        return value
    if as_float.is_integer():
        return int(as_float)
    return as_float


class YahooChartProvider(MarketDataProvider):
    """Direct Yahoo chart API fallback without yfinance's cookie layer."""

    def __init__(self, market: str):
        currency = {"ashare": "CNY", "hk": "HKD", "us": "USD"}[market]
        timezone_name = {
            "ashare": "Asia/Shanghai",
            "hk": "Asia/Hong_Kong",
            "us": "America/New_York",
        }[market]
        super().__init__(
            name=f"yahoo_chart_{market}",
            market=market,
            currency=currency,
            timezone_name=timezone_name,
        )

    def get_quotes(self, symbols: list[str]) -> ProviderResult:
        rows = []
        errors = []
        for symbol in symbols:
            result = self._chart(symbol, "5d")
            if not result.ok:
                errors.append(result.error or "unknown error")
                continue
            meta = result.payload["meta"]
            quotes = result.payload["quotes"]
            last = quotes[-1] if quotes else {}
            close = _value(meta.get("regularMarketPrice") or last.get("close"))
            prev_close = _value(meta.get("chartPreviousClose") or meta.get("previousClose"))
            change_pct = None
            if close is not None and prev_close:
                change_pct = (float(close) / float(prev_close) - 1) * 100
            rows.append({
                "symbol": symbol.upper(),
                "name": symbol.upper(),
                "market": self.market,
                "currency": meta.get("currency") or self.currency,
                "open": _value(last.get("open")),
                "high": _value(last.get("high")),
                "low": _value(last.get("low")),
                "close": close,
                "prev_close": prev_close,
                "volume": _value(last.get("volume")),
                "change_pct": change_pct,
                "timestamp": utc_now_iso(),
            })
        if not rows:
            return ProviderResult.failure(self.name, "; ".join(str(error) for error in errors))
        return ProviderResult(source=self.name, payload=rows)

    def get_historical(self, symbol: str, period: str = "6mo") -> ProviderResult:
        result = self._chart(symbol, _period_to_yahoo_range(period))
        if not result.ok:
            return result
        return ProviderResult(source=self.name, payload=result.payload["quotes"])

    def get_fundamentals(self, symbol: str) -> ProviderResult:
        quote = self.get_quotes([symbol])
        if not quote.ok:
            return quote
        row = quote.payload[0]
        return ProviderResult(
            source=self.name,
            payload={
                "symbol": symbol.upper(),
                "market": self.market,
                "currency": row.get("currency"),
                "company_name": row.get("name") or symbol.upper(),
                "current_price": row.get("close"),
                "pe_ratio": None,
                "pb_ratio": None,
                "market_cap": None,
            },
        )

    def _chart(self, symbol: str, range_value: str) -> ProviderResult:
        try:
            import httpx

            yahoo_symbol = self._format_symbol(symbol)
            url = (
                f"https://query1.finance.yahoo.com/v8/finance/chart/{yahoo_symbol}"
                f"?range={range_value}&interval=1d"
            )
            response = httpx.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
            response.raise_for_status()
            data = response.json()
            chart = data.get("chart", {})
            if chart.get("error"):
                return ProviderResult.failure(self.name, str(chart["error"]))
            result = (chart.get("result") or [None])[0]
            if not result:
                return ProviderResult.failure(self.name, "empty Yahoo chart response")
            meta = result.get("meta", {})
            timestamps = result.get("timestamp") or []
            quote = ((result.get("indicators") or {}).get("quote") or [{}])[0]
            records = []
            for idx, ts in enumerate(timestamps):
                close = _value(_at(quote.get("close"), idx))
                if close is None:
                    continue
                records.append({
                    "date": datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%d"),
                    "open": _value(_at(quote.get("open"), idx)),
                    "high": _value(_at(quote.get("high"), idx)),
                    "low": _value(_at(quote.get("low"), idx)),
                    "close": close,
                    "volume": _value(_at(quote.get("volume"), idx)),
                })
            if not records:
                return ProviderResult.failure(self.name, "Yahoo chart returned no quotes")
            return ProviderResult(source=self.name, payload={"meta": meta, "quotes": records})
        except Exception as exc:
            logger.warning(f"{self.name}._chart({symbol}) failed: {exc}")
            return ProviderResult.failure(self.name, str(exc))

    def _format_symbol(self, symbol: str) -> str:
        symbol = symbol.upper()
        if self.market == "us":
            return symbol
        if self.market == "hk":
            return f"{int(symbol):04d}.HK"
        suffix = "SS" if symbol.startswith(("5", "6", "9")) else "SZ"
        return f"{symbol.zfill(6)}.{suffix}"


def _period_to_yahoo_range(period: str) -> str:
    return {
        "1mo": "1mo",
        "3mo": "3mo",
        "6mo": "6mo",
        "1y": "1y",
        "2y": "2y",
        "5y": "5y",
        "max": "10y",
    }.get(period, "6mo")


def _at(values: Any, idx: int) -> Any:
    if not isinstance(values, list) or idx >= len(values):
        return None
    return values[idx]
