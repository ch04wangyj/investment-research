"""Market indices fetcher — A-share, HK, and US indices.

Data sources:
  - A-share / HK: Sina Finance real-time API (fast, works in China)
  - US: AKShare index_us_stock_sina (daily close from Sina)

Each source is cached independently; failure in one market does not block others.
"""

from datetime import datetime
from typing import Any

from src.data.cache import get_cache

# ── Index definitions ──

A_SHARE_INDICES = [
    ("s_sh000001", "sh000001", "上证指数", "Shanghai Composite", "ashare"),
    ("s_sz399001", "sz399001", "深证成指", "SZSE Component", "ashare"),
    ("s_sh000300", "sh000300", "沪深300", "CSI 300", "ashare"),
    ("s_sh000905", "sh000905", "中证500", "CSI 500", "ashare"),
    ("s_sh000688", "sh000688", "科创50", "STAR 50", "ashare"),
]

HK_INDICES = [
    ("rt_hkHSI", "int_hsi", "恒生指数", "Hang Seng", "hk"),
    ("rt_hkHSCEI", "int_hscei", "国企指数", "HSCEI", "hk"),
    ("rt_hkHSTECH", "int_hstech", "恒生科技", "Hang Seng TECH", "hk"),
]

US_INDICES = [
    (".INX", "sp500", "标普500", "S&P 500", "us"),
    (".IXIC", "nasdaq", "纳斯达克", "NASDAQ", "us"),
    (".DJI", "dji", "道琼斯", "Dow Jones", "us"),
]


def _safe_float(val: Any) -> float | None:
    """Convert value to float, returning None on failure."""
    if val is None:
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


# ── A-Share Indices (Sina API) ──

def _fetch_ashare_indices() -> list[dict]:
    """Fetch A-share index spot data from Sina Finance.

    Response format: var hq_str_s_sh000001="name,price,change,change_pct,volume,amount"
    """
    import urllib.request

    sina_codes = [item[0] for item in A_SHARE_INDICES]
    url = f"https://hq.sinajs.cn/list={','.join(sina_codes)}"
    req = urllib.request.Request(
        url,
        headers={"Referer": "https://finance.sina.com.cn"},
    )
    resp = urllib.request.urlopen(req, timeout=10)
    raw = resp.read().decode("gbk")

    results = []
    for line in raw.strip().split("\n"):
        if not line.strip():
            continue
        # Parse: var hq_str_s_sh000001="name,price,change,change_pct,volume,amount"
        try:
            var_part, data_part = line.split("=", 1)
            sina_code = var_part.replace("var hq_str_", "").strip()
            fields = data_part.strip('";').split(",")
            if len(fields) < 4:
                continue
            name = fields[0]
            price = _safe_float(fields[1])
            change = _safe_float(fields[2])
            change_pct = _safe_float(fields[3])
        except (ValueError, IndexError):
            continue

        # Match sina code to our index definition
        match = None
        for sc, ik, zn, en, mkt in A_SHARE_INDICES:
            if sc == sina_code:
                match = (ik, zn, en, mkt)
                break
        if match is None:
            continue

        results.append({
            "code": match[0],
            "name": match[1],
            "name_en": match[2],
            "price": price,
            "change": change,
            "change_pct": change_pct,
            "market": match[3],
            "source": "sina",
            "timestamp": datetime.now().isoformat(),
        })
    return results


# ── HK Indices (Sina API) ──

def _fetch_hk_indices() -> list[dict]:
    """Fetch HK index spot data from Sina Finance.

    Response format:
    var hq_str_rt_hkHSI="code,name,price,prev_close,high,low,open,change,change_pct,...,date,time,..."
    """
    import urllib.request

    sina_codes = [item[0] for item in HK_INDICES]
    url = f"https://hq.sinajs.cn/list={','.join(sina_codes)}"
    req = urllib.request.Request(
        url,
        headers={"Referer": "https://finance.sina.com.cn"},
    )
    resp = urllib.request.urlopen(req, timeout=10)
    raw = resp.read().decode("gbk")

    results = []
    for line in raw.strip().split("\n"):
        if not line.strip():
            continue
        try:
            var_part, data_part = line.split("=", 1)
            sina_code = var_part.replace("var hq_str_", "").strip()
            fields = data_part.strip('";').split(",")
            if len(fields) < 9:
                continue
            # Fields: code, name, price, prev_close, high, low, open, change, change_pct, ...
            price = _safe_float(fields[2])
            change = _safe_float(fields[7])
            change_pct = _safe_float(fields[8])
        except (ValueError, IndexError):
            continue

        match = None
        for sc, ik, zn, en, mkt in HK_INDICES:
            if sc == sina_code:
                match = (ik, zn, en, mkt)
                break
        if match is None:
            continue

        results.append({
            "code": match[0],
            "name": match[1],
            "name_en": match[2],
            "price": price,
            "change": change,
            "change_pct": change_pct,
            "market": match[3],
            "source": "sina",
            "timestamp": datetime.now().isoformat(),
        })
    return results


# ── US Indices (AKShare → Sina daily) ──

def _fetch_us_indices() -> list[dict]:
    """Fetch US index daily close via AKShare's Sina adapter.

    Returns the most recent close (usually previous trading day).
    """
    import akshare as ak

    results = []
    for ak_symbol, ik, zn, en, mkt in US_INDICES:
        try:
            df = ak.index_us_stock_sina(symbol=ak_symbol)
            if df is None or df.empty:
                continue
            latest = df.iloc[-1]
            prev = df.iloc[-2] if len(df) >= 2 else latest
            close = _safe_float(latest["close"])
            prev_close = _safe_float(prev["close"])
            change = close - prev_close if close is not None and prev_close is not None else None
            change_pct = (
                (change / prev_close * 100) if change is not None and prev_close else None
            )

            results.append({
                "code": ik,
                "name": zn,
                "name_en": en,
                "price": close,
                "change": round(change, 2) if change is not None else None,
                "change_pct": round(change_pct, 2) if change_pct is not None else None,
                "market": mkt,
                "source": "akshare_sina",
                "data_date": str(latest.get("date", "")),
                "timestamp": datetime.now().isoformat(),
            })
        except Exception:
            continue
    return results


# ── Combined fetcher ──

def fetch_all_indices() -> list[dict]:
    """Fetch all market indices. Each market fails independently.

    Returns:
        List of index dicts with keys:
        code, name, name_en, price, change, change_pct, market, source, timestamp
    """
    cache_key = "market:indices:all"
    cache = get_cache()
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    results: list[dict] = []

    for fetcher, label in [
        (_fetch_ashare_indices, "A-share"),
        (_fetch_hk_indices, "HK"),
        (_fetch_us_indices, "US"),
    ]:
        try:
            results.extend(fetcher())
        except Exception:
            # Graceful degradation: skip failed market
            pass

    if results:
        cache.set(cache_key, results, ttl_seconds=300)
    else:
        stale = cache.get_stale(cache_key)
        if stale is not None:
            return stale

    return results
