from src.research.audit import audit_research_report
from src.research.schemas import (
    AnalystView,
    DataSource,
    EvidenceItem,
    InformationSummary,
    ResearchEvidenceBook,
    ResearchReport,
)


def _report(**overrides):
    view = AnalystView(summary="ok", score=60, evidence=["source"], data_quality="high")
    values = {
        "run_id": "audit-test",
        "symbol": "AAPL",
        "market": "us",
        "company_name": "Apple",
        "rating": "HOLD",
        "confidence": "medium",
        "current_price": 100,
        "thesis": "Evidence-backed thesis",
        "valuation": view,
        "financial_quality": view,
        "technical": view,
        "sentiment": view,
        "information_summary": InformationSummary(source_count=4),
        "research_evidence": ResearchEvidenceBook(
            filings=[
                EvidenceItem(
                    channel="filing",
                    title="Annual report",
                    source="sec.gov",
                    quality="primary",
                )
            ],
            institutional_reports=[
                EvidenceItem(
                    channel="institutional_report",
                    title="Research note",
                    source="example.com",
                    quality="institutional",
                )
            ],
        ),
        "bull_case": ["Demand remains resilient."],
        "bear_case": ["Valuation may compress."],
        "catalysts": ["Quarterly earnings review."],
        "risks": ["Demand slowdown."],
        "sources": [DataSource(name="fake", stale=False)],
        "archive_history": [{"date": f"2026-01-{(index % 28) + 1:02d}"} for index in range(60)],
    }
    values.update(overrides)
    return ResearchReport(**values)


def test_publication_audit_approves_complete_report():
    audit = audit_research_report(_report())
    assert audit.status == "approved"
    assert audit.score == 100
    assert audit.findings == []


def test_publication_audit_blocks_missing_anchor_and_opposing_case():
    audit = audit_research_report(
        _report(
            current_price=None,
            information_summary=InformationSummary(source_count=0),
            bear_case=[],
        )
    )
    assert audit.status == "blocked"
    assert {finding.code for finding in audit.findings} >= {
        "missing_current_price",
        "missing_sources",
        "missing_bear_case",
    }
