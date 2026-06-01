"""Executable orchestration layer for audited research publication workflows."""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Callable

from config.settings import get_settings
from src.data.dal import detect_market, normalize_symbol
from src.research.audit import audit_research_report
from src.research.schemas import PublicationAudit, ResearchReport


PipelineCallable = Callable[..., ResearchReport]


class StageStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class PipelineStage(str, Enum):
    DATA_COLLECTION = "data_collection"
    DEEP_RESEARCH = "deep_research"
    REPORT_GENERATION = "report_generation"
    AUDIT = "audit"


PIPELINE_STAGES = (
    PipelineStage.DATA_COLLECTION,
    PipelineStage.DEEP_RESEARCH,
    PipelineStage.REPORT_GENERATION,
    PipelineStage.AUDIT,
)


@dataclass
class StageResult:
    stage: PipelineStage
    status: StageStatus = StageStatus.PENDING
    output_files: list[str] = field(default_factory=list)
    error: str | None = None
    started_at: str | None = None
    completed_at: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "StageResult":
        return cls(
            stage=PipelineStage(data["stage"]),
            status=StageStatus(data.get("status", StageStatus.PENDING.value)),
            output_files=list(data.get("output_files", [])),
            error=data.get("error"),
            started_at=data.get("started_at"),
            completed_at=data.get("completed_at"),
        )

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["stage"] = self.stage.value
        result["status"] = self.status.value
        return result


