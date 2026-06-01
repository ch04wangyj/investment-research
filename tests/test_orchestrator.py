from src.orchestrator.pipeline import PipelineOrchestrator, StageStatus
from src.research.schemas import (
    AnalystView,
    DataSource,
    EvidenceItem,
    InformationSummary,
    ResearchEvidenceBook,
    ResearchReport,
)


def _fake_pipeline(symbol, **kwargs):
    view = AnalystView(summary="ok", score=60, evidence=["source"], data_quality="high")
    return ResearchReport(
        run_id=f"run-{symbol}",
        symbol=symbol,
        market="us" if symbol == "AAPL" else "ashare",
        company_name=f"{symbol} Co",
        rating="HOLD",
        confidence="medium",
        current_price=100,
        thesis="Evidence-backed thesis",
        valuation=view,
        financial_quality=view,
        sentiment=view,
        information_summary=InformationSummary(source_count=4),
        research_evidence=ResearchEvidenceBook(
            filings=[
                EvidenceItem(
                    channel="filing",
                    title="Annual report",
                    source="exchange",
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
        bull_case=["Demand remains resilient."],
        bear_case=["Valuation may compress."],
        sources=[DataSource(name="fake", stale=False)],
    )


def test_orchestrator_executes_audits_and_restores_state(tmp_path):
    orchestrator = PipelineOrchestrator(root=tmp_path, pipeline=_fake_pipeline)
    execution = orchestrator.run_single("AAPL")
    assert execution.audit.status == "approved"
    assert execution.workflow.is_complete
    assert execution.report.publication_audit is not None

    restored = orchestrator.load_state("AAPL")
    assert restored is not None
    assert restored.is_complete
    assert restored.stages["audit"].status == StageStatus.COMPLETED

    cached = orchestrator.run_single("AAPL", skip_completed=True)
    assert cached.report.run_id == execution.report.run_id


def test_orchestrator_runs_batch_in_input_order(tmp_path):
    orchestrator = PipelineOrchestrator(root=tmp_path, pipeline=_fake_pipeline)
    executions = orchestrator.run_batch(["AAPL", "600519"], parallel=True)
    assert [item.report.symbol for item in executions] == ["AAPL", "600519"]


def test_orchestrator_missing_state_does_not_create_symbol_directory(tmp_path):
    orchestrator = PipelineOrchestrator(root=tmp_path, pipeline=_fake_pipeline)
    assert orchestrator.load_state("MSFT") is None
    assert not (tmp_path / "MSFT").exists()


def test_orchestrator_marks_running_stages_failed(tmp_path):
    def broken_pipeline(symbol, **kwargs):
        raise RuntimeError("provider down")

    orchestrator = PipelineOrchestrator(root=tmp_path, pipeline=broken_pipeline)
    try:
        orchestrator.run_single("AAPL")
    except RuntimeError:
        pass
    else:
        raise AssertionError("Expected pipeline failure")

    restored = orchestrator.load_state("AAPL")
    assert restored is not None
    assert restored.stages["data_collection"].status == StageStatus.FAILED
    assert restored.stages["deep_research"].status == StageStatus.FAILED
