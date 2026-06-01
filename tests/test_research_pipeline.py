from src.agents.research import graph as research_graph
from src.data.providers.base import ProviderResult
from src.research.schemas import EvidenceItem, InstitutionalNarrative, ResearchEvidenceBook, ResearchReport


class FakeDAL:
    def get_quote_result(self, symbol):
        return ProviderResult(
            source="fake_quote",
            payload=[{"symbol": symbol, "name": "Apple", "close": 100.0}],
        )

    def get_fundamentals_result(self, symbol):
        return ProviderResult(
            source="fake_fund",
            payload={
                "symbol": symbol,
                "company_name": "Apple",
                "pe_ratio": 18,
                "pb_ratio": 3,
                "roe": 0.22,
                "market_cap": 3_000_000_000_000,
            },
        )

    def get_history_result(self, symbol, period):
        return ProviderResult(
            source="fake_history",
            payload=[
                {
                    "date": f"2026-01-{(i % 28) + 1:02d}",
                    "open": 80 + i,
                    "high": 81 + i,
                    "low": 79 + i,
                    "close": 80 + i,
                    "volume": 1000 + i,
                }
                for i in range(80)
            ],
        )


def test_research_pipeline_returns_typed_report(monkeypatch):
    monkeypatch.setattr(research_graph, "get_dal", lambda: FakeDAL())
    monkeypatch.setattr(
        research_graph,
        "collect_research_evidence",
        lambda *args, **kwargs: ResearchEvidenceBook(
            macro=[
                EvidenceItem(
                    channel="macro",
                    title="US macro cycle remains mixed",
                    url="https://example.com/macro",
                    source="example.com",
                    quality="media",
                    score=70,
                )
            ],
            filings=[
                EvidenceItem(
                    channel="filing",
                    title="Apple annual report",
                    url="https://www.sec.gov/example",
                    source="sec.gov",
                    quality="primary",
                    score=95,
                )
            ],
            institutional_reports=[
                EvidenceItem(
                    channel="institutional_report",
                    title="Apple public research note",
                    url="https://example.com/report.pdf",
                    source="example.com",
                    quality="search",
                    score=62,
                )
            ],
        ),
    )
    monkeypatch.setattr(
        research_graph,
        "fetch_financial_news",
        lambda symbol=None, max_items=5: [{"title": "Market breadth improves"}],
    )
    report = research_graph.run_research_pipeline("AAPL")
    assert isinstance(report, ResearchReport)
    assert report.symbol == "AAPL"
    assert report.rating in {"BUY", "HOLD", "SELL"}
    assert report.valuation.score >= 0
    assert report.macro_context.evidence
    assert report.information_summary.structured_facts
    assert report.research_evidence.total_items >= 3
    assert report.institutional_narrative.company_analysis
    assert report.institutional_narrative.valuation_analysis
    assert report.institutional_narrative.evidence_notes
    assert report.trading_strategy is None
    assert isinstance(report.risk_alerts, list)
    assert all(item.startswith("[待验证假设] ") for item in report.bull_case + report.bear_case)
    assert report.pipeline_diagnostics.topology == "guarded_dag"
    assert report.archive_history


def test_parallel_research_collection_keeps_primary_report_anchor(monkeypatch):
    monkeypatch.setattr(research_graph, "get_dal", lambda: FakeDAL())
    monkeypatch.setattr(
        research_graph,
        "collect_research_evidence",
        lambda *args, **kwargs: ResearchEvidenceBook(),
    )
    monkeypatch.setattr(
        research_graph,
        "fetch_financial_news",
        lambda symbol=None, max_items=5: [],
    )
    report = research_graph.run_research_pipeline("AAPL", symbols=["AAPL", "MSFT"])
    assert report.symbol == "AAPL"
    assert report.archive_history


def test_editor_claim_guard_removes_unsupported_comparisons():
    fallback = InstitutionalNarrative(evidence_notes="fallback")
    narrative = InstitutionalNarrative(
        valuation_analysis=(
            "PE 为 15.02 倍。估值处于历史心理低位区域，负面预期已定价。"
            "由于缺少同行比较数据，当前无法输出估值修复阈值。"
        ),
        evidence_notes="编辑稿。",
    )

    clean = research_graph._sanitize_institutional_narrative(
        narrative,
        fallback=fallback,
        language="zh",
    )

    assert "PE 为 15.02 倍" in clean.valuation_analysis
    assert "历史心理低位" not in clean.valuation_analysis
    assert "已定价" not in clean.valuation_analysis
    assert "缺少同行比较数据" in clean.valuation_analysis
    assert "证据约束层已过滤" in clean.evidence_notes
