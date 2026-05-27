"""Analysis Agent — Phase 1 core agent.

A ReAct agent that:
1. Fetches market data, fundamentals, and news for a single stock
2. Calculates financial ratios and interprets them
3. Assesses sentiment from news/research
4. Produces a structured research report

Usage:
    from src.agents.analysis.graph import create_analysis_agent
    agent = create_analysis_agent(llm)
    result = run_agent_sync(agent, "Analyze AAPL")
"""

from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.tools import BaseTool
from langgraph.graph.state import CompiledStateGraph

from src.core.base_agent import create_agent
from src.core.state import AgentState, StructuredOutput
from src.tools.analysis_tools import calculate_financial_ratios
from src.tools.market_data import (
    get_fundamentals,
    get_historical_prices,
    get_stock_quotes,
)
from src.tools.web_search import web_search

# Tools available to the Analysis Agent
ANALYSIS_TOOLS: list[BaseTool] = [
    get_stock_quotes,
    get_historical_prices,
    get_fundamentals,
    calculate_financial_ratios,
    web_search,
]

SYSTEM_PROMPT = """You are a senior financial analyst at a top-tier investment research firm.

Your task: Analyze a given stock and produce a professional research report.

## Analysis Steps
1. **Data Gathering**: Fetch current quotes, historical prices (6 months), fundamentals, and recent news
2. **Financial Analysis**: Use calculate_financial_ratios on the fundamental data to get PE, PB, ROE etc. with interpretations
3. **Price Analysis**: Review the 6-month price history — identify trends, support/resistance levels, volatility patterns
4. **News & Sentiment**: Search for recent developments, analyst actions, and market sentiment
5. **Synthesis**: Combine all findings into a structured report

## Rules
- Always verify with at least two sources where possible
- Use specific numbers — "PE of 25.3" not "moderate valuation"
- Acknowledge uncertainty — never fabricate data
- If a metric is unavailable, say so; don't guess
- For A-share stocks (6-digit codes like '600519'), the financial data source is AKShare
- For US stocks (letter tickers like 'AAPL'), use yfinance

## Report Format
End your analysis with a structured summary:

```json
{
  "ticker": "SYMBOL",
  "company_name": "Name",
  "rating": "BUY / HOLD / SELL",
  "current_price": 123.45,
  "key_metrics": {
    "pe_ratio": ..., "pb_ratio": ..., "roe": ..., "market_cap": ...
  },
  "bull_case": "1-2 sentence thesis",
  "bear_case": "1-2 sentence risk",
  "key_catalysts": ["catalyst 1", "catalyst 2"],
  "risk_factors": ["risk 1", "risk 2"],
  "price_target_6mo": 000.00,
  "confidence": "low / medium / high"
}
```
"""


def create_analysis_agent(
    llm: BaseChatModel,
    tools: list[BaseTool] | None = None,
) -> CompiledStateGraph:
    """Create the Analysis Agent as a LangGraph subgraph.

    Args:
        llm: The language model (use deep_thinking_llm)
        tools: Optional custom tools (defaults to standard financial tools)

    Returns:
        Compiled LangGraph graph ready for use as a node or standalone
    """
    return create_agent(
        name="FinancialAnalyst",
        llm=llm,
        system_prompt=SYSTEM_PROMPT,
        tools=tools or ANALYSIS_TOOLS,
        checkpoint=True,
    )


def extract_report(state: AgentState) -> StructuredOutput | None:
    """Extract structured output from agent messages.

    Looks for the JSON block in the final AI message and parses it.
    """
    messages = state.get("messages", [])
    if not messages:
        return None

    # Find the last AI message
    last_ai = None
    for m in reversed(messages):
        if hasattr(m, "type") and m.type == "ai":
            last_ai = m
            break

    if last_ai is None:
        return None

    content = last_ai.content if hasattr(last_ai, "content") else str(last_ai)

    # Try to extract JSON from content
    import json
    import re

    # Find JSON block
    json_match = re.search(r"```json\s*(.*?)\s*```", content, re.DOTALL)
    if json_match:
        try:
            data = json.loads(json_match.group(1))
        except json.JSONDecodeError:
            # Try finding any JSON-like structure
            brace_match = re.search(r"\{[^{}]*\}", content)
            if brace_match:
                try:
                    data = json.loads(brace_match.group(0))
                except json.JSONDecodeError:
                    data = {}
            else:
                data = {}
    else:
        # Try finding bare JSON object
        brace_match = re.search(r"\{[^{}]*\"ticker\"[^{}]*\}", content)
        if brace_match:
            try:
                data = json.loads(brace_match.group(0))
            except json.JSONDecodeError:
                data = {}
        else:
            data = {}

    return StructuredOutput(
        agent_name="FinancialAnalyst",
        content_type="analysis_report",
        summary=content[-500:],  # Last 500 chars as summary
        data=data,
        confidence=str(data.get("confidence", "low")) if isinstance(data, dict) else "low",
        metadata={"ticker": data.get("ticker", "") if isinstance(data, dict) else ""},
    )


def format_report_for_display(report: StructuredOutput) -> str:
    """Format an agent report as markdown for Streamlit display."""
    data = report.data or {}

    lines = [
        f"## {data.get('company_name', 'Company')} ({data.get('ticker', '')})",
        f"**Rating**: {data.get('rating', 'N/A')} | "
        f"**Current Price**: {data.get('current_price', 'N/A')} | "
        f"**Confidence**: {data.get('confidence', 'N/A')}",
        "",
        "### Key Metrics",
    ]

    metrics = data.get("key_metrics", {})
    if metrics:
        for k, v in metrics.items():
            key_name = k.replace("_", " ").title()
            lines.append(f"- **{key_name}**: {v}")

    lines.extend([
        "",
        "### Bull Case",
        data.get("bull_case", "N/A"),
        "",
        "### Bear Case",
        data.get("bear_case", "N/A"),
        "",
        "### Key Catalysts",
    ])

    catalysts = data.get("key_catalysts", [])
    if catalysts:
        for c in catalysts:
            lines.append(f"- {c}")
    else:
        lines.append("- N/A")

    lines.extend(["", "### Risk Factors"])

    risks = data.get("risk_factors", [])
    if risks:
        for r in risks:
            lines.append(f"- {r}")
    else:
        lines.append("- N/A")

    lines.extend([
        "",
        f"**6-Month Price Target**: {data.get('price_target_6mo', 'N/A')}",
        "",
        "---",
        "### Full Analysis Transcript",
        report.summary,
    ])

    return "\n".join(lines)
