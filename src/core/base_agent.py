"""Agent factory — creates ReAct agents as LangGraph subgraphs.

This is the single most important file in the system.
Every agent (Analysis, Strategy, DataCollection sub-agents) is built
from create_agent(). The pattern is:
  LLM call (with tools) -> tool execution -> loop until done.

Borrowed from:
- TradingAgents: tool_call counter, multi-tier LLM
- Dexter: soft limits instead of hard failures
"""

from typing import Any, Callable

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.tools import BaseTool
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.prebuilt import ToolNode

from src.core.state import AgentState


def _get_max_tool_calls() -> int:
    from config.settings import get_settings
    return get_settings().max_tool_calls


def _create_agent_node(
    llm: BaseChatModel,
    tools: list[BaseTool],
    system_prompt: str,
) -> Callable:
    """Create the main agent reasoning node (LLM call with tool binding)."""
    llm_with_tools = llm.bind_tools(tools)

    def agent_node(state: AgentState) -> dict:
        # Inject system prompt if this is the first call
        messages = list(state.get("messages", []))
        if not messages or messages[0].type != "system":
            messages = [{"role": "system", "content": system_prompt}] + messages

        # Clean messages for DeepSeek V4 compatibility:
        # Strip reasoning_content from assistant messages so the API
        # doesn't require it to be echoed back on subsequent calls.
        cleaned = []
        for m in messages:
            if hasattr(m, "content") and isinstance(m, AIMessage):
                # Remove reasoning_content from additional_kwargs
                if hasattr(m, "additional_kwargs") and "reasoning_content" in m.additional_kwargs:
                    m = m.model_copy(update={"additional_kwargs": {
                        k: v for k, v in m.additional_kwargs.items()
                        if k != "reasoning_content"
                    }})
            cleaned.append(m)

        response = llm_with_tools.invoke(cleaned)

        # Track tool calls (TradingAgents pattern)
        count = state.get("tool_call_count", 0)

        max_calls = _get_max_tool_calls()
        # Soft limit warning (Dexter pattern)
        if count >= max_calls * 0.7 and hasattr(response, "tool_calls") and response.tool_calls:
            response.content += (
                f"\n\n[Note: You have made {count} tool calls. "
                f"Consider whether more are necessary.]"
            )

        return {
            "messages": [response],
            "tool_call_count": count,
        }

    return agent_node


def _should_continue(state: AgentState) -> str:
    """Router: continue to tools or finish? (TradingAgents pattern)"""
    messages = state.get("messages", [])
    last_msg = messages[-1] if messages else None

    count = state.get("tool_call_count", 0)

    # Hard limit reached — force end
    if count >= _get_max_tool_calls():
        return END

    # LLM requested tools -> execute
    if isinstance(last_msg, AIMessage) and last_msg.tool_calls:
        return "tools"

    # No more tool calls -> done
    return END


def _increment_tool_count(state: AgentState) -> dict:
    """Count each tool execution."""
    count = state.get("tool_call_count", 0)
    return {"tool_call_count": count + 1}


def create_agent(
    name: str,
    llm: BaseChatModel,
    system_prompt: str,
    tools: list[BaseTool],
    checkpoint: bool = True,
) -> CompiledStateGraph:
    """Create a ReAct agent as a LangGraph compiled subgraph.

    Args:
        name: Agent display name (for logging)
        llm: The language model (with tool binding)
        system_prompt: Agent role and instructions
        tools: Tools the agent can call
        checkpoint: Enable LangGraph checkpointing (default True)

    Returns:
        A compiled LangGraph graph usable as a node in parent graphs.

    The returned graph has:
      - Entry point: "agent" (LLM reasoning)
      - Conditional edge: agent -> tools | END
      - Edge: tools -> agent (loop back)
    """
    workflow = StateGraph(AgentState)

    # Nodes
    workflow.add_node("agent", _create_agent_node(llm, tools, system_prompt))
    workflow.add_node("tools", ToolNode(tools))

    # Tool node also increments the counter
    workflow.add_node("increment_count", _increment_tool_count)

    # Edges
    workflow.set_entry_point("agent")
    workflow.add_conditional_edges(
        "agent",
        _should_continue,
        {"tools": "increment_count", END: END},
    )
    workflow.add_edge("increment_count", "tools")
    workflow.add_edge("tools", "agent")  # Loop back to LLM

    # Compile
    checkpointer = MemorySaver() if checkpoint else None
    return workflow.compile(checkpointer=checkpointer, name=name)


# ── Agent runner (convenience wrapper) ──

async def run_agent(
    agent: CompiledStateGraph,
    user_input: str,
    metadata: dict[str, Any] | None = None,
    thread_id: str = "default",
) -> AgentState:
    """Run an agent with a single user input and return final state.

    Args:
        agent: Compiled agent graph from create_agent()
        user_input: The task description for the agent
        metadata: Optional run metadata (ticker, date, etc.)
        thread_id: LangGraph thread ID for checkpointing

    Returns:
        Final AgentState with messages and (optionally) structured_output
    """
    import asyncio
    from config.settings import get_settings

    initial_state: AgentState = {
        "messages": [{"role": "user", "content": user_input}],
        "tool_call_count": 0,
        "metadata": metadata or {},
        "artifacts": {},
    }

    config = {"configurable": {"thread_id": thread_id}}
    timeout = get_settings().agent_timeout_seconds
    final_state = await asyncio.wait_for(
        agent.ainvoke(initial_state, config),
        timeout=timeout,
    )
    return final_state


def run_agent_sync(
    agent: CompiledStateGraph,
    user_input: str,
    metadata: dict[str, Any] | None = None,
    thread_id: str = "default",
) -> AgentState:
    """Synchronous version of run_agent (for Streamlit / scripts)."""
    import concurrent.futures
    from config.settings import get_settings

    initial_state: AgentState = {
        "messages": [{"role": "user", "content": user_input}],
        "tool_call_count": 0,
        "metadata": metadata or {},
        "artifacts": {},
    }

    config = {"configurable": {"thread_id": thread_id}}
    timeout = get_settings().agent_timeout_seconds

    with concurrent.futures.ThreadPoolExecutor() as executor:
        future = executor.submit(agent.invoke, initial_state, config)
        try:
            final_state = future.result(timeout=timeout)
        except concurrent.futures.TimeoutError:
            raise TimeoutError(
                f"Agent '{thread_id}' timed out after {timeout}s"
            )
    return final_state