@dataclass
class SymbolResult:
    symbol: str
    name: str
    market: str
    stages: dict[str, StageResult] = field(default_factory=dict)
    run_id: str | None = None
    rating: str | None = None
    target_price: float | None = None
    current_price: float | None = None
    audit_status: str | None = None
    report_path: str | None = None
    audit_path: str | None = None
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())

    @property
    def is_complete(self) -> bool:
        return all(
            self.stages.get(stage.value, StageResult(stage)).status == StageStatus.COMPLETED
            for stage in PIPELINE_STAGES
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SymbolResult":
        return cls(
            symbol=data["symbol"],
            name=data.get("name", ""),
            market=data.get("market", detect_market(data["symbol"])),
            stages={
                key: StageResult.from_dict(value)
                for key, value in data.get("stages", {}).items()
            },
            run_id=data.get("run_id"),
            rating=data.get("rating"),
            target_price=data.get("target_price"),
            current_price=data.get("current_price"),
            audit_status=data.get("audit_status"),
            report_path=data.get("report_path"),
            audit_path=data.get("audit_path"),
            updated_at=data.get("updated_at", datetime.now().isoformat()),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "name": self.name,
            "market": self.market,
            "stages": {key: value.to_dict() for key, value in self.stages.items()},
            "run_id": self.run_id,
            "rating": self.rating,
            "target_price": self.target_price,
            "current_price": self.current_price,
            "audit_status": self.audit_status,
            "report_path": self.report_path,
            "audit_path": self.audit_path,
            "updated_at": self.updated_at,
            "is_complete": self.is_complete,
        }


@dataclass
class ResearchExecution:
    report: ResearchReport
    audit: PublicationAudit
    workflow: SymbolResult

    def to_dict(self) -> dict[str, Any]:
        return {
            "report": self.report.model_dump(mode="json"),
            "audit": self.audit.model_dump(mode="json"),
            "workflow": self.workflow.to_dict(),
        }


class PipelineOrchestrator:
    """Run the LangGraph research DAG and publish audited local artifacts."""

    def __init__(
        self,
        root: Path | str | None = None,
        pipeline: PipelineCallable | None = None,
    ):
        self.root = Path(root or get_settings().stock_research_root)
        self.root.mkdir(parents=True, exist_ok=True)
        if pipeline is None:
            from src.agents.research.graph import run_research_pipeline

            pipeline = run_research_pipeline
        self.pipeline = pipeline

    def symbol_dir(self, symbol: str) -> Path:
        normalized = normalize_symbol(symbol)
        return self.root / normalized

    def get_state_path(self, symbol: str) -> Path:
        return self.symbol_dir(symbol) / "pipeline_state.json"

    def load_state(self, symbol: str) -> SymbolResult | None:
        path = self.get_state_path(symbol)
        if not path.exists():
            return None
        return SymbolResult.from_dict(json.loads(path.read_text(encoding="utf-8")))

    def save_state(self, result: SymbolResult) -> None:
        result.updated_at = datetime.now().isoformat()
        path = self.get_state_path(result.symbol)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(result.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def run_single(
        self,
        symbol: str,
        *,
        name: str = "",
        period: str = "6mo",
        provider_id: str | None = None,
        use_llm: bool = False,
        language: str = "zh",
        skip_completed: bool = False,
    ) -> ResearchExecution:
        """Run one complete audited research workflow."""
        normalized = normalize_symbol(symbol)
        market = detect_market(normalized)
        previous = self.load_state(normalized)
        if skip_completed and previous and previous.is_complete and previous.report_path:
            return self._load_execution(previous)

        result = SymbolResult(symbol=normalized, name=name or normalized, market=market)
        for stage in PIPELINE_STAGES:
            result.stages[stage.value] = StageResult(stage=stage)
        self.save_state(result)

        active_stage = PipelineStage.DATA_COLLECTION
        try:
            self._start_stage(result, PipelineStage.DATA_COLLECTION)
            active_stage = PipelineStage.DEEP_RESEARCH
            self._start_stage(result, PipelineStage.DEEP_RESEARCH)
            report = self.pipeline(
                normalized,
                period=period,
                provider_id=provider_id,
                use_llm=use_llm,
                language=language,
            )
            self._complete_stage(result, PipelineStage.DATA_COLLECTION)
            self._complete_stage(result, PipelineStage.DEEP_RESEARCH)

            active_stage = PipelineStage.REPORT_GENERATION
            self._start_stage(result, active_stage)
            report_path, report_markdown_path = self._write_report(report)
            result.report_path = str(report_path)
            self._complete_stage(result, active_stage, [str(report_path), str(report_markdown_path)])

            active_stage = PipelineStage.AUDIT
            self._start_stage(result, active_stage)
            audit = audit_research_report(report)
            report = report.model_copy(update={"publication_audit": audit})
            report_path, report_markdown_path = self._write_report(report)
            audit_path, audit_markdown_path = self._write_audit(report, audit)
            result.run_id = report.run_id
            result.rating = report.rating
            result.target_price = report.price_target_6m
            result.current_price = report.current_price
            result.audit_status = audit.status
            result.report_path = str(report_path)
            result.audit_path = str(audit_path)
            self._complete_stage(result, active_stage, [str(audit_path), str(audit_markdown_path)])
            self.save_state(result)
            return ResearchExecution(report=report, audit=audit, workflow=result)
        except Exception as exc:
            self._fail_running_stages(result, str(exc))
            self.save_state(result)
            raise

    def run_batch(
        self,
        symbols: list[str | dict[str, Any]],
        *,
        parallel: bool = True,
        max_workers: int = 4,
        **kwargs: Any,
    ) -> list[ResearchExecution]:
        """Run audited research workflows for multiple symbols."""
        items = [self._normalize_batch_item(item) for item in symbols]
        if not parallel or len(items) <= 1:
            return [self.run_single(**item, **kwargs) for item in items]

        results: dict[int, ResearchExecution] = {}
        with ThreadPoolExecutor(max_workers=min(max_workers, len(items))) as executor:
            future_map = {
                executor.submit(self.run_single, **item, **kwargs): index
                for index, item in enumerate(items)
            }
            for future in as_completed(future_map):
                results[future_map[future]] = future.result()
        return [results[index] for index in range(len(items))]

    def _load_execution(self, state: SymbolResult) -> ResearchExecution:
        report = ResearchReport.model_validate_json(
            Path(state.report_path or "").read_text(encoding="utf-8")
        )
        audit = report.publication_audit or audit_research_report(report)
        return ResearchExecution(report=report, audit=audit, workflow=state)

    def _write_report(self, report: ResearchReport) -> tuple[Path, Path]:
        report_dir = self.symbol_dir(report.symbol) / "reports"
        report_dir.mkdir(parents=True, exist_ok=True)
        path = report_dir / f"{report.run_id}.json"
        path.write_text(report.model_dump_json(indent=2), encoding="utf-8")
        markdown_path = report_dir / f"{report.run_id}.md"
        markdown_path.write_text(_report_markdown(report), encoding="utf-8")
        return path, markdown_path

    def _write_audit(self, report: ResearchReport, audit: PublicationAudit) -> tuple[Path, Path]:
        audit_dir = self.symbol_dir(report.symbol) / "audit"
        audit_dir.mkdir(parents=True, exist_ok=True)
        path = audit_dir / f"{report.run_id}.json"
        path.write_text(audit.model_dump_json(indent=2), encoding="utf-8")
        markdown_path = audit_dir / f"{report.run_id}.md"
        markdown_path.write_text(_audit_markdown(report, audit), encoding="utf-8")
        return path, markdown_path

    def _start_stage(self, result: SymbolResult, stage: PipelineStage) -> None:
        current = result.stages[stage.value]
        current.status = StageStatus.RUNNING
        current.started_at = datetime.now().isoformat()
        current.error = None
        self.save_state(result)

    def _complete_stage(
        self,
        result: SymbolResult,
        stage: PipelineStage,
        output_files: list[str] | None = None,
    ) -> None:
        current = result.stages[stage.value]
        current.status = StageStatus.COMPLETED
        current.completed_at = datetime.now().isoformat()
        current.output_files = output_files or current.output_files
        self.save_state(result)

    def _fail_running_stages(self, result: SymbolResult, error: str) -> None:
        for current in result.stages.values():
            if current.status != StageStatus.RUNNING:
                continue
            current.status = StageStatus.FAILED
            current.completed_at = datetime.now().isoformat()
            current.error = error

    @staticmethod
    def _normalize_batch_item(item: str | dict[str, Any]) -> dict[str, str]:
        if isinstance(item, str):
            return {"symbol": item}
        if not item.get("symbol"):
            raise ValueError("Each batch item requires a symbol")
        return {"symbol": str(item["symbol"]), "name": str(item.get("name", ""))}


def _report_markdown(report: ResearchReport) -> str:
    return "\n".join(
        [
            f"# {report.company_name} ({report.symbol}) Research Report",
            "",
            f"- Rating: {report.rating}",
            f"- Confidence: {report.confidence}",
            f"- Current price: {report.current_price if report.current_price is not None else 'N/A'}",
            f"- 6M target: {report.price_target_6m if report.price_target_6m is not None else 'N/A'}",
            f"- Publication gate: {report.publication_audit.status if report.publication_audit else 'pending'}",
            "",
            "## Thesis",
            report.thesis,
            "",
            "## Bull Case",
            *[f"- {item}" for item in report.bull_case],
            "",
            "## Bear Case",
            *[f"- {item}" for item in report.bear_case],
            "",
            "## Data Gaps",
            *[f"- {item}" for item in report.information_summary.data_gaps],
            "",
            "## Disclaimer",
            report.disclaimer,
        ]
    )


def _audit_markdown(report: ResearchReport, audit: PublicationAudit) -> str:
    lines = [
        f"# {report.company_name} ({report.symbol}) Publication Audit",
        "",
        f"- Status: {audit.status}",
        f"- Score: {audit.score:.0f}/100",
        f"- Reviewer: {audit.reviewer}",
        "",
        "## Findings",
    ]
    if not audit.findings:
        lines.append("- No automated publication blockers found.")
    for finding in audit.findings:
        lines.append(
            f"- [{finding.severity.upper()}] {finding.title}: "
            f"{finding.detail} Remediation: {finding.remediation}"
        )
    lines.extend(["", "## Scope", audit.disclaimer])
    return "\n".join(lines)
