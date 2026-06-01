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
from src.research.publication import (
    archive_directory_name,
    artifact_filename,
    render_archive_readme,
    render_audit_markdown,
    render_fundamentals_markdown,
    render_macro_markdown,
    render_report_markdown,
    render_technical_markdown,
    validate_report_contract,
)
from src.research.schemas import PublicationAudit, ResearchReport


PipelineCallable = Callable[..., ResearchReport]


class StageStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"
    SKIPPED = "skipped"


class PipelineStage(str, Enum):
    KLINE = "kline"
    FUNDAMENTALS = "fundamentals"
    TECHNICAL = "technical"
    MACRO = "macro"
    REPORT = "report"
    AUDIT = "audit"
    PUBLISH = "publish"  # .md → .html + .pdf conversion


PIPELINE_STAGES = (
    PipelineStage.KLINE,
    PipelineStage.FUNDAMENTALS,
    PipelineStage.TECHNICAL,
    PipelineStage.MACRO,
    PipelineStage.REPORT,
    PipelineStage.AUDIT,
    PipelineStage.PUBLISH,
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
    archive_path: str | None = None
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
            archive_path=data.get("archive_path"),
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
            "archive_path": self.archive_path,
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

    def symbol_dir(self, symbol: str, company_name: str = "") -> Path:
        normalized = normalize_symbol(symbol)
        if company_name:
            return self.root / archive_directory_name(normalized, company_name)
        exact = self.root / normalized
        if exact.exists():
            return exact
        matches = sorted(path for path in self.root.glob(f"{normalized}_*") if path.is_dir())
        return matches[0] if matches else exact

    def get_state_path(self, symbol: str) -> Path:
        return self.root / ".workflow" / f"{normalize_symbol(symbol)}.json"

    def find_published_report_pdf(self, symbol: str) -> Path | None:
        normalized = normalize_symbol(symbol)
        archive_dirs = [
            path
            for path in [self.root / normalized, *self.root.glob(f"{normalized}_*")]
            if path.is_dir()
        ]
        candidates = sorted(
            (
                pdf
                for archive_dir in archive_dirs
                for pdf in (archive_dir / "reports").glob(
                    f"{normalized}_investment_report_*.pdf"
                )
            ),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
        return candidates[0] if candidates else None

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
        skip_completed: bool | None = None,
    ) -> ResearchExecution:
        """Run one complete audited research workflow."""
        settings = get_settings()
        skip_completed = settings.pipeline_skip_completed if skip_completed is None else skip_completed
        normalized = normalize_symbol(symbol)
        market = detect_market(normalized)
        previous = self.load_state(normalized)
        if skip_completed and previous and previous.is_complete and previous.report_path:
            return self._load_execution(previous)

        result = SymbolResult(symbol=normalized, name=name or normalized, market=market)
        for stage in PIPELINE_STAGES:
            result.stages[stage.value] = StageResult(stage=stage)
        self.save_state(result)

        active_stage = PipelineStage.KLINE
        try:
            for stage in [
                PipelineStage.KLINE,
                PipelineStage.FUNDAMENTALS,
                PipelineStage.TECHNICAL,
                PipelineStage.MACRO,
            ]:
                self._start_stage(result, stage)
            report = self.pipeline(
                normalized,
                period=period,
                provider_id=provider_id,
                use_llm=use_llm,
                language=language,
            )
            result.name = report.company_name
            result.archive_path = str(self.symbol_dir(report.symbol, report.company_name))
            archive_files = self._write_archive_inputs(report)
            self._complete_stage(result, PipelineStage.KLINE, archive_files["kline"])
            self._complete_stage(result, PipelineStage.FUNDAMENTALS, archive_files["fundamentals"])
            self._complete_stage(result, PipelineStage.TECHNICAL, archive_files["technical"])
            self._complete_stage(result, PipelineStage.MACRO, archive_files["macro"])

            active_stage = PipelineStage.REPORT
            self._start_stage(result, active_stage)
            report_path, report_markdown_path = self._write_report(report)
            result.report_path = str(report_path)
            self._complete_stage(
                result,
                active_stage,
                [str(report_path), str(report_markdown_path)],
            )

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

            # ── PUBLISH: .md → .html + .pdf (Moutai CSS template via Edge headless) ──
            active_stage = PipelineStage.PUBLISH
            self._start_stage(result, active_stage)
            if audit.status != "approved":
                self._block_stage(
                    result,
                    active_stage,
                    f"Publication gate is {audit.status}; resolve audit findings before final publication.",
                )
                self.save_state(result)
                return ResearchExecution(report=report, audit=audit, workflow=result)
            if not settings.pipeline_publish_enabled:
                self._skip_stage(result, active_stage, "Publication is disabled by configuration.")
                self.save_state(result)
                return ResearchExecution(report=report, audit=audit, workflow=result)
            publish_files = self._publish_formats(result)
            self._complete_stage(result, active_stage, publish_files)

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
        max_workers: int | None = None,
        **kwargs: Any,
    ) -> list[ResearchExecution]:
        """Run audited research workflows for multiple symbols."""
        items = [self._normalize_batch_item(item) for item in symbols]
        max_workers = max_workers or get_settings().pipeline_max_workers
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
        report_dir = self.symbol_dir(report.symbol, report.company_name) / "reports"
        report_dir.mkdir(parents=True, exist_ok=True)
        path = report_dir / f"{report.run_id}.json"
        path.write_text(report.model_dump_json(indent=2), encoding="utf-8")
        markdown_path = report_dir / artifact_filename(report, "report")
        markdown = render_report_markdown(report)
        validate_report_contract(markdown)
        markdown_path.write_text(markdown, encoding="utf-8")
        return path, markdown_path

    def _write_audit(self, report: ResearchReport, audit: PublicationAudit) -> tuple[Path, Path]:
        audit_dir = self.symbol_dir(report.symbol, report.company_name) / "audit"
        audit_dir.mkdir(parents=True, exist_ok=True)
        path = audit_dir / f"{report.run_id}.json"
        path.write_text(audit.model_dump_json(indent=2), encoding="utf-8")
        markdown_path = audit_dir / artifact_filename(report, "audit")
        markdown_path.write_text(render_audit_markdown(report, audit), encoding="utf-8")
        return path, markdown_path

    def _write_archive_inputs(self, report: ResearchReport) -> dict[str, list[str]]:
        """Write independent archive inputs before final publication rendering."""
        files = {
            "fundamentals": [self._write_section(report, "fundamentals", render_fundamentals_markdown(report))],
            "technical": [self._write_section(report, "technical", render_technical_markdown(report))],
            "macro": [self._write_section(report, "macro", render_macro_markdown(report))],
            "kline": self._write_kline_files(report),
        }
        readme = self.symbol_dir(report.symbol, report.company_name) / "README.md"
        readme.write_text(render_archive_readme(report), encoding="utf-8")
        files["macro"].append(str(readme))
        return files

    def _write_section(self, report: ResearchReport, section: str, markdown: str) -> str:
        directory = self.symbol_dir(report.symbol, report.company_name) / section
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / artifact_filename(report, section)
        path.write_text(markdown, encoding="utf-8")
        return str(path)

    def _write_kline_files(self, report: ResearchReport) -> list[str]:
        rows = report.archive_history
        if not rows:
            return []
        import pandas as pd

        frame = pd.DataFrame(rows)
        if "date" not in frame.columns:
            return []
        frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
        frame = frame.dropna(subset=["date"]).sort_values("date")
        if frame.empty:
            return []

        start = frame["date"].iloc[0].strftime("%Y%m%d")
        end = frame["date"].iloc[-1].strftime("%Y%m%d")
        kline_dir = self.symbol_dir(report.symbol, report.company_name) / "kline"
        daily_dir = kline_dir / "daily"
        weekly_dir = kline_dir / "weekly"
        daily_dir.mkdir(parents=True, exist_ok=True)
        weekly_dir.mkdir(parents=True, exist_ok=True)
        daily_path = daily_dir / f"{report.symbol}_daily_{start}_{end}.csv"
        weekly_path = weekly_dir / f"{report.symbol}_weekly_{start}_{end}.csv"
        frame.to_csv(daily_path, index=False, encoding="utf-8-sig")

        aggregations = {
            key: reducer
            for key, reducer in {
                "open": "first",
                "high": "max",
                "low": "min",
                "close": "last",
                "volume": "sum",
            }.items()
            if key in frame.columns
        }
        weekly = (
            frame.set_index("date")
            .resample("W-FRI")
            .agg(aggregations)
            .dropna(how="all")
            .reset_index()
        )
        weekly.to_csv(weekly_path, index=False, encoding="utf-8-sig")
        return [str(daily_path), str(weekly_path)]

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

    def _block_stage(self, result: SymbolResult, stage: PipelineStage, error: str) -> None:
        current = result.stages[stage.value]
        current.status = StageStatus.BLOCKED
        current.completed_at = datetime.now().isoformat()
        current.error = error

    def _skip_stage(self, result: SymbolResult, stage: PipelineStage, reason: str) -> None:
        current = result.stages[stage.value]
        current.status = StageStatus.SKIPPED
        current.completed_at = datetime.now().isoformat()
        current.error = reason

    @staticmethod
    def _normalize_batch_item(item: str | dict[str, Any]) -> dict[str, str]:
        if isinstance(item, str):
            return {"symbol": item}
        if not item.get("symbol"):
            raise ValueError("Each batch item requires a symbol")
        return {"symbol": str(item["symbol"]), "name": str(item.get("name", ""))}

    def _publish_formats(self, result: SymbolResult) -> list[str]:
        """Convert all .md outputs to .html + .pdf using the Moutai-standard pipeline.

        Calls scripts/md2pdf.py which:
        1. Runs scripts/md2html.py on each .md → .html (Moutai #8B0000 CSS)
        2. Prints each .html → .pdf via Edge headless (Windows native, no GTK)
        """
        import subprocess
        import sys

        sym_dir = Path(result.archive_path or self.symbol_dir(result.symbol))
        script = Path(__file__).resolve().parent.parent.parent / "scripts" / "md2pdf.py"
        if not script.exists():
            raise FileNotFoundError(f"md2pdf.py not found at {script}")

        result = subprocess.run(
            [sys.executable, str(script), str(sym_dir)],
            capture_output=True, text=True, timeout=300,
        )
        if result.returncode != 0:
            raise RuntimeError(f"Publish failed: {result.stderr.strip()}")
        return self._validate_published_archive(sym_dir)

    @staticmethod
    def _validate_published_archive(sym_dir: Path) -> list[str]:
        errors = []
        files = []
        for section in ["fundamentals", "technical", "macro", "reports", "audit"]:
            markdown_files = sorted((sym_dir / section).glob("*.md"))
            if not markdown_files:
                errors.append(f"{section}/ has no markdown artifact")
                continue
            for markdown in markdown_files:
                for suffix in [".md", ".html", ".pdf"]:
                    sibling = markdown.with_suffix(suffix)
                    if not sibling.exists() or sibling.stat().st_size <= 0:
                        errors.append(f"Missing or empty artifact: {sibling}")
                    else:
                        files.append(str(sibling))
        for period in ["daily", "weekly"]:
            csv_files = sorted((sym_dir / "kline" / period).glob("*.csv"))
            if not csv_files:
                errors.append(f"kline/{period}/ has no CSV artifact")
            files.extend(str(path) for path in csv_files)
        if not (sym_dir / "README.md").exists():
            errors.append("README.md is missing")
        else:
            files.append(str(sym_dir / "README.md"))
        if errors:
            raise RuntimeError("Archive publication validation failed:\n" + "\n".join(errors))
        return sorted(set(files))


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


