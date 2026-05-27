"""Local technical indicators for research reports."""

from typing import Any

import numpy as np
import pandas as pd


def compute_technical_snapshot(history: list[dict[str, Any]]) -> dict[str, Any]:
    if not history:
        return {
            "summary": "No price history available.",
            "data_quality": "missing",
            "indicators": {},
        }

    df = pd.DataFrame(history).copy()
    if "close" not in df.columns or df["close"].dropna().empty:
        return {
            "summary": "Price history does not contain usable close prices.",
            "data_quality": "limited",
            "indicators": {},
        }

    for col in ["open", "high", "low", "close", "volume"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    close = df["close"].dropna()
    returns = close.pct_change().dropna()
    sma20 = close.rolling(20).mean().iloc[-1] if len(close) >= 20 else None
    sma60 = close.rolling(60).mean().iloc[-1] if len(close) >= 60 else None
    rsi14 = _rsi(close, 14)
    macd_line, macd_signal, macd_hist = _macd(close)
    latest = float(close.iloc[-1])
    first = float(close.iloc[0])
    momentum = (latest / first - 1) * 100 if first else None
    volatility = float(returns.tail(30).std() * np.sqrt(252) * 100) if len(returns) >= 2 else None

    trend = "neutral"
    if sma20 is not None and sma60 is not None:
        if latest > sma20 > sma60:
            trend = "uptrend"
        elif latest < sma20 < sma60:
            trend = "downtrend"
    elif momentum is not None:
        trend = "uptrend" if momentum > 5 else ("downtrend" if momentum < -5 else "neutral")

    summary = _summary(trend, momentum, rsi14, volatility)
    return {
        "summary": summary,
        "data_quality": "high" if len(close) >= 60 else "limited",
        "indicators": {
            "latest_close": _round(latest),
            "momentum_pct": _round(momentum),
            "sma_20": _round(sma20),
            "sma_60": _round(sma60),
            "rsi_14": _round(rsi14),
            "macd": _round(macd_line),
            "macd_signal": _round(macd_signal),
            "macd_histogram": _round(macd_hist),
            "annualized_volatility_pct": _round(volatility),
            "trend": trend,
        },
    }


def _rsi(close: pd.Series, window: int) -> float | None:
    if len(close) <= window:
        return None
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(window).mean()
    loss = (-delta.clip(upper=0)).rolling(window).mean()
    rs = gain / loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    value = rsi.iloc[-1]
    if pd.isna(value) and loss.iloc[-1] == 0 and gain.iloc[-1] > 0:
        return 100.0
    if pd.isna(value):
        return None
    return float(value)


def _macd(close: pd.Series) -> tuple[float | None, float | None, float | None]:
    if len(close) < 26:
        return None, None, None
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    macd_line = ema12 - ema26
    signal = macd_line.ewm(span=9, adjust=False).mean()
    hist = macd_line - signal
    return float(macd_line.iloc[-1]), float(signal.iloc[-1]), float(hist.iloc[-1])


def _summary(
    trend: str,
    momentum: float | None,
    rsi: float | None,
    volatility: float | None,
) -> str:
    parts = [f"Trend is {trend}"]
    if momentum is not None:
        parts.append(f"{momentum:.1f}% period momentum")
    if rsi is not None:
        zone = "overbought" if rsi >= 70 else ("oversold" if rsi <= 30 else "neutral")
        parts.append(f"RSI {rsi:.1f} ({zone})")
    if volatility is not None:
        parts.append(f"annualized volatility {volatility:.1f}%")
    return "; ".join(parts) + "."


def _round(value: Any) -> float | str | None:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
        return round(float(value), 4)
    except (TypeError, ValueError):
        return value
