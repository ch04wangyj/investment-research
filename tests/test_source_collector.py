from src.research import source_collector


def test_build_research_queries_targets_official_sources():
    queries = source_collector.build_research_queries(
        "AAPL",
        "us",
        company_name="Apple",
        sector="Consumer Electronics",
    )
    assert any("sec.gov" in query for query in queries["filing"])
    assert queries["macro"]
    assert queries["institutional_report"]


def test_collect_research_evidence_groups_results(monkeypatch):
    def fake_search(query, max_results):
        return [{
            "title": f"Result for {query}",
            "summary": "summary",
            "url": "https://www.sec.gov/example.pdf" if "10-K" in query else "https://example.com/research",
        }]

    monkeypatch.setattr(source_collector, "_search_web", fake_search)
    monkeypatch.setattr(
        source_collector,
        "fetch_financial_news",
        lambda symbol=None, max_items=6: [{"title": "Policy update", "url": "https://news.example.com"}],
    )
    monkeypatch.setattr(source_collector.get_cache(), "get", lambda key: None)
    monkeypatch.setattr(source_collector.get_cache(), "set", lambda *args, **kwargs: None)

    book = source_collector.collect_research_evidence("AAPL", "us", company_name="Apple")
    assert book.filings
    assert book.filings[0].quality == "primary"
    assert book.macro
    assert book.news
    assert book.total_items >= 4
