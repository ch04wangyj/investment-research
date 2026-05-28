"""Supervisor Router — coordinates specialist agents with dynamic routing.

Architecture:
  User Request
      |
      v
  Supervisor Router (LLM analyzes intent)
      |
      +--> DataCollector ──+
      +--> ResearchPipeline─+--> Supervisor Router (re-route)
      +--> AnalysisAgent ───+         |
                                       v
                                      END

The supervisor is called twice:
  1. At entry, to choose the first specialist
  2. After each specialist finishes, to decide the next step
This provides loop-back: if data is insufficient, re-collect; if analysis
is done, move to strategy.
"""

from typing import Any

from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph
from loguru import logger

from src.core.state import WorkflowState


SUPERVISOR_SYSTEM_PROMPT = """You are a Supervisor agent coordinating a team of specialist investment research agents.

## Available Specialists
1. **DataCollector** — Fetches market data (quotes, fundamentals, history) for symbols. Use this FIRST for any ticker-related request.
2. **ResearchPipeline** — Runs the full institutional research pipeline: analysis, bull/bear debate, strategy. Produces a structured ResearchReport. Use this for single-stock deep analysis.
3. **AnalysisAgent** — A ReAct agent with tool access for open-ended analysis. Use this for complex questions requiring multiple tool calls.

## Your Job
Given the user's request and current workflow stage, decide the next step.

## Routing Rules
- If no data has been collected yet and tickers are present → DataCollector
- If data is collected but not analyzed → ResearchPipeline (single ticker) or AnalysisAgent (complex/multi)
- If analysis is complete → END
- If tickers list is empty → set END
- For "compare X and Y" or multi-ticker requests → DataCollector, then ResearchPipeline
- For "analyze X" → DataCollector, then ResearchPipeline
- For general market questions → AnalysisAgent

## Current State
Stage: {stage}
Tickers: {tickers}
Errors: {errors}
Has results: {has_results}

## Response Format
Return a JSON object:
{{
  "next_stage": "data_collection | analysis | strategy | done",
  "next_agent": "DataCollector | ResearchPipeline | AnalysisAgent | done",
  "reasoning": "Brief explanation of routing decision"
}}
"""


def _supervisor_router_node(state: WorkflowState) -> dict[str, Any]:
    """LLM-driven supervisor routing node.

    Analyzes the current workflow state and decides the next specialist to invoke.
    Falls back to rule-based routing if LLM is unavailable.
    """
    import json
    import re

    stage = state.get("stage", "init")
    tickers = state.get("tickers", [])
    errors = state.get("errors", [])
    has_results = bool(state.get("agent_results", {}))

    # Try LLM routing
    try:
        from src.core.llm import create_chat_model

        llm = create_chat_model(None, tier="quick", temperature=0.1)
        prompt = SUPERVISOR_SYSTEM_PROMPT.format(
            stage=stage,
            tickers=tickers or "none",
            errors=errors[:3] or "none",
            has_results=has_results,
        )
        response = llm.invoke([
            {"role": "system", "content": prompt},
            {"role": "user", "content": state.get("task", "No task specified")},
        ])
        content = str(response.content)

        # Extract JSON from response
        json_match = re.search(r"\{[^{}]*\}", content)
        if json_match:
            try:
                decision = json.loads(json_match.group(0))
                return {
                    "stage": decision.get("next_stage", "done"),
                    "next_agent": decision.get("next_agent", "done"),
                }
            except json.JSONDecodeError:
                pass
    except Exception as exc:
        logger.debug(f"Supervisor LLM routing failed: {exc}")

    # Rule-based fallback
    return _rule_based_route(state)


def _rule_based_route(state: WorkflowState) -> dict[str, Any]:
    """Deterministic fallback routing when LLM is unavailable."""
    stage = state.get("stage", "init")
    tickers = state.get("tickers", [])
    has_results = bool(state.get("agent_results", {}))

    if not tickers:
        return {"stage": "done", "next_agent": "done"}

    if stage == "init":
        return {"stage": "data_collection", "next_agent": "DataCollector"}

    if stage == "data_collection":
        if has_results:
            return {"stage": "analysis", "next_agent": "ResearchPipeline"}
        return {"stage": "data_collection", "next_agent": "DataCollector"}

    if stage == "analysis":
        return {"stage": "done", "next_agent": "done"}

    return {"stage": "done", "next_agent": "done"}


def _route_from_supervisor(state: WorkflowState) -> str:
    """Conditional edge: route to the chosen specialist or end."""
    next_agent = state.get("next_agent", "done")
    if next_agent == "done" or next_agent == END:
        return END
    valid = {"DataCollector", "ResearchPipeline", "AnalysisAgent"}
    if next_agent in valid:
        return next_agent
    return END


# ── Specialist wrapper nodes ──


