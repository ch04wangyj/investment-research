#!/usr/bin/env python
"""CLI entry point for the institutional research pipeline."""

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv

load_dotenv(str(PROJECT_ROOT / ".env"))


def main():
    parser = argparse.ArgumentParser(description="AI Investment Research — Research Pipeline")
    parser.add_argument("ticker", help="Ticker, e.g. 600519, 00700, AAPL")
    parser.add_argument("--period", default="6mo", help="History period, e.g. 3mo, 6mo, 1y")
    parser.add_argument("--provider", default=None, help="LLM provider id from /api/models")
    parser.add_argument("--use-llm", action="store_true", help="Use configured LLM to polish thesis")
    parser.add_argument("--save-db", action="store_true", help="Save report to SQLite")
    args = parser.parse_args()

    from src.orchestrator.pipeline import PipelineOrchestrator

    execution = PipelineOrchestrator().run_single(
        args.ticker,
        period=args.period,
        provider_id=args.provider,
        use_llm=args.use_llm,
    )
    report = execution.report
    # Handle Windows GBK console encoding
    json_output = report.model_dump_json(indent=2)
    try:
        print(json_output)
    except UnicodeEncodeError:
        sys.stdout.reconfigure(encoding="utf-8")
        print(json_output)

    if args.save_db:
        from src.storage.repository import AgentReportRepository
        from config.settings import get_settings

        repo = AgentReportRepository(get_settings().operational_db_path)
        repo.create_tables()
        repo.save({
            "agent_name": "ResearchDirectorAudited",
            "run_id": report.run_id,
            "ticker": report.symbol,
            "report_type": "institutional_research",
            "content": report.model_dump(mode="json"),
            "trigger_type": "manual",
        })
        print(f"\nSaved to {get_settings().operational_db_path}")


if __name__ == "__main__":
    main()
