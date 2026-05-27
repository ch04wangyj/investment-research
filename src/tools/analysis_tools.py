"""Financial analysis tools for agents.

Computational tools for ratio calculation, trend analysis, and
valuation assessment. These run locally on the data the agent has already fetched.
"""

import math
from typing import Any

from langchain_core.tools import tool
from loguru import logger


@tool
def calculate_financial_ratios(
    fundamentals: dict[str, Any],
    market_data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Calculate key financial ratios from fundamental and market data.

    Computes: PE, PB, ROE, ROA, profit margins, debt ratios, and
    provides an interpretation of each metric.

    Args:
        fundamentals: Dict from get_fundamentals() containing PE, PB, ROE, revenue, etc.
        market_data: Optional dict from get_stock_quotes() for current price context

    Returns a dict with calculated ratios and plain-English interpretation.
    """
    logger.info("Tool: calculate_financial_ratios")
    if not fundamentals:
        return {"error": "No fundamental data provided"}

    ratios = {}
    interpretations = {}

    # PE Ratio
    pe = fundamentals.get("pe_ratio")
    if pe is not None and not (isinstance(pe, float) and math.isnan(pe)):
        ratios["pe_ratio"] = pe
        if pe < 0:
            interpretations["pe_ratio"] = f"PE={pe:.1f}: Negative earnings (unprofitable)"
        elif pe < 15:
            interpretations["pe_ratio"] = f"PE={pe:.1f}: Low valuation relative to market"
        elif pe < 25:
            interpretations["pe_ratio"] = f"PE={pe:.1f}: Moderate valuation"
        elif pe < 40:
            interpretations["pe_ratio"] = f"PE={pe:.1f}: Above-average valuation"
        else:
            interpretations["pe_ratio"] = f"PE={pe:.1f}: High valuation / growth expectations"

    # PB Ratio
    pb = fundamentals.get("pb_ratio")
    if pb is not None and not (isinstance(pb, float) and math.isnan(pb)):
        ratios["pb_ratio"] = pb
        if pb < 1:
            interpretations["pb_ratio"] = f"PB={pb:.2f}: Trading below book value"
        elif pb < 3:
            interpretations["pb_ratio"] = f"PB={pb:.2f}: Reasonable asset valuation"
        else:
            interpretations["pb_ratio"] = f"PB={pb:.2f}: Premium to book value"

    # ROE
    roe = fundamentals.get("roe")
    if roe is not None and not (isinstance(roe, float) and math.isnan(roe)):
        ratios["roe"] = roe
        if roe < 0:
            interpretations["roe"] = f"ROE={roe*100:.1f}%: Negative return on equity"
        elif roe < 0.10:
            interpretations["roe"] = f"ROE={roe*100:.1f}%: Below-average profitability"
        elif roe < 0.20:
            interpretations["roe"] = f"ROE={roe*100:.1f}%: Good profitability"
        else:
            interpretations["roe"] = f"ROE={roe*100:.1f}%: Excellent profitability"

    # ROA
    roa = fundamentals.get("roa")
    if roa is not None and not (isinstance(roa, float) and math.isnan(roa)):
        ratios["roa"] = roa

    # Debt to Equity
    dte = fundamentals.get("debt_to_equity")
    if dte is not None and not (isinstance(dte, float) and math.isnan(dte)):
        ratios["debt_to_equity"] = dte
        if dte < 30:
            interpretations["debt_to_equity"] = f"D/E={dte:.1f}: Low leverage"
        elif dte < 100:
            interpretations["debt_to_equity"] = f"D/E={dte:.1f}: Moderate leverage"
        else:
            interpretations["debt_to_equity"] = f"D/E={dte:.1f}: High leverage — risk flag"

    # Dividend Yield
    div = fundamentals.get("dividend_yield")
    if div is not None and not (isinstance(div, float) and math.isnan(div)):
        ratios["dividend_yield"] = div
        if div > 0:
            interpretations["dividend_yield"] = f"Dividend yield: {div*100:.2f}%"

    # Market cap
    mcap = fundamentals.get("market_cap")
    if mcap is not None and not (isinstance(mcap, float) and math.isnan(mcap)):
        ratios["market_cap"] = mcap

    return {
        "ratios": ratios,
        "interpretations": interpretations,
        "data_quality": "high" if len(ratios) >= 4 else "limited",
    }
