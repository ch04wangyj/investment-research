"""FinAgent workflow comparison and local design blueprint."""

from __future__ import annotations

from datetime import datetime
from typing import Any


def workflow_blueprint() -> dict[str, Any]:
    """Return the current architecture comparison and planned workflow upgrades."""
    return {
        "generated_at": datetime.now().isoformat(),
        "positioning": (
            "本项目不再追求同花顺式资讯终端，而是围绕快速信息收集、证据校验、"
            "公司基本面和宏观约束生成机构研报。交易策略作为独立后续模块进入。"
        ),
        "comparisons": [
            {
                "framework": "TradingAgents",
                "observed_pattern": "分析师团队、牛熊研究员、交易员、风险团队和组合经理分工，强调辩论与风险审查。",
                "adopted_improvement": "保留多角色交叉审查，但将交易建议降级为后续模块；当前研报先通过证据簿、宏观、基本面和风险门控形成结论。",
                "risk_control": "避免单一路径从数据到结论直线传导；每个结论必须绑定来源、数据新鲜度和反方论点。",
            },
            {
                "framework": "FinRobot",
                "observed_pattern": "围绕财报、估值、图表和报告生成组织金融分析 agent，适合机构报告形态拆分。",
                "adopted_improvement": "新增信息收集员和研究总监角色，先汇总结构化/非结构化资料，再生成中金风格研报大纲。",
                "risk_control": "财务质量、估值和新闻情绪分开评分，缺失数据会降低置信度而不是自动补全。",
            },
            {
                "framework": "OpenBB",
                "observed_pattern": "用 provider 抽象连接多类金融数据源，统一输出给分析层和 agent 使用。",
                "adopted_improvement": "继续强化 provider registry/fallback，每条数据都暴露 source/as_of/stale/error 元数据。",
                "risk_control": "数据源失败时显式展示降级路径，防止 UI 看似完整但底层数据失真。",
            },
        ],
        "workflow": [
            {
                "stage": "Evidence Collector",
                "goal": "抓取公告/年报、公开机构研报线索、宏观政策、新闻与渠道观点。",
                "latency_strategy": "并行检索、缓存每日阅读、先返回可用摘要，慢源不阻塞研报主路径。",
            },
            {
                "stage": "Fundamental And Macro Analysts",
                "goal": "把商业模式、财务质量、估值锚、宏观周期约束拆开评分。",
                "latency_strategy": "结构化指标本地计算，LLM 只做文本归纳和冲突解释。",
            },
            {
                "stage": "Bull/Bear Review",
                "goal": "强制生成支持和反对论据，防止 agent 单方向叙事。",
                "latency_strategy": "低温度、短上下文的反方审查，减少深度模型调用次数。",
            },
            {
                "stage": "Research Director",
                "goal": "按机构研报形态输出评级、关键假设、催化剂、风险和非投资建议声明。",
                "latency_strategy": "先输出结构化报告，再按需生成 PDF 和长文本。",
            },
        ],
        "next_actions": [
            "每日优质研报抓取进入资料目录，作为开盘前阅读和个股研报的证据来源。",
            "报告历史支持删除，避免本地实验报告污染评级统计。",
            "后续技术策略模块与研报模块分离，防止交易信号压过基本面研究。",
            "引入异步 run 状态和局部刷新，减少长链 pipeline 对前端响应的阻塞。",
        ],
    }
