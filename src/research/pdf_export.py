"""PDF export for institutional-style research reports."""

from __future__ import annotations

from io import BytesIO
from typing import Any
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.platypus import (
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


def render_research_pdf(report: dict[str, Any], lang: str = "zh") -> bytes:
    """Render a research report PDF aligned to a concise sell-side format."""
    buffer = BytesIO()
    font_name = _font_name(lang)
    styles = _styles(font_name)
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=16 * mm,
        leftMargin=16 * mm,
        topMargin=14 * mm,
        bottomMargin=14 * mm,
        title=f"{report.get('symbol', '')} Research Report",
    )
    story = []
    story.extend(_cover(report, styles, lang))
    story.extend(_investment_summary(report, styles, lang))
    story.extend(_analysis_sections(report, styles, lang))
    story.extend(_evidence_sections(report, styles, lang))
    story.extend(_risk_sections(report, styles, lang))
    story.append(Paragraph(_txt(lang, "免责声明", "Disclaimer"), styles["h2"]))
    story.append(Paragraph(_safe(report.get("disclaimer", "")), styles["body"]))
    doc.build(story, onFirstPage=_footer, onLaterPages=_footer)
    return buffer.getvalue()


def _font_name(lang: str) -> str:
    if lang == "zh":
        try:
            pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
            return "STSong-Light"
        except Exception:
            return "Helvetica"
    return "Helvetica"


def _styles(font_name: str) -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "ReportTitle",
            parent=base["Title"],
            fontName=font_name,
            fontSize=20,
            leading=26,
            alignment=TA_CENTER,
            textColor=colors.HexColor("#111827"),
            spaceAfter=10,
        ),
        "subtitle": ParagraphStyle(
            "Subtitle",
            parent=base["Normal"],
            fontName=font_name,
            fontSize=9,
            leading=13,
            alignment=TA_CENTER,
            textColor=colors.HexColor("#6b7280"),
            spaceAfter=12,
        ),
        "h2": ParagraphStyle(
            "SectionHeading",
            parent=base["Heading2"],
            fontName=font_name,
            fontSize=13,
            leading=18,
            textColor=colors.HexColor("#111827"),
            spaceBefore=10,
            spaceAfter=6,
        ),
        "body": ParagraphStyle(
            "Body",
            parent=base["BodyText"],
            fontName=font_name,
            fontSize=9,
            leading=14,
            textColor=colors.HexColor("#374151"),
            spaceAfter=5,
        ),
        "small": ParagraphStyle(
            "Small",
            parent=base["BodyText"],
            fontName=font_name,
            fontSize=7.5,
            leading=11,
            textColor=colors.HexColor("#6b7280"),
        ),
    }


def _cover(report: dict[str, Any], styles: dict[str, ParagraphStyle], lang: str) -> list[Any]:
    title = f"{report.get('company_name') or report.get('symbol')} ({report.get('symbol')})"
    subtitle = _txt(lang, "AI 投资研究报告 - 对齐卖方研报结构", "AI Investment Research Report")
    generated = report.get("generated_at", "")
    rows = [
        [_txt(lang, "评级", "Rating"), report.get("rating", "-")],
        [_txt(lang, "置信度", "Confidence"), report.get("confidence", "-")],
        [_txt(lang, "当前价格", "Current price"), _fmt(report.get("current_price"))],
        [_txt(lang, "6个月目标价", "6M target"), _fmt(report.get("price_target_6m"))],
        [_txt(lang, "出版质量门", "Publication gate"), (report.get("publication_audit", {}) or {}).get("status", "pending")],
    ]
    return [
        Paragraph(_safe(title), styles["title"]),
        Paragraph(_safe(f"{subtitle} | {generated}"), styles["subtitle"]),
        _table(rows, styles),
        Spacer(1, 6),
    ]


def _investment_summary(report: dict[str, Any], styles: dict[str, ParagraphStyle], lang: str) -> list[Any]:
    metrics = report.get("key_metrics", {}) or {}
    rows = [
        ["Composite", _fmt(metrics.get("composite_score")), "Risk penalty", _fmt(metrics.get("risk_penalty"))],
        ["PE", _fmt(metrics.get("pe_ratio")), "PB", _fmt(metrics.get("pb_ratio"))],
        ["ROE", _pct(metrics.get("roe")), "Market cap", _fmt(metrics.get("market_cap"))],
        ["External sources", _fmt(metrics.get("external_sources")), "Primary sources", _fmt(metrics.get("primary_sources"))],
    ]
    story = [
        Paragraph(_txt(lang, "投资摘要", "Investment Summary"), styles["h2"]),
        Paragraph(_safe(report.get("thesis", "")), styles["body"]),
        _table(rows, styles),
    ]
    return story


