"""Institutional-grade markdown publication contract for research archives."""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from src.research.schemas import AnalystView, PublicationAudit, ResearchReport


REPORT_REQUIRED_HEADINGS = (
    "## 一、投资摘要",
    "## 二、公司与基本面",
    "## 三、宏观、政策与行业环境",
    "## 四、价格背景与技术面",
    "## 五、估值与情景分析",
    "## 六、多空辩论",
    "## 七、催化剂、风险与监控",
    "## 八、证据索引与数据缺口",
    "## 九、审计结论",
)


def archive_directory_name(symbol: str, company_name: str) -> str:
    """Return a stable StockResearch-compatible directory name."""

    safe_name = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "_", company_name.strip())
    safe_name = re.sub(r"\s+", "_", safe_name).strip("._ ")
    if not safe_name or safe_name.upper() == symbol.upper():
        return symbol
    return f"{symbol}_{safe_name[:80]}"


def artifact_filename(report: ResearchReport, kind: str, suffix: str = ".md") -> str:
    date = report.generated_at.strftime("%Y%m%d")
    stems = {
        "fundamentals": f"{report.symbol}_fundamentals_{date}",
        "technical": f"{report.symbol}_technical_{date}",
        "macro": f"macro_briefing_{date}",
        "report": f"{report.symbol}_investment_report_{date}",
        "audit": f"{report.symbol}_audit_{date}",
    }
    if kind not in stems:
        raise ValueError(f"Unknown publication artifact kind: {kind}")
    return stems[kind] + suffix


def render_fundamentals_markdown(report: ResearchReport) -> str:
    metrics = report.key_metrics
    return "\n".join(
        [
            f"# {report.company_name}（{report.symbol}）基本面研究",
            "",
            *_metadata(report, "基本面研究员"),
            "",
            "## 一、执行摘要",
            report.financial_quality.summary,
            "",
            report.institutional_narrative.company_analysis,
            "",
            f"> 估值评分 **{report.valuation.score:.0f}/100**；财务质量评分 **{report.financial_quality.score:.0f}/100**。"
            "评分用于筛查和研究排序，不替代盈利预测、DCF 或可比公司估值。",
            "",
            "## 二、公司画像",
            "",
            "| 维度 | 当前信息 |",
            "|---|---|",
            f"| 市场 | {report.market} |",
            f"| 行业 | {_display(metrics.get('industry') or metrics.get('sector'))} |",
            f"| 当前价 | {_money(report.current_price)} |",
            f"| 市值 | {_compact(metrics.get('market_cap'))} |",
            f"| 外部公开资料 | {_display(metrics.get('external_sources'))} 条 |",
            "",
            "## 三、核心财务与估值仪表盘",
            "",
            "| 指标 | 数值 | 研究含义 |",
            "|---|---:|---|",
            *_metric_rows(metrics),
            "",
            "## 四、估值判断",
            "",
            report.valuation.summary,
            "",
            *_bullets(report.valuation.evidence, "暂无可展示估值指标。"),
            "",
            "## 五、财务质量判断",
            "",
            report.financial_quality.summary,
            "",
            *_bullets(report.financial_quality.evidence, "暂无可展示财务质量指标。"),
            "",
            "## 六、护城河研究清单",
            "",
            "| 维度 | 当前状态 | 后续核验重点 |",
            "|---|---|---|",
            "| 品牌与无形资产 | 待核验 | 品牌份额、定价权、客户粘性、监管资质 |",
            "| 成本与规模优势 | 待核验 | 单位经济性、产能利用率、供应链议价权 |",
            "| 转换成本与网络效应 | 待核验 | 留存、生态、开发者或渠道依赖 |",
            "| 资本配置 | 待核验 | 分红、回购、并购、资本开支与再投资回报 |",
            "",
            "## 七、公司层面资料线索",
            "",
            *_evidence_table(report, ("filings", "institutional_reports", "channel_analysis")),
            "",
            "## 八、数据缺口",
            "",
            *_bullets(report.information_summary.data_gaps, "当前未识别额外数据缺口。"),
            "",
            "## 免责声明",
            report.disclaimer,
        ]
    )


