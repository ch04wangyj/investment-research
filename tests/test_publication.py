from datetime import datetime

from src.research.publication import (
    archive_directory_name,
    artifact_filename,
    render_report_markdown,
    validate_report_contract,
)
from src.research.schemas import (
    AnalystView,
    EvidenceItem,
    InformationSummary,
    ResearchEvidenceBook,
    ResearchReport,
)


def _report() -> ResearchReport:
    view = AnalystView(summary="Evidence-backed view.", score=62, evidence=["trend: neutral"], data_quality="high")
    return ResearchReport(
        run_id="publication-test",
        symbol="600519",
        market="ashare",
        company_name="贵州茅台",
        generated_at=datetime(2026, 6, 1, 8, 0, 0),
        rating="HOLD",
        confidence="medium",
        current_price=1326,
        price_target_6m=1450,
        thesis="Research thesis with explicit evidence boundaries.",
        key_metrics={"pe_ratio": 20, "pb_ratio": 6, "roe": 0.33, "external_sources": 2, "primary_sources": 1},
        valuation=view,
        financial_quality=view,
        macro_context=view,
        technical=view,
        sentiment=view,
        information_summary=InformationSummary(source_count=2),
        research_evidence=ResearchEvidenceBook(
            filings=[EvidenceItem(channel="filing", title="Annual report", quality="primary")],
        ),
        bull_case=["Brand and cash generation remain resilient."],
        bear_case=["Demand and channel inventory need monitoring."],
        catalysts=["Next earnings update."],
        risks=["Policy and channel risks remain."],
    )


def test_publication_contract_matches_stockresearch_naming():
    report = _report()
    assert archive_directory_name(report.symbol, report.company_name) == "600519_贵州茅台"
    assert artifact_filename(report, "report") == "600519_investment_report_20260601.md"
    assert artifact_filename(report, "macro") == "macro_briefing_20260601.md"


def test_institutional_report_contains_all_required_sections():
    markdown = render_report_markdown(_report())
    validate_report_contract(markdown)
    assert "## 六、多空辩论" in markdown
    assert "## 八、证据索引与数据缺口" in markdown
    assert "不是 DCF 结论" in markdown
