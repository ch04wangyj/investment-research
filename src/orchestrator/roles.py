"""Application-facing catalog for the specialist research roles.

The local ``.claude/agents`` files remain useful authoring profiles. This
catalog maps their responsibilities onto the executable LangGraph runtime.
"""

from __future__ import annotations

from typing import Any


RESEARCH_AGENT_ROLES: tuple[dict[str, Any], ...] = (
    {
        "id": "kline-collector",
        "name": "K-Line Collector",
        "name_zh": "K线数据收集员",
        "runtime_nodes": ["DataCollector"],
        "stage": "data_collection",
        "mode": "deterministic",
        "responsibility": "Fetch quote, fundamentals, and OHLCV history with provider fallback metadata.",
    },
    {
        "id": "fundamentals-researcher",
        "name": "Fundamentals Researcher",
        "name_zh": "基本面研究员",
        "runtime_nodes": ["ResearchSourceCollector", "InformationSummarizer", "FundamentalAnalyst"],
        "stage": "deep_research",
        "mode": "hybrid",
        "responsibility": "Assess valuation, profitability, evidence coverage, and company-level data gaps.",
    },
    {
        "id": "macro-researcher",
        "name": "Macro Researcher",
        "name_zh": "宏观研究员",
        "runtime_nodes": ["ResearchSourceCollector", "MacroAnalyst", "NewsSentimentAnalyst"],
        "stage": "deep_research",
        "mode": "hybrid",
        "responsibility": "Collect macro, policy, cycle, and public-channel context before synthesis.",
    },
    {
        "id": "technical-analyst",
        "name": "Technical Analyst",
        "name_zh": "技术分析员",
        "runtime_nodes": ["TechnicalAnalyst", "RiskMonitor"],
        "stage": "deep_research",
        "mode": "deterministic",
        "responsibility": "Compute price-context indicators and deterministic drawdown risk alerts from OHLCV.",
    },
    {
        "id": "report-writer",
        "name": "Report Writer",
        "name_zh": "研报撰写员",
        "runtime_nodes": ["BullResearcher", "BearResearcher", "ResearchDirector"],
        "stage": "report_generation",
        "mode": "hybrid",
        "responsibility": "Synthesize opposing cases into a typed institutional-style research report.",
    },
    {
        "id": "research-auditor",
        "name": "Research Auditor",
        "name_zh": "研究审计员",
        "runtime_nodes": ["DeterministicPublicationGate"],
        "stage": "audit",
        "mode": "deterministic",
        "responsibility": "Block publication when required anchors, sources, or opposing-case checks fail.",
    },
)


def research_agent_catalog() -> list[dict[str, Any]]:
    """Return a JSON-safe copy of the registered specialist roles."""
    return [dict(item) for item in RESEARCH_AGENT_ROLES]