def render_technical_markdown(report: ResearchReport) -> str:
    indicators = _technical_indicators(report.technical)
    return "\n".join(
        [
            f"# {report.company_name}（{report.symbol}）价格背景与技术面研究",
            "",
            *_metadata(report, "技术分析员"),
            "",
            "## 一、趋势摘要",
            report.technical.summary,
            "",
            report.institutional_narrative.technical_analysis,
            "",
            f"> 技术面评分 **{report.technical.score:.0f}/100**。技术指标只用于刻画价格背景和风险位置，"
            "不能替代基本面判断，也不自动构成交易指令。",
            "",
            "## 二、指标仪表盘",
            "",
            "| 指标 | 数值 |",
            "|---|---:|",
            *[f"| {key} | {_display(value)} |" for key, value in indicators.items()],
            "",
            "## 三、量价与趋势解读",
            "",
            *_bullets(report.technical.evidence, "历史 K 线不足，暂无法形成完整技术面判断。"),
            "",
            "## 四、价格风险监控",
            "",
            *_risk_alert_table(report),
            "",
            "## 五、研究约束",
            "",
            "- 技术面结论必须与财务质量、估值、宏观和政策风险交叉阅读。",
            "- 若历史样本不足或行情源降级，应下调技术判断权重。",
            "- 策略模块启用前，本节不输出自动交易动作。",
            "",
            "## 免责声明",
            report.disclaimer,
        ]
    )


def render_macro_markdown(report: ResearchReport) -> str:
    return "\n".join(
        [
            f"# {report.company_name}（{report.symbol}）宏观、政策与情绪简报",
            "",
            *_metadata(report, "宏观研究员"),
            "",
            "## 一、宏观与周期判断",
            report.macro_context.summary,
            "",
            report.institutional_narrative.macro_analysis,
            "",
            f"> 宏观评分 **{report.macro_context.score:.0f}/100**。当前版本优先记录公开资料和政策线索；"
            "缺少一手宏观序列时，必须将结论视为方向性背景。",
            "",
            "## 二、宏观与政策证据目录",
            "",
            *_evidence_table(report, ("macro", "news")),
            "",
            "## 三、市场观点与情绪",
            report.sentiment.summary,
            "",
            *_bullets(report.sentiment.evidence, "暂未获取新的情绪或渠道观点。"),
            "",
            "## 四、催化剂日历与关注事项",
            "",
            *_bullets(report.catalysts, "关注下一次经营更新、财报和政策事件。"),
            "",
            "## 五、宏观风险",
            "",
            *_bullets(report.risks, "关注利率、流动性和政策波动。"),
            "",
            "## 免责声明",
            report.disclaimer,
        ]
    )


