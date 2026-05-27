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
    def fake_pipeline(symbol, period="6mo", provider_id=None, use_llm=False):
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
