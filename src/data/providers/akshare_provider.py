"""AKShare providers for A-share, Hong Kong, and US equities."""

import json
import re
from datetime import datetime, timedelta
from typing import Any

import pandas as pd
from loguru import logger

from src.data.providers.base import MarketDataProvider, ProviderResult, utc_now_iso


class AshareAkshareProvider(MarketDataProvider):
    def __init__(self):
        super().__init__(
            name="akshare_ashare",
            market="ashare",
            currency="CNY",
            timezone_name="Asia/Shanghai",
        )

    def get_quotes(self, symbols: list[str]) -> ProviderResult:
        try:
            import akshare as ak

            df = ak.stock_zh_a_spot_em()
            df["symbol"] = df["代码"].astype(str).str.zfill(6)
            filtered = df[df["symbol"].isin([s.zfill(6) for s in symbols])].copy()
            if filtered.empty:
                return ProviderResult.failure(self.name, f"No A-share quote for {symbols}")

            records = []
            for _, row in filtered.iterrows():
                records.append({
                    "symbol": row["symbol"],
                    "name": _clean(row.get("名称")),
                    "market": self.market,
                    "currency": self.currency,
                    "open": _num(row.get("今开")),
                    "high": _num(row.get("最高")),
                    "low": _num(row.get("最低")),
                    "close": _num(row.get("最新价")),
                    "prev_close": _num(row.get("昨收")),
                    "volume": _num(row.get("成交量")),
                    "amount": _num(row.get("成交额")),
                    "change_pct": _num(row.get("涨跌幅")),
                    "timestamp": utc_now_iso(),
                })
            return ProviderResult(source=self.name, payload=records)
        except Exception as exc:
            logger.warning(f"{self.name}.get_quotes failed: {exc}")
            return ProviderResult.failure(self.name, str(exc))

    def get_historical(self, symbol: str, period: str = "6mo") -> ProviderResult:
        try:
            import akshare as ak

            days = _period_to_days(period)
            start_date = (datetime.now() - timedelta(days=days)).strftime("%Y%m%d")
            end_date = datetime.now().strftime("%Y%m%d")
            df = ak.stock_zh_a_hist(
                symbol=symbol.zfill(6),
                period="daily",
                start_date=start_date,
                end_date=end_date,
                adjust="qfq",
            )
            records = _ohlcv_records(
                df,
                date_col="日期",
                open_col="开盘",
                high_col="最高",
                low_col="最低",
                close_col="收盘",
                volume_col="成交量",
            )
            if not records:
                return ProviderResult.failure(self.name, f"No A-share history for {symbol}")
            return ProviderResult(source=self.name, payload=records)
        except Exception as exc:
            logger.warning(f"{self.name}.get_historical({symbol}) failed: {exc}")
            return ProviderResult.failure(self.name, str(exc))

    def get_fundamentals(self, symbol: str) -> ProviderResult:
        try:
            import akshare as ak

            info_df = ak.stock_individual_info_em(symbol=symbol.zfill(6))
            info: dict[str, Any] = {}
            if info_df is not None and not info_df.empty:
                for _, row in info_df.iterrows():
                    info[str(row["item"])] = row["value"]

            latest: dict[str, Any] = {}
            fin_df = ak.stock_financial_analysis_indicator(symbol=symbol.zfill(6))
            if fin_df is not None and not fin_df.empty:
                latest_row = fin_df.iloc[0]
                latest["roe"] = _num(latest_row.get("净资产收益率"))
                latest["eps"] = _num(latest_row.get("每股收益"))

            payload = {
                "symbol": symbol.zfill(6),
                "market": self.market,
                "currency": self.currency,
                "company_name": _clean(info.get("股票简称") or info.get("简称")),
                "pe_ratio": _num(info.get("市盈率-动态")),
                "pb_ratio": _num(info.get("市净率")),
                "market_cap": _num(info.get("总市值")),
                "revenue": _num(info.get("营业收入")),
                "net_income": _num(info.get("净利润")),
                "roe": latest.get("roe"),
                "eps": latest.get("eps"),
                "sector": _clean(info.get("行业")),
                "total_shares": _num(info.get("总股本")),
            }
            return ProviderResult(source=self.name, payload=payload)
        except Exception as exc:
            logger.warning(f"{self.name}.get_fundamentals({symbol}) failed: {exc}")
            return ProviderResult.failure(self.name, str(exc))


