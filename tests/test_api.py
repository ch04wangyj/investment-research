from fastapi.testclient import TestClient

from src.api.main import app
from src.research.schemas import AnalystView, ResearchReport


def test_health_and_models():
    client = TestClient(app)
    health = client.get("/api/health")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"

    models = client.get("/api/models")
    assert models.status_code == 200
    assert "providers" in models.json()


def test_run_research_endpoint_with_mock_pipeline(monkeypatch):
    def fake_pipeline(symbol, period="6mo", provider_id=None, use_llm=False, language="zh"):
        view = AnalystView(summary="ok", score=55, evidence=[], data_quality="limited")
        return ResearchReport(
            run_id="run-test",
            symbol=symbol,
            market="us",
            company_name="Test Co",
            rating="HOLD",
            confidence="medium",
            thesis="Mock thesis",
            valuation=view,
            financial_quality=view,
            technical=view,
            sentiment=view,
        )

    monkeypatch.setattr("src.api.main.run_research_pipeline", fake_pipeline)
    class FakeRepo:
        def create_tables(self):
            return None

        def save(self, data):
            return 1

    monkeypatch.setattr("src.api.main._report_repo", lambda: FakeRepo())
    client = TestClient(app)
    response = client.post("/api/research/AAPL", json={"use_llm": False})
    assert response.status_code == 200
    assert response.json()["report"]["symbol"] == "AAPL"
    assert response.json()["audit"]["status"] == "blocked"
    assert response.json()["workflow"]["stages"]["audit"]["status"] == "completed"


def test_start_and_read_background_research_job(monkeypatch):
    class FakeJobs:
        def submit(self, *, symbol, execute, workflow):
            return {"job_id": "job-1", "symbol": symbol, "status": "queued"}

        def get(self, job_id, *, workflow):
            if job_id != "job-1":
                return None
            return {"job_id": job_id, "symbol": "AAPL", "status": "running", "workflow": {"stages": {}}}

    monkeypatch.setattr("src.api.main.research_jobs", FakeJobs())
    client = TestClient(app)
    started = client.post("/api/research/AAPL/jobs", json={"use_llm": False})
    assert started.status_code == 200
    assert started.json()["job_id"] == "job-1"
    running = client.get("/api/research/jobs/job-1")
    assert running.status_code == 200
    assert running.json()["status"] == "running"
    assert client.get("/api/research/jobs/missing").status_code == 404


def test_pdf_endpoint_returns_pdf(monkeypatch):
    class FakeRow:
        id = 1
        agent_name = "ResearchDirector"
        run_id = "run-test"
        ticker = "AAPL"
        report_type = "institutional_research"
        created_at = None
        trigger_type = "manual"
        content = {
            "run_id": "run-test",
            "symbol": "AAPL",
            "market": "us",
            "company_name": "Apple",
            "rating": "HOLD",
            "confidence": "medium",
            "thesis": "Test thesis",
            "valuation": {"summary": "PE 20", "score": 55, "evidence": ["PE 20"], "data_quality": "limited"},
            "financial_quality": {"summary": "ROE ok", "score": 55, "evidence": ["ROE 12%"], "data_quality": "limited"},
            "sentiment": {"summary": "Neutral", "score": 50, "evidence": [], "data_quality": "limited"},
        }

    class FakeRepo:
        def create_tables(self):
            return None

        def get_latest(self, symbol, limit=1):
            return [FakeRow()]

    monkeypatch.setattr("src.api.main._report_repo", lambda: FakeRepo())
    client = TestClient(app)
    response = client.get("/api/research/AAPL/pdf?lang=zh")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.content.startswith(b"%PDF")


def test_strategy_research_endpoint(monkeypatch):
    monkeypatch.setattr(
        "src.api.main.collect_strategy_research",
        lambda max_items_per_section=6: {
            "generated_at": "2026-01-01T00:00:00",
            "principles": ["research first"],
            "sections": [],
        },
    )
    client = TestClient(app)
    response = client.get("/api/strategy/research?limit=2")
    assert response.status_code == 200
    assert response.json()["principles"] == ["research first"]


def test_fixed_income_framework_endpoint():
    client = TestClient(app)
    response = client.get("/api/fixed-income/framework")
    assert response.status_code == 200
    assert len(response.json()["framework_sections"]) == 6


def test_fixed_income_overview_endpoint(monkeypatch):
    monkeypatch.setattr(
        "src.api.main.build_fixed_income_dashboard",
        lambda max_products_per_category=8: {
            "generated_at": "2026-01-01T00:00:00",
            "framework_sections": [],
            "agents": [],
            "market_snapshot": {"yield_curve": [], "curve_signals": [], "liquidity": [], "source_status": []},
            "allocation_profiles": [],
            "product_categories": [],
            "products": [{"id": "money:1"}],
        },
    )
    client = TestClient(app)
    response = client.get("/api/fixed-income/overview?limit=2")
    assert response.status_code == 200
    assert response.json()["products"][0]["id"] == "money:1"


def test_intelligence_overview_endpoint(monkeypatch):
    monkeypatch.setattr(
        "src.api.main.intelligence_overview",
        lambda limit=40: {
            "generated_at": "2026-06-01T00:00:00",
            "positioning": "auditable learning",
            "stats": {"total_documents": 1},
            "skills": [{"id": "source-ranked-research"}],
            "documents": [],
            "learning_protocol": [],
        },
    )
    client = TestClient(app)
    response = client.get("/api/intelligence/overview?limit=10")
    assert response.status_code == 200
    assert response.json()["skills"][0]["id"] == "source-ranked-research"


