"""Pipeline orchestrator for automated multi-symbol research workflows.

This package is the central coordination layer for the AI research system.
It provides:
- PipelineOrchestrator: executable LangGraph-backed research runner
- workflow_spec: formal specification (agents, phases, output standards)
- roles: agent role catalog (runtime node bindings)
- Future extensions: auto-screener, real-time monitor, daily briefing, trading signals
"""

from src.orchestrator.pipeline import PipelineOrchestrator, ResearchExecution
from src.orchestrator.roles import research_agent_catalog
from src.orchestrator.workflow_spec import (
    AGENT_ROLES,
    FUTURE_MODULES,
    MARKET_COVERAGE,
    OUTPUT_CONVENTIONS,
    OUTPUT_DIR_TEMPLATE,
    PHASE_ORDER,
    AgentRole,
    ExtensionSlot,
    Phase,
    get_agent_catalog,
    get_future_modules,
    workflow_manifest,
)

__all__ = [
    "PipelineOrchestrator",
    "ResearchExecution",
    "research_agent_catalog",
    # Workflow spec
    "AGENT_ROLES",
    "FUTURE_MODULES",
    "MARKET_COVERAGE",
    "OUTPUT_CONVENTIONS",
    "OUTPUT_DIR_TEMPLATE",
    "PHASE_ORDER",
    "AgentRole",
    "ExtensionSlot",
    "Phase",
    "get_agent_catalog",
    "get_future_modules",
    "workflow_manifest",
]