class HkAkshareProvider(MarketDataProvider):
    def __init__(self):
        super().__init__(
            name="akshare_hk",
            market="hk",
            currency="HKD",
            timezone_name="Asia/Hong_Kong",
        )

    def get_quotes(self, symbols: list[str]) -> ProviderResult:
        try:
            import akshare as ak

            df = ak.stock_hk_spot_em()
            df["symbol"] = df["代码"].astype(str).str.zfill(5)
            wanted = [s.zfill(5) for s in symbols]
            filtered = df[df["symbol"].isin(wanted)].copy()
            if filtered.empty:
                return ProviderResult.failure(self.name, f"No HK quote for {symbols}")

            records = []
            for _, row in filtered.iterrows():
                records.append({
                    "symbol": row["symbol"],
                    "name": _clean(row.get("名称")),
                    "market": self.market,
                    "currency": self.currency,
                    "open": _num(row.get("今开")),
                    "high": _num(row.get("最高")),
                    "low": _num(row.get("最低")),
                    "close": _num(row.get("最新价")),
                    "prev_close": _num(row.get("昨收")),
                    "volume": _num(row.get("成交量")),
                    "amount": _num(row.get("成交额")),
                    "change_pct": _num(row.get("涨跌幅")),
                    "timestamp": utc_now_iso(),
                })
            return ProviderResult(source=self.name, payload=records)
        except Exception as exc:
            logger.warning(f"{self.name}.get_quotes failed: {exc}")
            return ProviderResult.failure(self.name, str(exc))

    def get_historical(self, symbol: str, period: str = "6mo") -> ProviderResult:
        try:
            import akshare as ak

            days = _period_to_days(period)
            start_date = (datetime.now() - timedelta(days=days)).strftime("%Y%m%d")
            end_date = datetime.now().strftime("%Y%m%d")
            df = ak.stock_hk_hist(
                symbol=symbol.zfill(5),
                period="daily",
                start_date=start_date,
                end_date=end_date,
                adjust="qfq",
            )
            records = _ohlcv_records(
                df,
                date_col="日期",
                open_col="开盘",
                high_col="最高",
                low_col="最低",
                close_col="收盘",
                volume_col="成交量",
            )
            if not records:
                return ProviderResult.failure(self.name, f"No HK history for {symbol}")
            return ProviderResult(source=self.name, payload=records)
        except Exception as exc:
            logger.warning(f"{self.name}.get_historical({symbol}) failed: {exc}")
            return ProviderResult.failure(self.name, str(exc))

    def get_fundamentals(self, symbol: str) -> ProviderResult:
        quote = self.get_quotes([symbol])
        if not quote.ok:
            return quote
        row = quote.payload[0]
        payload = {
            "symbol": symbol.zfill(5),
            "market": self.market,
            "currency": self.currency,
            "company_name": row.get("name"),
            "current_price": row.get("close"),
            "pe_ratio": None,
            "pb_ratio": None,
            "market_cap": None,
            "sector": None,
            "industry": None,
        }
        return ProviderResult(source=self.name, payload=payload)


class UsAkshareProvider(MarketDataProvider):
    def __init__(self):
        super().__init__(
            name="akshare_us",
            market="us",
            currency="USD",
            timezone_name="America/New_York",
        )

    def get_quotes(self, symbols: list[str]) -> ProviderResult:
        try:
            import akshare as ak

            df = ak.stock_us_spot_em()
            symbol_col = _first_existing(df, ["代码", "symbol", "Symbol"])
            if symbol_col is None:
                return ProviderResult.failure(self.name, "US spot data has no symbol column")
            df["symbol"] = df[symbol_col].astype(str).str.upper()
            wanted = [s.upper() for s in symbols]
            filtered = df[df["symbol"].isin(wanted)].copy()
            if filtered.empty:
                return ProviderResult.failure(self.name, f"No US quote for {symbols}")

            records = []
            for _, row in filtered.iterrows():
                records.append({
                    "symbol": row["symbol"],
                    "name": _clean(row.get("名称") or row.get("name") or row["symbol"]),
                    "market": self.market,
                    "currency": self.currency,
                    "open": _num(row.get("开盘价") or row.get("今开")),
                    "high": _num(row.get("最高价") or row.get("最高")),
                    "low": _num(row.get("最低价") or row.get("最低")),
                    "close": _num(row.get("最新价")),
                    "prev_close": _num(row.get("昨收价") or row.get("昨收")),
                    "volume": _num(row.get("成交量")),
                    "amount": _num(row.get("成交额")),
                    "change_pct": _num(row.get("涨跌幅")),
                    "timestamp": utc_now_iso(),
                })
            return ProviderResult(source=self.name, payload=records)
        except Exception as exc:
            logger.warning(f"{self.name}.get_quotes failed: {exc}")
            return ProviderResult.failure(self.name, str(exc))

    def get_historical(self, symbol: str, period: str = "6mo") -> ProviderResult:
        try:
            import akshare as ak

            days = _period_to_days(period)
            start = datetime.now() - timedelta(days=days)
            df = ak.stock_us_daily(symbol=symbol.upper())
            if df is None or df.empty:
                return ProviderResult.failure(self.name, f"No US history for {symbol}")
            df["date"] = pd.to_datetime(df["date"])
            df = df[df["date"] >= pd.Timestamp(start)]
            records = _ohlcv_records(
                df,
                date_col="date",
                open_col="open",
                high_col="high",
                low_col="low",
                close_col="close",
                volume_col="volume",
            )
            if not records:
                return ProviderResult.failure(self.name, f"No US history for {symbol}")
            return ProviderResult(source=self.name, payload=records)
        except Exception as exc:
            logger.warning(f"{self.name}.get_historical({symbol}) failed: {exc}")
            return ProviderResult.failure(self.name, str(exc))

    def get_fundamentals(self, symbol: str) -> ProviderResult:
        quote = self.get_quotes([symbol])
        if not quote.ok:
            return quote
        row = quote.payload[0]
        payload = {
            "symbol": symbol.upper(),
            "market": self.market,
            "currency": self.currency,
            "company_name": row.get("name"),
            "current_price": row.get("close"),
            "pe_ratio": None,
            "pb_ratio": None,
            "market_cap": None,
            "sector": None,
            "industry": None,
        }
        return ProviderResult(source=self.name, payload=payload)