def _analyst_view_markdown(title: str, report: ResearchReport, views: list[tuple[str, Any]]) -> str:
    lines = [
        f"# {report.company_name} ({report.symbol}) {title}",
        "",
        f"- Run ID: {report.run_id}",
        f"- Generated at: {report.generated_at.isoformat()}",
    ]
    for label, view in views:
        lines.extend(
            [
                "",
                f"## {label}",
                f"- Score: {view.score:.0f}/100",
                f"- Data quality: {view.data_quality}",
                "",
                view.summary,
                "",
                "### Evidence",
            ]
        )
        lines.extend([f"- {item}" for item in view.evidence] or ["- No structured evidence available."])
    lines.extend(["", "## Disclaimer", report.disclaimer])
    return "\n".join(lines)


def _fundamentals_markdown(report: ResearchReport) -> str:
    lines = [
        _analyst_view_markdown(
            "Fundamentals Snapshot",
            report,
            [("Valuation", report.valuation), ("Financial Quality", report.financial_quality)],
        ),
        "",
        "## Key Metrics",
    ]
    lines.extend([f"- {key}: {value}" for key, value in sorted(report.key_metrics.items())])
    return "\n".join(lines)


def _technical_markdown(report: ResearchReport) -> str:
    return _analyst_view_markdown(
        "Price Context Snapshot",
        report,
        [("Technical Context", report.technical)],
    )


def _macro_markdown(report: ResearchReport) -> str:
    return _analyst_view_markdown(
        "Macro Briefing",
        report,
        [("Macro And Policy Context", report.macro_context), ("News Sentiment", report.sentiment)],
    )


def _archive_readme(report: ResearchReport) -> str:
    return "\n".join(
        [
            f"# {report.company_name} ({report.symbol}) Research Archive",
            "",
            f"- Latest run: {report.run_id}",
            f"- Generated at: {report.generated_at.isoformat()}",
            f"- Rating: {report.rating}",
            f"- Confidence: {report.confidence}",
            "",
            "## Archive Layout",
            "- `kline/`: daily and weekly price context CSV files",
            "- `fundamentals/`: valuation and financial-quality snapshots",
            "- `technical/`: price-context snapshot",
            "- `macro/`: macro, policy, and public-news context",
            "- `reports/`: structured final report",
            "- `audit/`: deterministic publication gate",
            "",
            "## Disclaimer",
            report.disclaimer,
        ]
    )
