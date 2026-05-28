"""Yahoo Finance fallback provider for US stocks."""

import time
from datetime import datetime, timezone
from typing import Any

from loguru import logger

from src.data.providers.base import MarketDataProvider, ProviderResult, utc_now_iso

_RATE_LIMIT_SECONDS = 1.2
_LAST_REQUEST_TIME = 0.0
_NASDAQ_HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "application/json, text/plain, */*",
    "Origin": "https://www.nasdaq.com",
    "Referer": "https://www.nasdaq.com/",
}


def _rate_limit():
    global _LAST_REQUEST_TIME
    now = time.time()
    elapsed = now - _LAST_REQUEST_TIME
    if elapsed < _RATE_LIMIT_SECONDS:
        time.sleep(_RATE_LIMIT_SECONDS - elapsed)
    _LAST_REQUEST_TIME = time.time()


class NasdaqUsProvider(MarketDataProvider):
    """US quote and fundamentals from Nasdaq's public website API."""

    def __init__(self):
        super().__init__(
            name="nasdaq_us",
            market="us",
            currency="USD",
            timezone_name="America/New_York",
        )

    def get_quotes(self, symbols: list[str]) -> ProviderResult:
        rows = []
        errors = []
        for symbol in symbols:
            try:
                info = _nasdaq_json(f"https://api.nasdaq.com/api/quote/{symbol.upper()}/info?assetclass=stocks")
                summary = _nasdaq_json(f"https://api.nasdaq.com/api/quote/{symbol.upper()}/summary?assetclass=stocks")
                primary = info.get("primaryData", {}) or {}
                summary_data = summary.get("summaryData", {}) or {}
                close = _parse_number(primary.get("lastSalePrice"))
                prev_close = _parse_number(_nasdaq_value(summary_data, "PreviousClose"))
                change_pct = _parse_number(primary.get("percentageChange"))
                if change_pct is None and close is not None and prev_close:
                    change_pct = (float(close) / float(prev_close) - 1) * 100
                rows.append({
                    "symbol": symbol.upper(),
                    "name": str(info.get("companyName") or symbol.upper()),
                    "market": self.market,
                    "currency": primary.get("currency") or self.currency,
                    "open": None,
                    "high": None,
                    "low": None,
                    "close": close,
                    "prev_close": prev_close,
                    "volume": _parse_number(primary.get("volume")),
                    "change_pct": change_pct,
                    "timestamp": utc_now_iso(),
                })
            except Exception as exc:
                errors.append(f"{symbol}: {exc}")
        if not rows:
            return ProviderResult.failure(self.name, "; ".join(errors) or "empty Nasdaq quote response")
        return ProviderResult(source=self.name, payload=rows)

    def get_historical(self, symbol: str, period: str = "6mo") -> ProviderResult:
        return ProviderResult.failure(self.name, "Nasdaq provider does not expose daily history")

    def get_fundamentals(self, symbol: str) -> ProviderResult:
        try:
            symbol = symbol.upper()
            summary = _nasdaq_json(f"https://api.nasdaq.com/api/quote/{symbol}/summary?assetclass=stocks")
            profile = _nasdaq_json(f"https://api.nasdaq.com/api/company/{symbol}/company-profile")
            financials = _nasdaq_json(f"https://api.nasdaq.com/api/company/{symbol}/financials?frequency=1")

            summary_data = summary.get("summaryData", {}) or {}
            income = (financials.get("incomeStatementTable", {}) or {}).get("rows", []) or []
            balance = (financials.get("balanceSheetTable", {}) or {}).get("rows", []) or []
            ratios = (financials.get("financialRatiosTable", {}) or {}).get("rows", []) or []

            market_cap = _parse_number(_nasdaq_value(summary_data, "MarketCap"))
            revenue = _table_value(income, "Total Revenue", scale=1000)
            net_income = (
                _table_value(income, "Net Income", scale=1000)
                or _table_value(income, "Net Income Applicable to Common Shareholders", scale=1000)
            )
            equity = _table_value(balance, "Total Equity", scale=1000)
            pe_ratio = market_cap / net_income if market_cap and net_income else None
            pb_ratio = market_cap / equity if market_cap and equity else None
            roe = net_income / equity if net_income and equity else _parse_percent(_table_value(ratios, "After Tax ROE"))
            profit_margins = net_income / revenue if net_income and revenue else _parse_percent(_table_value(ratios, "Profit Margin"))

            payload = {
                "symbol": symbol,
                "market": self.market,
                "currency": self.currency,
                "company_name": _nasdaq_value(profile, "CompanyName") or symbol,
                "pe_ratio": pe_ratio,
                "forward_pe": None,
                "pb_ratio": pb_ratio,
                "market_cap": market_cap,
                "revenue": revenue,
                "net_income": net_income,
                "roe": roe,
                "roa": None,
                "debt_to_equity": None,
                "dividend_yield": _parse_percent(_nasdaq_value(summary_data, "Yield")),
                "sector": _nasdaq_value(summary_data, "Sector") or _nasdaq_value(profile, "Sector"),
                "industry": _nasdaq_value(summary_data, "Industry") or _nasdaq_value(profile, "Industry"),
                "beta": None,
                "fifty_two_week_high": _split_high_low(_nasdaq_value(summary_data, "FiftTwoWeekHighLow"))[0],
                "fifty_two_week_low": _split_high_low(_nasdaq_value(summary_data, "FiftTwoWeekHighLow"))[1],
                "profit_margins": profit_margins,
                "revenue_growth": None,
                "earnings_growth": None,
            }
            return ProviderResult(source=self.name, payload=payload)
        except Exception as exc:
            logger.warning(f"{self.name}.get_fundamentals({symbol}) failed: {exc}")
            return ProviderResult.failure(self.name, str(exc))


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
                    "currency": _fast_info_get(fi, "currency", "USD"),
                    "open": _value(_fast_info_get(fi, "open")),
                    "high": _value(_fast_info_get(fi, "day_high")),
                    "low": _value(_fast_info_get(fi, "day_low")),
                    "close": _value(_fast_info_get(fi, "last_price")),
                    "prev_close": _value(_fast_info_get(fi, "previous_close")),
                    "volume": _value(_fast_info_get(fi, "last_volume")),
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
                "currency": _fast_info_get(fi, "currency", "USD"),
                "company_name": info.get("shortName") or info.get("longName") or symbol.upper(),
                "pe_ratio": info.get("trailingPE"),
                "forward_pe": info.get("forwardPE"),
                "pb_ratio": info.get("priceToBook"),
                "market_cap": info.get("marketCap") or _value(_fast_info_get(fi, "market_cap")),
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
                or _value(_fast_info_get(fi, "year_high")),
                "fifty_two_week_low": info.get("fiftyTwoWeekLow")
                or _value(_fast_info_get(fi, "year_low")),
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