def test_intelligence_refresh_endpoint(monkeypatch):
    monkeypatch.setattr(
        "src.api.main.refresh_research_intelligence",
        lambda max_items_per_section=5: {"stats": {"total_documents": 3}},
    )
    client = TestClient(app)
    response = client.post("/api/intelligence/refresh?limit=3")
    assert response.status_code == 200
    assert response.json()["stats"]["total_documents"] == 3


def test_daily_reads_endpoint(monkeypatch):
    monkeypatch.setattr(
        "src.api.main.collect_daily_reads",
        lambda max_items_per_section=5: {
            "generated_at": "2026-01-01T00:00:00",
            "reading_protocol": ["macro first"],
            "sections": [{"id": "macro_strategy", "title": "Daily", "description": "", "items": []}],
        },
    )
    client = TestClient(app)
    response = client.get("/api/research/daily-reads?limit=2")
    assert response.status_code == 200
    assert response.json()["reading_protocol"] == ["macro first"]


def test_news_endpoint_exposes_source_catalog(monkeypatch):
    monkeypatch.setattr(
        "src.api.main.fetch_financial_news",
        lambda symbol=None, max_items=30: [{"title": "政策更新", "source": "东方财富财经"}],
    )
    client = TestClient(app)
    response = client.get("/api/news?limit=2")
    assert response.status_code == 200
    assert response.json()["items"][0]["title"] == "政策更新"
    assert any(item["region"] == "cn" for item in response.json()["sources"])


def test_workflow_blueprint_endpoint():
    client = TestClient(app)
    response = client.get("/api/workflow/blueprint")
    assert response.status_code == 200
    data = response.json()
    assert {item["framework"] for item in data["comparisons"]} >= {"TradingAgents", "FinRobot", "OpenBB"}
    assert len(data["registered_agents"]) >= 8


def test_workflow_agents_endpoint():
    client = TestClient(app)
    response = client.get("/api/workflow/agents")
    assert response.status_code == 200
    assert {item["id"] for item in response.json()["agents"]} >= {
        "kline-collector",
        "information-curator",
        "fundamentals-researcher",
        "macro-researcher",
        "technical-analyst",
        "institutional-report-editor",
        "report-writer",
        "research-auditor",
    }


def test_workflow_run_endpoint(monkeypatch):
    class FakeState:
        def to_dict(self):
            return {"symbol": "AAPL", "audit_status": "conditional"}

    class FakeOrchestrator:
        def load_state(self, symbol):
            return FakeState() if symbol == "AAPL" else None

    monkeypatch.setattr("src.api.main._research_orchestrator", lambda: FakeOrchestrator())
    client = TestClient(app)
    response = client.get("/api/workflow/runs/AAPL")
    assert response.status_code == 200
    assert response.json()["workflow"]["audit_status"] == "conditional"
    assert client.get("/api/workflow/runs/MSFT").status_code == 404


def test_delete_research_run_endpoint(monkeypatch):
    class FakeRepo:
        def create_tables(self):
            return None

        def delete_by_id(self, report_id):
            return report_id == 1

    monkeypatch.setattr("src.api.main._report_repo", lambda: FakeRepo())
    client = TestClient(app)
    response = client.delete("/api/research/runs/1")
    assert response.status_code == 200
    assert response.json() == {"status": "deleted", "id": 1}

    missing = client.delete("/api/research/runs/2")
    assert missing.status_code == 404


def test_batch_delete_research_runs_endpoint(monkeypatch):
    class FakeRepo:
        def create_tables(self):
            return None

        def delete_many(self, report_ids):
            assert report_ids == [1, 2, 3]
            return 2

    monkeypatch.setattr("src.api.main._report_repo", lambda: FakeRepo())
    client = TestClient(app)
    response = client.post("/api/research/runs/delete", json={"ids": [3, 2, 2, 1]})
    assert response.status_code == 200
    assert response.json()["deleted"] == 2
    assert response.json()["ids"] == [1, 2, 3]


def test_symbol_compare_endpoint(monkeypatch):
    class FakeDal:
        def get_symbol_profile(self, symbol, period="6mo"):
            return {
                "symbol": symbol,
                "market": "us",
                "quote": {
                    "source": "mock_quote",
                    "payload": [{"symbol": symbol, "name": f"{symbol} Inc", "close": 100, "change_pct": 1.2}],
                    "stale": False,
                    "error": None,
                },
                "fundamentals": {
                    "source": "mock_fund",
                    "payload": {"marketCap": 1000, "trailingPE": 20, "priceToBook": 4, "returnOnEquity": 0.18},
                    "stale": False,
                    "error": None,
                },
                "history": {"source": "mock_history", "payload": [], "stale": False, "error": None},
            }

    class FakeRepo:
        def create_tables(self):
            return None

        def get_latest(self, symbol, limit=1):
            return []

    monkeypatch.setattr("src.api.main.get_dal", lambda: FakeDal())
    monkeypatch.setattr("src.api.main._report_repo", lambda: FakeRepo())
    client = TestClient(app)
    response = client.get("/api/symbols/compare?symbols=AAPL,MSFT&period=6mo")
    assert response.status_code == 200
    data = response.json()
    assert data["symbols"] == ["AAPL", "MSFT"]
    assert data["items"][0]["pe_ratio"] == 20
    assert data["items"][0]["data_sources"]["quote"] == "mock_quote"


def test_symbol_risk_alert_endpoint(monkeypatch):
    monkeypatch.setattr("src.api.main.evaluate_symbol_risk", lambda symbol, period="6mo": [])
    client = TestClient(app)
    response = client.get("/api/risk/alerts/AAPL")
    assert response.status_code == 200
    data = response.json()
    assert data["symbol"] == "AAPL"
    assert data["summary"]["total"] == 0
