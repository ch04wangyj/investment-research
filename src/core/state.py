"""Shared state definitions for all agents.

Every agent uses AgentState as its internal state TypedDict.
StructuredOutput is the typed envelope for inter-agent communication.
"""

from datetime import datetime
from typing import Any, Literal

from langgraph.graph import MessagesState
from pydantic import BaseModel, Field
from typing_extensions import NotRequired, TypedDict


# ── Structured Output (inter-agent communication) ──

class StructuredOutput(BaseModel):
    """Typed envelope passed between agents. Prevents info degradation."""
    agent_name: str
    timestamp: datetime = Field(default_factory=datetime.now)
    content_type: Literal[
        "market_data", "analysis_report", "trade_signal", "news_summary"
    ] = "analysis_report"
    summary: str = ""           # NL summary for LLM consumption
    data: dict[str, Any] = {}   # Structured data for deterministic use
    confidence: str = "low"
    metadata: dict[str, Any] = {}


# ── Agent State ──

class AgentState(MessagesState):
    """Base state for every agent (extends LangGraph MessagesState).

    All agents share this structure. Subgraphs extend it as needed.
    """
    # Structured output produced by this agent
    structured_output: NotRequired[dict[str, Any]]

    # Sidecar artifacts (chart data, file paths, URLs)
    artifacts: NotRequired[dict[str, Any]]

    # Run metadata
    metadata: NotRequired[dict[str, Any]]

    # Tool call tracking (TradingAgents pattern: prevent infinite loops)
    tool_call_count: NotRequired[int]

    # Next agent for handoff (supervisor pattern)
    next_agent: NotRequired[str]


# ── Workflow-level state (supervisor graph) ──

class WorkflowState(TypedDict):
    """Top-level state shared across the entire workflow run."""
    # Task description
    task: str
    # Which ticker(s) to analyze
    tickers: list[str]
    # Results from each agent (keyed by agent name)
    agent_results: dict[str, StructuredOutput]
    # Current stage in the pipeline
    stage: Literal["init", "data_collection", "analysis", "strategy", "done"]
    # Error tracking
    errors: list[str]
    # Run ID for traceability
    run_id: str