def render_report_markdown(report: ResearchReport) -> str:
    metrics = report.key_metrics
    upside = _upside(report.current_price, report.price_target_6m)
    return "\n".join(
        [
            f"# {report.company_name}（{report.symbol}）投资研究报告",
            "",
            *_metadata(report, "AI 多智能体研究部"),
            "",
            "---",
            "",
            "## 一、投资摘要",
            "",
            "### 1.1 核心观点",
            "",
            f"**评级：{_rating_zh(report.rating)} | 置信度：{_confidence_zh(report.confidence)} | "
            f"当前价：{_money(report.current_price)} | 研究锚：{_money(report.price_target_6m)} | "
            f"隐含空间：{_pct(upside)}**",
            "",
            report.thesis,
            "",
            report.institutional_narrative.executive_summary,
            "",
            "### 1.2 核心数据",
            "",
            "| 指标 | 数值 | 指标 | 数值 |",
            "|---|---:|---|---:|",
            f"| 综合评分 | {_display(metrics.get('composite_score'))} | 风险扣分 | {_display(metrics.get('risk_penalty'))} |",
            f"| PE | {_display(metrics.get('pe_ratio'))} | PB | {_display(metrics.get('pb_ratio'))} |",
            f"| ROE | {_pct(_ratio(metrics.get('roe')))} | 净利率 | {_pct(_ratio(metrics.get('profit_margins')))} |",
            f"| 营收 | {_compact(metrics.get('revenue'))} | 净利润 | {_compact(metrics.get('net_income'))} |",
            f"| 外部资料 | {_display(metrics.get('external_sources'))} | 一手资料 | {_display(metrics.get('primary_sources'))} |",
            "",
            "### 1.3 投资亮点",
            "",
            *_bullets(report.bull_case, "当前资料不足以形成高置信度看多结论。"),
            "",
            "### 1.4 核心风险",
            "",
            *_bullets(report.risks, "仍需持续监测宏观、政策和经营风险。"),
            "",
            "## 二、公司与基本面",
            "",
            "### 2.1 公司画像",
            "",
            "| 维度 | 当前信息 |",
            "|---|---|",
            f"| 市场 | {report.market} |",
            f"| 行业 | {_display(metrics.get('industry') or metrics.get('sector'))} |",
            f"| 市值 | {_compact(metrics.get('market_cap'))} |",
            f"| 财务质量 | {report.financial_quality.summary} |",
            "",
            "### 2.2 财务质量与估值",
            "",
            "| 模块 | 评分 | 数据质量 | 结论 |",
            "|---|---:|---|---|",
            *_view_rows(
                [
                    ("估值", report.valuation),
                    ("财务质量", report.financial_quality),
                    ("宏观周期", report.macro_context),
                    ("价格背景", report.technical),
                    ("新闻与观点", report.sentiment),
                ]
            ),
            "",
            "### 2.3 基本面证据",
            "",
            report.institutional_narrative.company_analysis,
            "",
            *_bullets(report.financial_quality.evidence, "暂无完整财务指标，需补充财报核验。"),
            "",
            "## 三、宏观、政策与行业环境",
            "",
            report.macro_context.summary,
            "",
            report.institutional_narrative.macro_analysis,
            "",
            *_bullets(report.macro_context.evidence, "宏观与政策资料偏薄，需补充一手指标。"),
            "",
            "## 四、价格背景与技术面",
            "",
            report.technical.summary,
            "",
            report.institutional_narrative.technical_analysis,
            "",
            "| 指标 | 数值 |",
            "|---|---:|",
            *[f"| {key} | {_display(value)} |" for key, value in _technical_indicators(report.technical).items()],
            "",
            "## 五、估值与情景分析",
            "",
            report.valuation.summary,
            "",
            report.institutional_narrative.valuation_analysis,
            "",
            "> 当前研究锚是基于结构化评分和风险扣分生成的情景锚，不是 DCF 结论。"
            "在补齐盈利预测、自由现金流、可比公司和资本成本前，不应把该数值解释为精确目标价。",
            "",
            "| 情景 | 价格参考 | 相对当前价 | 使用方式 |",
            "|---|---:|---:|---|",
            *_scenario_rows(report),
            "",
            "## 六、多空辩论",
            "",
            "### 6.1 Bull Researcher",
            "",
            *_bullets(report.bull_case, "看多逻辑尚未形成。"),
            "",
            "### 6.2 Bear Researcher",
            "",
            *_bullets(report.bear_case, "看空复核尚未形成。"),
            "",
            "## 七、催化剂、风险与监控",
            "",
            "### 7.1 催化剂",
            "",
            report.institutional_narrative.catalyst_analysis,
            "",
            *_bullets(report.catalysts, "关注财报、经营更新与政策窗口。"),
            "",
            "### 7.2 风险提醒队列",
            "",
            report.institutional_narrative.risk_analysis,
            "",
            *_risk_alert_table(report),
            "",
            "## 八、证据索引与数据缺口",
            "",
            "### 8.1 公开资料索引",
            "",
            *_evidence_table(report, ("filings", "institutional_reports", "macro", "channel_analysis", "news")),
            "",
            "### 8.2 数据缺口",
            "",
            report.institutional_narrative.evidence_notes,
            "",
            *_bullets(report.information_summary.data_gaps, "当前未识别额外数据缺口。"),
            "",
            "## 九、审计结论",
            "",
            *_audit_summary(report.publication_audit),
            "",
            "## 免责声明",
            report.disclaimer,
        ]
    )


def render_audit_markdown(report: ResearchReport, audit: PublicationAudit) -> str:
    return "\n".join(
        [
            f"# {report.company_name}（{report.symbol}）研究审计报告",
            "",
            *_metadata(report, "研究审计员"),
            "",
            "## 一、审计结论",
            "",
            f"**状态：{audit.status.upper()} | 自动审计评分：{audit.score:.0f}/100 | 审计器：{audit.reviewer}**",
            "",
            "## 二、流水线完整性",
            "",
            "| 阶段 | 要求 | 当前状态 |",
            "|---|---|---|",
            "| K 线采集 | 日线与周线 CSV | 出版时检查 |",
            "| 基本面研究 | MD + HTML + PDF | 出版时检查 |",
            "| 技术分析 | MD + HTML + PDF | 出版时检查 |",
            "| 宏观简报 | MD + HTML + PDF | 出版时检查 |",
            "| 综合研报 | MD + HTML + PDF | 出版时检查 |",
            "| 审计报告 | MD + HTML + PDF | 出版时检查 |",
            "",
            "## 三、自动审计发现",
            "",
            "| 严重度 | 类别 | 问题 | 处置建议 |",
            "|---|---|---|---|",
            *_audit_finding_rows(audit),
            "",
            "## 四、证据覆盖",
            "",
            "| 渠道 | 条目数 |",
            "|---|---:|",
            *_coverage_rows(report),
            "",
            "## 五、人工复核边界",
            "",
            "- 自动审计检查结构、来源覆盖、新鲜度、多空观点和归档完整性。",
            "- 搜索摘要、媒体摘要和机构研报线索不能替代公告、财报、论文或研报原文。",
            "- 对目标价、盈利预测、政策影响和重大经营判断，仍需人工逐条回溯证据。",
            "",
            "## 六、审计声明",
            audit.disclaimer,
        ]
    )