class SinaAshareProvider(MarketDataProvider):
    def __init__(self):
        super().__init__(
            name="sina_ashare",
            market="ashare",
            currency="CNY",
            timezone_name="Asia/Shanghai",
        )

    def get_quotes(self, symbols: list[str]) -> ProviderResult:
        try:
            import httpx

            sina_symbols = [_sina_ashare_symbol(symbol) for symbol in symbols]
            response = httpx.get(
                "https://hq.sinajs.cn/list=" + ",".join(sina_symbols),
                headers=_sina_headers(),
                timeout=15,
            )
            response.encoding = "gbk"
            records = []
            for match in re.finditer(r'var hq_str_(?P<code>\w+)="(?P<body>.*?)";', response.text):
                code = match.group("code")
                fields = match.group("body").split(",")
                if len(fields) < 32 or not fields[0]:
                    continue
                symbol = code[-6:]
                prev_close = _num(fields[2])
                close = _num(fields[3])
                change_pct = None
                if prev_close and close is not None:
                    change_pct = (close / prev_close - 1) * 100
                records.append({
                    "symbol": symbol,
                    "name": fields[0],
                    "market": self.market,
                    "currency": self.currency,
                    "open": _num(fields[1]),
                    "prev_close": prev_close,
                    "close": close,
                    "high": _num(fields[4]),
                    "low": _num(fields[5]),
                    "volume": _num(fields[8]),
                    "amount": _num(fields[9]),
                    "change_pct": change_pct,
                    "timestamp": f"{fields[30]} {fields[31]}",
                })
            if not records:
                return ProviderResult.failure(self.name, f"No Sina A-share quote for {symbols}")
            return ProviderResult(source=self.name, payload=records)
        except Exception as exc:
            logger.warning(f"{self.name}.get_quotes failed: {exc}")
            return ProviderResult.failure(self.name, str(exc))

    def get_historical(self, symbol: str, period: str = "6mo") -> ProviderResult:
        try:
            import httpx

            days = _period_to_days(period)
            url = (
                "https://quotes.sina.cn/cn/api/jsonp_v2.php/var%20data=/"
                "CN_MarketDataService.getKLineData"
                f"?symbol={_sina_ashare_symbol(symbol)}&scale=240&ma=no&datalen={days}"
            )
            response = httpx.get(url, headers=_sina_headers(), timeout=15)
            match = re.search(r"var data=\((.*)\);", response.text, flags=re.DOTALL)
            if not match:
                return ProviderResult.failure(self.name, "Unexpected Sina history response")
            raw = json.loads(match.group(1))
            records = [
                {
                    "date": row.get("day"),
                    "open": _num(row.get("open")),
                    "high": _num(row.get("high")),
                    "low": _num(row.get("low")),
                    "close": _num(row.get("close")),
                    "volume": _num(row.get("volume")),
                }
                for row in raw
            ]
            if not records:
                return ProviderResult.failure(self.name, f"No Sina A-share history for {symbol}")
            return ProviderResult(source=self.name, payload=records)
        except Exception as exc:
            logger.warning(f"{self.name}.get_historical({symbol}) failed: {exc}")
            return ProviderResult.failure(self.name, str(exc))

    def get_fundamentals(self, symbol: str) -> ProviderResult:
        quote = self.get_quotes([symbol])
        if not quote.ok:
            return quote
        row = quote.payload[0]
        return ProviderResult(
            source=self.name,
            payload={
                "symbol": row.get("symbol"),
                "market": self.market,
                "currency": self.currency,
                "company_name": row.get("name"),
                "current_price": row.get("close"),
                "pe_ratio": None,
                "pb_ratio": None,
                "market_cap": None,
            },
        )