def _fast_info_get(fast_info: Any, key: str, default: Any = None) -> Any:
    """Read yfinance fast_info without letting missing keys fail the provider."""
    try:
        if hasattr(fast_info, "get"):
            return fast_info.get(key, default)
    except Exception:
        pass
    try:
        return getattr(fast_info, key)
    except Exception:
        pass
    try:
        return fast_info[key]
    except Exception:
        return default


def _nasdaq_json(url: str) -> dict[str, Any]:
    import httpx

    _rate_limit()
    response = httpx.get(url, headers=_NASDAQ_HEADERS, timeout=15)
    response.raise_for_status()
    data = response.json()
    payload = data.get("data")
    if not isinstance(payload, dict):
        raise ValueError("empty Nasdaq response")
    return payload


def _nasdaq_value(data: dict[str, Any], key: str) -> Any:
    item = data.get(key)
    if isinstance(item, dict):
        return item.get("value")
    return item


def _table_value(rows: list[dict[str, Any]], label: str, scale: float = 1) -> float | None:
    for row in rows:
        if str(row.get("value1", "")).strip().lower() == label.lower():
            value = _parse_number(row.get("value2"))
            return value * scale if value is not None else None
    return None


def _parse_number(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text in {"N/A", "--"}:
        return None
    negative = text.startswith("-")
    text = text.replace("$", "").replace(",", "").replace("%", "").replace("(", "").replace(")", "")
    text = text.lstrip("+-")
    try:
        number = float(text)
    except ValueError:
        return None
    return -number if negative else number


def _parse_percent(value: Any) -> float | None:
    number = _parse_number(value)
    if number is None:
        return None
    if "%" in str(value):
        return number / 100
    return number / 100 if abs(number) > 1 else number


def _split_high_low(value: Any) -> tuple[float | None, float | None]:
    text = str(value or "")
    if "/" not in text:
        return None, None
    high, low = text.split("/", 1)
    return _parse_number(high), _parse_number(low)


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
