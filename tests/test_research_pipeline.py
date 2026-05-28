from src.agents.research import graph as research_graph
from src.data.providers.base import ProviderResult
from src.research.schemas import ResearchReport


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
        "fetch_financial_news",
        lambda symbol=None, max_items=5: [{"title": "Market breadth improves"}],
    )
    report = research_graph.run_research_pipeline("AAPL")
    assert isinstance(report, ResearchReport)
    assert report.symbol == "AAPL"
    assert report.rating in {"BUY", "HOLD", "SELL"}
    assert report.valuation.score >= 0
    assert report.information_summary.structured_facts
    assert report.trading_strategy is not None
    assert report.trading_strategy.action in {"accumulate", "hold", "reduce", "avoid"}
    assert isinstance(report.risk_alerts, list)
    assert report.pipeline_diagnostics.topology == "guarded_dag"