def _analysis_sections(report: dict[str, Any], styles: dict[str, ParagraphStyle], lang: str) -> list[Any]:
    sections = [
        (_txt(lang, "宏观与周期", "Macro Context"), report.get("macro_context", {})),
        (_txt(lang, "估值分析", "Valuation"), report.get("valuation", {})),
        (_txt(lang, "财务质量", "Financial Quality"), report.get("financial_quality", {})),
        (_txt(lang, "市场共识", "Market Consensus"), report.get("sentiment", {})),
    ]
    story = []
    for title, section in sections:
        story.append(Paragraph(title, styles["h2"]))
        story.append(Paragraph(_safe(section.get("summary", "")), styles["body"]))
        evidence = section.get("evidence", []) or []
        if evidence:
            story.extend(_bullets(evidence[:6], styles))
        else:
            story.append(Paragraph(_txt(lang, "暂无可展示证据，见数据缺口。", "No displayable evidence; see data gaps."), styles["small"]))
    return story


def _evidence_sections(report: dict[str, Any], styles: dict[str, ParagraphStyle], lang: str) -> list[Any]:
    evidence = report.get("research_evidence", {}) or {}
    story = [PageBreak(), Paragraph(_txt(lang, "资料目录", "Evidence Book"), styles["h2"])]
    for title, key in [
        (_txt(lang, "公告/年报/监管披露", "Filings and Disclosures"), "filings"),
        (_txt(lang, "公开机构研报线索", "Public Institutional Report Leads"), "institutional_reports"),
        (_txt(lang, "宏观政策与渠道观点", "Macro and Channel Views"), "macro"),
        (_txt(lang, "新闻", "News"), "news"),
    ]:
        rows = []
        for item in (evidence.get(key, []) or [])[:8]:
            rows.append([
                Paragraph(_safe(item.get("title", "")), styles["small"]),
                Paragraph(_safe(item.get("source", "")), styles["small"]),
                Paragraph(_safe(item.get("quality", "")), styles["small"]),
            ])
        story.append(Paragraph(title, styles["h2"]))
        story.append(_table(rows or [["-", "-", "-"]], styles, header=None))
    return story


def _risk_sections(report: dict[str, Any], styles: dict[str, ParagraphStyle], lang: str) -> list[Any]:
    audit = report.get("publication_audit", {}) or {}
    findings = audit.get("findings", []) or []
    story = [
        Paragraph(_txt(lang, "催化剂", "Catalysts"), styles["h2"]),
        *_bullets(report.get("catalysts", [])[:8], styles),
        Paragraph(_txt(lang, "主要风险", "Key Risks"), styles["h2"]),
        *_bullets(report.get("risks", [])[:10], styles),
        Paragraph(_txt(lang, "出版质量门", "Publication Gate"), styles["h2"]),
        Paragraph(
            _safe(
                _txt(lang, "自动审计状态", "Automated audit status")
                + f": {audit.get('status', 'pending')} | "
                + _txt(lang, "评分", "Score")
                + f": {audit.get('score', '-')}"
            ),
            styles["body"],
        ),
        *_bullets(
            [
                f"[{item.get('severity', 'info')}] {item.get('title', '')}: {item.get('detail', '')}"
                for item in findings[:8]
            ],
            styles,
        ),
    ]
    return story


def _bullets(items: list[Any], styles: dict[str, ParagraphStyle]) -> list[Any]:
    return [Paragraph("- " + _safe(str(item)), styles["body"]) for item in items if str(item).strip()]


def _table(rows: list[list[Any]], styles: dict[str, ParagraphStyle], header: list[str] | None = None) -> Table:
    data = ([header] if header else []) + rows
    table = Table(data, hAlign="LEFT", colWidths=None)
    table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), styles["body"].fontName),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("LEADING", (0, 0), (-1, -1), 11),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#d1d5db")),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f3f4f6")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    return table


def _footer(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica", 7)
    canvas.setFillColor(colors.HexColor("#9ca3af"))
    canvas.drawRightString(196 * mm, 8 * mm, f"Page {doc.page}")
    canvas.restoreState()


def _txt(lang: str, zh: str, en: str) -> str:
    return zh if lang == "zh" else en


def _safe(value: Any) -> str:
    return escape(str(value or ""))


def _fmt(value: Any) -> str:
    if value is None or value == "":
        return "-"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    if abs(number) >= 1_000_000_000_000:
        return f"{number / 1_000_000_000_000:.2f}T"
    if abs(number) >= 1_000_000_000:
        return f"{number / 1_000_000_000:.2f}B"
    if abs(number) >= 1_000_000:
        return f"{number / 1_000_000:.2f}M"
    return f"{number:.2f}"


def _pct(value: Any) -> str:
    number = _fmt_number(value)
    if number is None:
        return "-"
    pct = number * 100 if abs(number) <= 10 else number
    return f"{pct:.1f}%"


def _fmt_number(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