class SinaHkProvider(MarketDataProvider):
    def __init__(self):
        super().__init__(
            name="sina_hk",
            market="hk",
            currency="HKD",
            timezone_name="Asia/Hong_Kong",
        )

    def get_quotes(self, symbols: list[str]) -> ProviderResult:
        try:
            import httpx

            sina_symbols = ["hk" + symbol.zfill(5) for symbol in symbols]
            response = httpx.get(
                "https://hq.sinajs.cn/list=" + ",".join(sina_symbols),
                headers=_sina_headers(),
                timeout=15,
            )
            response.encoding = "gbk"
            records = []
            for match in re.finditer(r'var hq_str_(?P<code>\w+)="(?P<body>.*?)";', response.text):
                fields = match.group("body").split(",")
                if len(fields) < 18 or not fields[0]:
                    continue
                symbol = match.group("code")[-5:]
                records.append({
                    "symbol": symbol,
                    "name": fields[1] or fields[0],
                    "market": self.market,
                    "currency": self.currency,
                    "open": _num(fields[2]),
                    "prev_close": _num(fields[3]),
                    "high": _num(fields[4]),
                    "low": _num(fields[5]),
                    "close": _num(fields[6]),
                    "change_pct": _num(fields[8]),
                    "amount": _num(fields[10]),
                    "volume": _num(fields[11]),
                    "timestamp": f"{fields[17]} {fields[18] if len(fields) > 18 else ''}".strip(),
                })
            if not records:
                return ProviderResult.failure(self.name, f"No Sina HK quote for {symbols}")
            return ProviderResult(source=self.name, payload=records)
        except Exception as exc:
            logger.warning(f"{self.name}.get_quotes failed: {exc}")
            return ProviderResult.failure(self.name, str(exc))

    def get_historical(self, symbol: str, period: str = "6mo") -> ProviderResult:
        return ProviderResult.failure(self.name, "Sina HK daily history is not exposed by this adapter")

    def get_fundamentals(self, symbol: str) -> ProviderResult:
        quote = self.get_quotes([symbol])
        if not quote.ok:
            return quote
        row = quote.payload[0]
        return ProviderResult(
            source=self.name,
            payload={
                "symbol": row.get("symbol"),
                "market": self.market,
                "currency": self.currency,
                "company_name": row.get("name"),
                "current_price": row.get("close"),
                "pe_ratio": None,
                "pb_ratio": None,
                "market_cap": None,
            },
        )


# Backward-compatible alias used by older Streamlit code paths.
AkshareProvider = AshareAkshareProvider


def _period_to_days(period: str) -> int:
    mapping = {
        "1mo": 30,
        "3mo": 90,
        "6mo": 180,
        "1y": 365,
        "2y": 730,
        "5y": 1825,
        "max": 3650,
    }
    return mapping.get(period, 180)


def _first_existing(df: pd.DataFrame, names: list[str]) -> str | None:
    for name in names:
        if name in df.columns:
            return name
    return None


def _sina_ashare_symbol(symbol: str) -> str:
    symbol = symbol.zfill(6)
    return ("sh" if symbol.startswith(("5", "6", "9")) else "sz") + symbol


def _sina_headers() -> dict[str, str]:
    return {
        "Referer": "https://finance.sina.com.cn",
        "User-Agent": "Mozilla/5.0",
    }


def _ohlcv_records(
    df: pd.DataFrame | None,
    *,
    date_col: str,
    open_col: str,
    high_col: str,
    low_col: str,
    close_col: str,
    volume_col: str,
) -> list[dict[str, Any]]:
    if df is None or df.empty:
        return []
    records = []
    for _, row in df.iterrows():
        date_value = row.get(date_col)
        if hasattr(date_value, "strftime"):
            date_str = date_value.strftime("%Y-%m-%d")
        else:
            date_str = str(date_value)
        records.append({
            "date": date_str,
            "open": _num(row.get(open_col)),
            "high": _num(row.get(high_col)),
            "low": _num(row.get(low_col)),
            "close": _num(row.get(close_col)),
            "volume": _num(row.get(volume_col)),
        })
    return records


def _num(value: Any) -> float | None:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except TypeError:
        pass
    text = str(value).replace(",", "").strip()
    if text in {"", "-", "--", "None", "nan"}:
        return None
    units = {"万": 1e4, "亿": 1e8, "万亿": 1e12}
    for unit, multiplier in sorted(units.items(), key=lambda item: len(item[0]), reverse=True):
        if text.endswith(unit):
            return float(text.removesuffix(unit)) * multiplier
    try:
        return float(text)
    except (TypeError, ValueError):
        return None


def _clean(value: Any) -> Any:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except TypeError:
        pass
    return value
