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


def test_symbol_risk_alert_endpoint(monkeypatch):
    monkeypatch.setattr("src.api.main.evaluate_symbol_risk", lambda symbol, period="6mo": [])
    client = TestClient(app)
    response = client.get("/api/risk/alerts/AAPL")
    assert response.status_code == 200
    data = response.json()
    assert data["symbol"] == "AAPL"
    assert data["summary"]["total"] == 0
