"""Formal workflow specification for the AI multi-agent research system.

This module is the single source of truth for:
- Complete research pipeline (6 phases + publish)
- Agent role definitions and scheduling
- Output standards (directory structure, three-format, naming conventions)
- Extension points for future modules (Phase 4 roadmap)

Version: 2.0 (2026-06-01) — added PUBLISH stage + three-format enforcement + extension slots
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


# ═══════════════════════════════════════════════════════════════════
# Pipeline Stages
# ═══════════════════════════════════════════════════════════════════

class Phase(str, Enum):
    """Canonical research pipeline phases. Every analysis MUST pass through all 7."""
    KLINE = "kline"
    FUNDAMENTALS = "fundamentals"
    TECHNICAL = "technical"
    MACRO = "macro"
    REPORT = "report"
    AUDIT = "audit"
    PUBLISH = "publish"


PHASE_ORDER: tuple[Phase, ...] = (
    Phase.KLINE,
    Phase.FUNDAMENTALS,
    Phase.TECHNICAL,
    Phase.MACRO,
    Phase.REPORT,
    Phase.AUDIT,
    Phase.PUBLISH,
)

# Phases 1-4 can run in parallel (independent data sources)
PARALLEL_PHASES: tuple[Phase, ...] = (
    Phase.KLINE,
    Phase.FUNDAMENTALS,
    Phase.TECHNICAL,
    Phase.MACRO,
)


class AgentMode(str, Enum):
    DETERMINISTIC = "deterministic"  # Pure computation, no LLM
    HYBRID = "hybrid"                # LLM for text, local for metrics
    LLM_DRIVEN = "llm_driven"        # Full LLM orchestration


# ═══════════════════════════════════════════════════════════════════
# Agent Role Catalog
# ═══════════════════════════════════════════════════════════════════

@dataclass
class AgentRole:
    """Formal definition of a research agent role."""
    id: str
    name: str
    name_zh: str
    phase: Phase
    mode: AgentMode
    subagent_type: str              # Claude Code agent type name
    inputs: list[str]               # Required input types
    outputs: list[str]              # Expected output types
    output_dir: str                 # Subdirectory under symbol dir
    output_formats: tuple[str, ...] = (".md", ".html", ".pdf")
    description: str = ""


AGENT_ROLES: tuple[AgentRole, ...] = (
    AgentRole(
        id="kline-collector",
        name="K-Line Collector",
        name_zh="K线数据采集员",
        phase=Phase.KLINE,
        mode=AgentMode.DETERMINISTIC,
        subagent_type="kline-collector",
        inputs=[],
        outputs=["{symbol}_daily_{start}_{end}.csv", "{symbol}_weekly_{start}_{end}.csv"],
        output_dir="kline",
        output_formats=(".csv",),  # K-line is CSV only
        description="采集股票历史K线(OHLCV)数据，支持A股/港股/美股。日线+周线双周期。",
    ),
    AgentRole(
        id="fundamentals-researcher",
        name="Fundamentals Researcher",
        name_zh="基本面研究员",
        phase=Phase.FUNDAMENTALS,
        mode=AgentMode.HYBRID,
        subagent_type="fundamentals-researcher",
        inputs=["kline/daily/*.csv"],
        outputs=["{symbol}_fundamentals_{date}.md"],
        output_dir="fundamentals",
        description="深度基本面分析：财务报表、护城河评估、业务结构、成长性、盈利能力。定量+定性双轨。",
    ),
    AgentRole(
        id="technical-analyst",
        name="Technical Analyst",
        name_zh="技术分析员",
        phase=Phase.TECHNICAL,
        mode=AgentMode.DETERMINISTIC,
        subagent_type="technical-analyst",
        inputs=["kline/daily/*.csv"],
        outputs=["{symbol}_technical_{date}.md"],
        output_dir="technical",
        description="纯技术分析：量价关系、技术指标计算、图表形态识别、交易信号生成。不涉及基本面。",
    ),
    AgentRole(
        id="macro-researcher",
        name="Macro Researcher",
        name_zh="宏观研究员",
        phase=Phase.MACRO,
        mode=AgentMode.HYBRID,
        subagent_type="macro-researcher",
        inputs=[],
        outputs=["macro_briefing_{date}.md"],
        output_dir="macro",
        description="宏观经济、政策、资金面、市场情绪分析。覆盖GDP/CPI/PMI/央行政策/行业政策/北向资金。",
    ),
    AgentRole(
        id="report-writer",
        name="Report Writer",
        name_zh="研报撰写员",
        phase=Phase.REPORT,
        mode=AgentMode.HYBRID,
        subagent_type="report-writer",
        inputs=[
            "fundamentals/{symbol}_fundamentals_{date}.md",
            "technical/{symbol}_technical_{date}.md",
            "macro/macro_briefing_{date}.md",
            "kline/daily/*.csv",
        ],
        outputs=["{symbol}_investment_report_{date}.md"],
        output_dir="reports",
        description="综合所有前序产出，生成机构级投资研报。含投资摘要、估值分析、风险矩阵、操作建议。",
    ),
    AgentRole(
        id="research-auditor",
        name="Research Auditor",
        name_zh="研究审计员",
        phase=Phase.AUDIT,
        mode=AgentMode.DETERMINISTIC,
        subagent_type="research-auditor",
        inputs=[
            "reports/{symbol}_investment_report_{date}.md",
            "fundamentals/{symbol}_fundamentals_{date}.md",
            "technical/{symbol}_technical_{date}.md",
            "macro/macro_briefing_{date}.md",
            "kline/daily/*.csv",
        ],
        outputs=["{symbol}_audit_{date}.md"],
        output_dir="audit",
        description="最后防线：回溯全部数据源，交叉核验关键数字，批判性审查研报草稿，找出逻辑漏洞和数据矛盾。",
    ),
)


# ═══════════════════════════════════════════════════════════════════
# Output Standards
# ═══════════════════════════════════════════════════════════════════

OUTPUT_DIR_TEMPLATE = """{symbol}_{name}/
├── README.md                          ← 研究档案索引
├── kline/
│   ├── daily/{symbol}_daily_{start}_{end}.csv
│   └── weekly/{symbol}_weekly_{start}_{end}.csv
├── fundamentals/{symbol}_fundamentals_{date}.{{md,html,pdf}}
├── technical/{symbol}_technical_{date}.{{md,html,pdf}}
├── macro/macro_briefing_{date}.{{md,html,pdf}}
├── reports/{symbol}_investment_report_{date}.{{md,html,pdf}}
└── audit/{symbol}_audit_{date}.{{md,html,pdf}}"""

OUTPUT_CONVENTIONS = {
    "root": "E:/StockResearch/{symbol}_{name}/",
    "kline_daily": "kline/daily/{symbol}_daily_{start}_{end}.csv",
    "kline_weekly": "kline/weekly/{symbol}_weekly_{start}_{end}.csv",
    "fundamentals": "fundamentals/{symbol}_fundamentals_{date}.md",
    "technical": "technical/{symbol}_technical_{date}.md",
    "macro": "macro/macro_briefing_{date}.md",
    "report": "reports/{symbol}_investment_report_{date}.md",
    "audit": "audit/{symbol}_audit_{date}.md",
    "readme": "README.md",
}

HTML_CSS_TEMPLATE = "scripts/md2html.py"   # #8B0000 Moutai-standard CSS
PDF_CONVERTER = "scripts/md2pdf.py"         # Edge headless print-to-pdf
MD2HTML_SCRIPT = "scripts/md2html.py"
MD2PDF_SCRIPT = "scripts/md2pdf.py"


# ═══════════════════════════════════════════════════════════════════
# Future Extension Points (Phase 4 Roadmap)
# ═══════════════════════════════════════════════════════════════════

@dataclass
class ExtensionSlot:
    """Defines a future module slot that can be plugged into the pipeline."""
    id: str
    name: str
    name_zh: str
    trigger: str                    # When it runs (cron / event / pre-phase / post-phase)
    phase_hook: Phase | None        # Which phase it attaches to (None = standalone)
    inputs: list[str]
    outputs: list[str]
    status: str = "planned"         # planned | in_progress | live
    description: str = ""


FUTURE_MODULES: tuple[ExtensionSlot, ...] = (
    ExtensionSlot(
        id="auto-screener",
        name="Auto Screener",
        name_zh="自动推票引擎",
        trigger="cron: 0 8 * * 1-5",   # Weekdays 8am
        phase_hook=None,                 # Standalone — runs before Phase 1
        inputs=[],
        outputs=["watchlists/auto_screen_{date}.json"],
        status="planned",
        description="批量扫描全市场（A股/港股/美股），按多因子模型（PE/PB/ROE/动量/量比）自动筛选候选标的，推送到监控池。"
    ),
    ExtensionSlot(
        id="real-time-monitor",
        name="Real-Time Monitor",
        name_zh="实时行情捕捉",
        trigger="cron: */5 9-15 * * 1-5",  # Every 5 min during trading hours
        phase_hook=None,                    # Standalone — runs independently
        inputs=["portfolios/*.json"],
        outputs=["alerts/realtime_{datetime}.json"],
        status="planned",
        description="实时监控持仓和关注列表的异动（价格突破、放量、技术信号触发、新闻突发），通过Webhook/App推送告警。"
    ),
    ExtensionSlot(
        id="daily-briefing",
        name="Daily Briefing",
        name_zh="每日投研简报",
        trigger="cron: 0 8 * * 1-5",
        phase_hook=Phase.PUBLISH,            # Runs after publish
        inputs=["watchlists/*.json", "daily/scanner_results.json"],
        outputs=["daily/{date}_briefing.md"],
        status="planned",
        description="盘前简报：市场概览+热点扫描+持仓监控+快速分析聚焦，作为每日投研的起点。"
    ),
    ExtensionSlot(
        id="portfolio-tracker",
        name="Portfolio Tracker",
        name_zh="组合跟踪器",
        trigger="event: on_research_complete",
        phase_hook=Phase.PUBLISH,
        inputs=["reports/*_investment_report_*.md"],
        outputs=["portfolios/current.json", "portfolios/history/{date}.json"],
        status="planned",
        description="自动更新投资组合状态：持仓权重、盈亏、风险敞口、目标价偏离度。研究完成后自动同步。"
    ),
    ExtensionSlot(
        id="comparison-engine",
        name="Cross-Symbol Comparison Engine",
        name_zh="跨标的对比引擎",
        trigger="event: on_batch_complete",
        phase_hook=None,
        inputs=["reports/*_investment_report_*.md"],
        outputs=["docs/{sector}_comparison_{date}.md"],
        status="planned",
        description="同行业多标的横向对比：估值矩阵、成长性排名、技术面排序、综合评分。白酒行业已演示。"
    ),
    ExtensionSlot(
        id="trading-signals",
        name="Trading Signals Module",
        name_zh="交易信号模块",
        trigger="event: on_audit_pass",
        phase_hook=Phase.AUDIT,
        inputs=["reports/*_investment_report_*.md", "technical/*_technical_*.md"],
        outputs=["signals/trade_signals_{date}.json"],
        status="planned",
        description="基于研报评级+技术面信号+风险矩阵，生成结构化交易信号（入场/加仓/减仓/止损），供手动或自动执行。"
    ),
)


# ═══════════════════════════════════════════════════════════════════
# Market Coverage
# ═══════════════════════════════════════════════════════════════════

MARKET_COVERAGE = {
    "a_share": {
        "name": "A股（上证/深证）",
        "providers": ["akshare", "cn-financial MCP"],
        "data_types": ["kline", "fundamentals", "indicators", "news", "money_flow"],
        "status": "live",
    },
    "hk": {
        "name": "港股",
        "providers": ["akshare"],
        "data_types": ["kline", "fundamentals", "indicators"],
        "status": "live",
    },
    "us": {
        "name": "美股",
        "providers": ["akshare", "yfinance"],
        "data_types": ["kline", "fundamentals", "indicators"],
        "status": "live",
    },
    "crypto": {
        "name": "加密货币",
        "providers": ["aktools MCP (OKX)"],
        "data_types": ["kline", "loan_ratios", "taker_volume", "ai_report"],
        "status": "planned",
    },
}


# ═══════════════════════════════════════════════════════════════════
# Utility
# ═══════════════════════════════════════════════════════════════════

def get_agent_catalog() -> list[dict[str, Any]]:
    """JSON-safe agent role catalog for API/frontend consumption."""
    return [
        {
            "id": r.id,
            "name": r.name,
            "name_zh": r.name_zh,
            "phase": r.phase.value,
            "mode": r.mode.value,
            "subagent_type": r.subagent_type,
            "inputs": r.inputs,
            "outputs": r.outputs,
            "output_dir": r.output_dir,
            "output_formats": list(r.output_formats),
            "description": r.description,
        }
        for r in AGENT_ROLES
    ]


def get_future_modules() -> list[dict[str, Any]]:
    """JSON-safe future module catalog."""
    return [
        {
            "id": m.id,
            "name": m.name,
            "name_zh": m.name_zh,
            "trigger": m.trigger,
            "phase_hook": m.phase_hook.value if m.phase_hook else None,
            "inputs": m.inputs,
            "outputs": m.outputs,
            "status": m.status,
        }
        for m in FUTURE_MODULES
    ]


def workflow_manifest() -> dict[str, Any]:
    """Complete workflow manifest — agents, standards, extensions, coverage."""
    from datetime import datetime
    return {
        "version": "2.0",
        "generated_at": datetime.now().isoformat(),
        "phases": [p.value for p in PHASE_ORDER],
        "parallel_phases": [p.value for p in PARALLEL_PHASES],
        "agents": get_agent_catalog(),
        "output_conventions": OUTPUT_CONVENTIONS,
        "output_template": OUTPUT_DIR_TEMPLATE,
        "html_template": HTML_CSS_TEMPLATE,
        "pdf_converter": PDF_CONVERTER,
        "market_coverage": MARKET_COVERAGE,
        "future_modules": get_future_modules(),
    }
