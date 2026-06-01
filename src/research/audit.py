"""Deterministic publication checks for generated research reports.

The gate is intentionally conservative. It verifies report structure and
evidence coverage without pretending to perform claim-level fact checking.
"""

from __future__ import annotations

from src.research.schemas import AuditFinding, PublicationAudit, ResearchReport


def audit_research_report(report: ResearchReport) -> PublicationAudit:
    """Evaluate whether a generated report is ready for publication."""
    findings: list[AuditFinding] = []

    def add(
        code: str,
        severity: str,
        category: str,
        title: str,
        detail: str,
        remediation: str,
    ) -> None:
        findings.append(
            AuditFinding(
                code=code,
                severity=severity,
                category=category,
                title=title,
                detail=detail,
                remediation=remediation,
            )
        )

    if report.current_price is None:
        add(
            "missing_current_price",
            "critical",
            "market_data",
            "Current price is missing",
            "The report cannot anchor valuation or freshness without a current price.",
            "Refresh quote providers before publishing.",
        )
    if report.information_summary.source_count <= 0:
        add(
            "missing_sources",
            "critical",
            "evidence",
            "No usable sources were collected",
            "The report has no structured market source or public evidence item.",
            "Retry provider and evidence collection before publishing.",
        )
    if not report.research_evidence.filings:
        add(
            "missing_primary_filing",
            "warning",
            "evidence",
            "Primary filing coverage is incomplete",
            "No filing, annual report, SEC, or HKEX disclosure candidate was collected.",
            "Review the issuer disclosure channel manually or retry evidence collection.",
        )
    if not report.research_evidence.institutional_reports:
        add(
            "missing_institutional_report",
            "warning",
            "evidence",
            "External research comparison is incomplete",
            "No public institutional research lead was collected for comparison.",
            "Add at least one external report lead or explicitly document the gap.",
        )
    if not report.bull_case:
        add(
            "missing_bull_case",
            "critical",
            "challenge_review",
            "Bull case is missing",
            "The report was published without a supporting investment case.",
            "Run BullResearcher before synthesis.",
        )
    if not report.bear_case:
        add(
            "missing_bear_case",
            "critical",
            "challenge_review",
            "Bear case is missing",
            "The report was published without an opposing review.",
            "Run BearResearcher before synthesis.",
        )
    if len(report.archive_history) < 40:
        add(
            "insufficient_kline_history",
            "critical",
            "technical",
            "K-line history is insufficient",
            f"Only {len(report.archive_history)} OHLCV rows are available; institutional technical context requires at least 40.",
            "Refresh historical providers and rerun K-line collection.",
        )
    if not report.technical.evidence:
        add(
            "missing_technical_indicators",
            "critical",
            "technical",
            "Technical indicator dashboard is missing",
            "The technical analyst did not produce auditable indicator evidence.",
            "Rerun TechnicalAnalyst after usable OHLCV history is collected.",
        )
    if not report.catalysts:
        add(
            "missing_catalysts",
            "warning",
            "research_depth",
            "Catalyst monitoring list is missing",
            "The report has no explicit event or operating catalyst list.",
            "Add earnings, policy, product, or operating checkpoints.",
        )
    if not report.risks:
        add(
            "missing_risk_register",
            "critical",
            "risk",
            "Risk register is missing",
            "The final report does not contain a synthesized risk register.",
            "Run risk monitoring and BearResearcher before publication.",
        )

    stale_sources = [source.name for source in report.sources if source.stale]
    if stale_sources:
        add(
            "stale_sources",
            "warning",
            "freshness",
            "Some sources are stale",
            "Cached or stale sources: " + ", ".join(stale_sources[:6]),
            "Refresh stale sources when a live decision depends on them.",
        )

    source_errors = [source.name for source in report.sources if source.error]
    if source_errors:
        add(
            "provider_errors",
            "warning",
            "provider",
            "Some providers returned errors",
            "Degraded sources: " + ", ".join(source_errors[:6]),
            "Inspect provider fallback metadata and retry failed sources.",
        )

    gaps = report.information_summary.data_gaps
    if gaps:
        add(
            "data_gaps",
            "warning",
            "evidence",
            "The report contains unresolved data gaps",
            "; ".join(gaps[:5]),
            "Resolve material gaps or keep the report in conditional status.",
        )

    if report.rating == "BUY" and report.confidence == "low":
        add(
            "low_confidence_buy",
            "warning",
            "rating",
            "BUY rating has low confidence",
            "The rating is more assertive than the report confidence.",
            "Revisit the rating or collect stronger supporting evidence.",
        )

    critical_count = sum(item.severity == "critical" for item in findings)
    warning_count = sum(item.severity == "warning" for item in findings)
    score = max(0.0, 100.0 - critical_count * 30.0 - warning_count * 8.0)
    status = "blocked" if critical_count else ("conditional" if warning_count else "approved")
    return PublicationAudit(
        status=status,
        score=score,
        findings=findings,
        checks=[
            "Required market anchors are present.",
            "Evidence coverage and unresolved gaps are surfaced.",
            "Bull and Bear cases both reach the publication gate.",
            "K-line history, technical indicators, catalysts, and risk register are present.",
            "Provider freshness and fallback errors are visible.",
            "The publication gate does not claim human-level source-to-claim verification.",
        ],
    )