def _data_collector_node(state: WorkflowState) -> dict[str, Any]:
    """Wrap the research pipeline's data_collector for the supervisor."""
    from src.agents.research.graph import data_collector
    from src.data.dal import detect_market, normalize_symbol

    tickers = state.get("tickers", [])
    results = {}
    errors = list(state.get("errors", []))

    for symbol in tickers:
        try:
            market = detect_market(symbol)
            normalized = normalize_symbol(symbol, market)
            # Build a minimal ResearchState for data_collector
            mini_state = {
                "symbol": normalized,
                "market": market,
                "period": "6mo",
                "errors": errors,
            }
            result = data_collector(mini_state)
            results[symbol] = {
                "quote": result.get("quote", {}),
                "fundamentals": result.get("fundamentals", {}),
                "history": result.get("history", []),
                "sources": result.get("sources", []),
            }
            errors = result.get("errors", errors)
        except Exception as exc:
            errors.append(f"DataCollector/{symbol}: {exc}")

    return {
        "agent_results": {**state.get("agent_results", {}), "data_collection": results},
        "stage": "data_collection",
        "errors": errors,
        "next_agent": "supervisor",
    }


def _research_pipeline_node(state: WorkflowState) -> dict[str, Any]:
    """Run the full institutional research pipeline for each ticker."""
    from src.agents.research.graph import run_research_pipeline

    tickers = state.get("tickers", [])
    results = {}
    errors = list(state.get("errors", []))

    for symbol in tickers:
        try:
            report = run_research_pipeline(symbol)
            results[symbol] = report.model_dump(mode="json")
        except Exception as exc:
            errors.append(f"ResearchPipeline/{symbol}: {exc}")

    return {
        "agent_results": {**state.get("agent_results", {}), "research_pipeline": results},
        "stage": "analysis",
        "errors": errors,
        "next_agent": "supervisor",
    }


def _analysis_agent_node(state: WorkflowState) -> dict[str, Any]:
    """Run the ReAct Analysis Agent for open-ended research."""
    from src.agents.analysis.graph import create_analysis_agent, extract_report
    from src.core.base_agent import run_agent_sync
    from src.core.llm import create_chat_model

    errors = list(state.get("errors", []))
    try:
        llm = create_chat_model(None, tier="deep", temperature=0.2)
        agent = create_analysis_agent(llm)
        task = state.get("task", "Analyze the given tickers")
        tickers = state.get("tickers", [])
        user_input = f"{task}\n\nTickers: {', '.join(tickers)}" if tickers else task

        result = run_agent_sync(agent, user_input)
        report = extract_report(result)
        data = report.model_dump(mode="json") if report else {}
    except Exception as exc:
        data = {}
        errors.append(f"AnalysisAgent: {exc}")

    return {
        "agent_results": {**state.get("agent_results", {}), "analysis_agent": data},
        "stage": "analysis",
        "errors": errors,
        "next_agent": "supervisor",
    }


# ── Graph builder ──


def build_supervisor_graph() -> CompiledStateGraph:
    """Build the supervisor graph with dynamic routing.

    Graph structure:
        Supervisor -> [route] -> DataCollector ─┐
                       |-> ResearchPipeline ────┤-> Supervisor -> END
                       |-> AnalysisAgent ───────┘
    """
    workflow = StateGraph(WorkflowState)

    workflow.add_node("Supervisor", _supervisor_router_node)
    workflow.add_node("DataCollector", _data_collector_node)
    workflow.add_node("ResearchPipeline", _research_pipeline_node)
    workflow.add_node("AnalysisAgent", _analysis_agent_node)

    workflow.set_entry_point("Supervisor")

    workflow.add_conditional_edges(
        "Supervisor",
        _route_from_supervisor,
        {
            "DataCollector": "DataCollector",
            "ResearchPipeline": "ResearchPipeline",
            "AnalysisAgent": "AnalysisAgent",
            END: END,
        },
    )

    # All specialists return to Supervisor for re-routing
    workflow.add_edge("DataCollector", "Supervisor")
    workflow.add_edge("ResearchPipeline", "Supervisor")
    workflow.add_edge("AnalysisAgent", "Supervisor")

    return workflow.compile(name="SupervisorRouter")


def run_supervisor(
    task: str,
    tickers: list[str],
    *,
    provider_id: str | None = None,
) -> WorkflowState:
    """Run the supervisor graph for a given task.

    Args:
        task: Natural language task description
        tickers: List of stock symbols to analyze
        provider_id: Optional LLM provider override

    Returns:
        Final WorkflowState with agent_results from all invoked specialists
    """
    import uuid

    graph = build_supervisor_graph()
    initial_state: WorkflowState = {
        "task": task,
        "tickers": tickers,
        "agent_results": {},
        "stage": "init",
        "errors": [],
        "run_id": str(uuid.uuid4()),
    }
    result = graph.invoke(initial_state)
    return result