def render_archive_readme(report: ResearchReport) -> str:
    date = report.generated_at.strftime("%Y%m%d")
    return "\n".join(
        [
            f"# {report.company_name}（{report.symbol}）研究档案",
            "",
            f"- 最新运行：`{report.run_id}`",
            f"- 生成时间：{report.generated_at.isoformat()}",
            f"- 评级：{_rating_zh(report.rating)}",
            f"- 置信度：{_confidence_zh(report.confidence)}",
            "",
            "## 归档结构",
            "",
            f"- `kline/daily/`：{report.symbol} 日线 OHLCV",
            f"- `kline/weekly/`：{report.symbol} 周线 OHLCV",
            f"- `fundamentals/{artifact_filename(report, 'fundamentals')}`",
            f"- `technical/{artifact_filename(report, 'technical')}`",
            f"- `macro/{artifact_filename(report, 'macro')}`",
            f"- `reports/{artifact_filename(report, 'report')}`",
            f"- `audit/{artifact_filename(report, 'audit')}`",
            "",
            "## 三格式铁律",
            "",
            "除 K 线 CSV 外，每份 Agent 研究产物必须同时存在 `.md`、`.html`、`.pdf`。",
            "任何格式缺失，或自动审计未批准，均不得标记为正式出版。",
            "",
            "## 报告日期",
            "",
            date,
            "",
            "## 免责声明",
            report.disclaimer,
        ]
    )


def validate_report_contract(markdown: str) -> None:
    missing = [heading for heading in REPORT_REQUIRED_HEADINGS if heading not in markdown]
    if missing:
        raise RuntimeError("Institutional report contract is incomplete: " + ", ".join(missing))
    if markdown.count("|") < 30:
        raise RuntimeError("Institutional report contract requires structured research tables")


def _metadata(report: ResearchReport, author: str) -> list[str]:
    return [
        f"**报告日期：** {report.generated_at.strftime('%Y年%m月%d日')}",
        f"**研究角色：** {author}",
        f"**运行编号：** `{report.run_id}`",
        f"**报告性质：** 自动化研究草稿；仅在审计批准且三格式齐备后视为正式出版",
    ]


def _metric_rows(metrics: dict[str, Any]) -> list[str]:
    rows = [
        ("市盈率 PE", metrics.get("pe_ratio"), "估值筛查"),
        ("预期 PE", metrics.get("forward_pe"), "盈利预期筛查"),
        ("市净率 PB", metrics.get("pb_ratio"), "资产定价筛查"),
        ("ROE", _pct(_ratio(metrics.get("roe"))), "股东资本回报"),
        ("ROA", _pct(_ratio(metrics.get("roa"))), "资产效率"),
        ("净利率", _pct(_ratio(metrics.get("profit_margins"))), "盈利能力"),
        ("营收增长", _pct(_ratio(metrics.get("revenue_growth"))), "成长性"),
        ("利润增长", _pct(_ratio(metrics.get("earnings_growth"))), "成长质量"),
        ("营收", _compact(metrics.get("revenue")), "规模"),
        ("净利润", _compact(metrics.get("net_income")), "利润规模"),
    ]
    return [f"| {label} | {_display(value)} | {meaning} |" for label, value, meaning in rows]


def _technical_indicators(view: AnalystView) -> dict[str, str]:
    indicators: dict[str, str] = {}
    for evidence in view.evidence:
        if ": " not in evidence:
            continue
        key, value = evidence.split(": ", 1)
        indicators[key] = value
    return indicators or {"data_quality": view.data_quality}


def _view_rows(views: Iterable[tuple[str, AnalystView]]) -> list[str]:
    return [
        f"| {label} | {view.score:.0f}/100 | {view.data_quality} | {view.summary} |"
        for label, view in views
    ]


