import time

from src.api.research_jobs import ResearchJobRegistry


def test_background_job_completes_without_blocking_submit():
    registry = ResearchJobRegistry(max_workers=1)

    def execute():
        time.sleep(0.05)
        return {"report": {"symbol": "AAPL"}}

    job = registry.submit(
        symbol="AAPL",
        execute=execute,
        workflow=lambda symbol: {"symbol": symbol, "stages": {"kline": {"status": "running"}}},
    )
    assert job["status"] in {"queued", "running"}

    for _ in range(30):
        job = registry.get(job["job_id"])
        if job and job["status"] == "completed":
            break
        time.sleep(0.02)

    assert job is not None
    assert job["status"] == "completed"
    assert job["result"]["report"]["symbol"] == "AAPL"