def _scenario_rows(report: ResearchReport) -> list[str]:
    current = report.current_price
    anchor = report.price_target_6m
    if current is None:
        return ["| 数据不足 | - | - | 等待行情源恢复 |"]
    base = anchor if anchor is not None else current
    scenarios = [
        ("保守", round(min(current * 0.88, base * 0.9), 2), "风险压力测试"),
        ("基准", round(base, 2), "结构化评分研究锚"),
        ("乐观", round(max(current * 1.12, base * 1.1), 2), "仅作为上行情景观察"),
    ]
    return [
        f"| {label} | {_money(price)} | {_pct(_upside(current, price))} | {meaning} |"
        for label, price, meaning in scenarios
    ]


def _risk_alert_table(report: ResearchReport) -> list[str]:
    if not report.risk_alerts:
        return ["| 当前无触发告警 | - | - | 仍需持续监控 |"]
    return [
        "| 级别 | 类型 | 事件 | 处置提示 |",
        "|---|---|---|---|",
        *[
            f"| {item.severity} | {item.category} | {item.title} | {item.action_hint or item.message} |"
            for item in report.risk_alerts[:12]
        ],
    ]


def _evidence_table(report: ResearchReport, channels: Iterable[str]) -> list[str]:
    evidence = report.research_evidence
    rows = []
    for channel in channels:
        for item in getattr(evidence, channel, [])[:10]:
            title = item.title.replace("|", "/")
            summary = item.summary.replace("|", "/")[:160]
            url = item.url or "-"
            rows.append(
                f"| {channel} | {item.quality} | {item.source or '-'} | [{title}]({url}) | {summary or '-'} |"
            )
    return [
        "| 渠道 | 质量 | 来源 | 标题与链接 | 摘要 |",
        "|---|---|---|---|---|",
        *(rows or ["| - | - | - | 暂无资料 | - |"]),
    ]


def _audit_summary(audit: PublicationAudit | None) -> list[str]:
    if not audit:
        return ["自动审计尚未运行。"]
    return [
        f"**状态：{audit.status.upper()} | 评分：{audit.score:.0f}/100**",
        "",
        *_bullets(
            [f"[{finding.severity}] {finding.title}：{finding.detail}" for finding in audit.findings],
            "自动审计未发现结构性阻断项。",
        ),
    ]


def _audit_finding_rows(audit: PublicationAudit) -> list[str]:
    if not audit.findings:
        return ["| info | publication | 未发现结构性阻断项 | 保持人工复核 |"]
    return [
        f"| {item.severity} | {item.category} | {item.title}：{item.detail} | {item.remediation} |"
        for item in audit.findings
    ]


def _coverage_rows(report: ResearchReport) -> list[str]:
    evidence = report.research_evidence
    return [
        f"| 公告/财报/监管披露 | {len(evidence.filings)} |",
        f"| 公开机构研报线索 | {len(evidence.institutional_reports)} |",
        f"| 宏观与政策 | {len(evidence.macro)} |",
        f"| 渠道观点 | {len(evidence.channel_analysis)} |",
        f"| 新闻 | {len(evidence.news)} |",
    ]


def _bullets(items: Iterable[Any], empty: str) -> list[str]:
    values = [str(item).strip() for item in items if str(item).strip()]
    return [f"- {item}" for item in values] or [f"- {empty}"]


def _rating_zh(value: str) -> str:
    return {"BUY": "增持", "HOLD": "中性", "SELL": "减持"}.get(value, value)


def _confidence_zh(value: str) -> str:
    return {"high": "高", "medium": "中", "low": "低"}.get(value, value)


def _ratio(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number / 100 if abs(number) > 10 else number


def _upside(current: float | None, target: float | None) -> float | None:
    if current in (None, 0) or target is None:
        return None
    return target / current - 1


def _pct(value: Any) -> str:
    try:
        return f"{float(value) * 100:.1f}%"
    except (TypeError, ValueError):
        return "-"


def _money(value: Any) -> str:
    try:
        return f"{float(value):,.2f}"
    except (TypeError, ValueError):
        return "-"


def _compact(value: Any) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "-"
    for divisor, suffix in [
        (1_000_000_000_000, "T"),
        (1_000_000_000, "B"),
        (1_000_000, "M"),
    ]:
        if abs(number) >= divisor:
            return f"{number / divisor:.2f}{suffix}"
    return f"{number:,.2f}"


def _display(value: Any) -> str:
    if value in (None, "", "None"):
        return "-"
    return str(value)
