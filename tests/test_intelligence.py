from datetime import datetime
from types import SimpleNamespace

from src.research import intelligence
from src.research.intelligence import (
    ResearchIntelligenceRepository,
    intelligence_overview,
    refresh_research_intelligence,
    retrieve_research_context,
    search_research_intelligence,
    should_auto_refresh_research_intelligence,
)


def test_repository_upserts_and_searches_ranked_documents(tmp_path):
    repository = ResearchIntelligenceRepository(tmp_path / "intelligence.db")
    repository.upsert_documents([
        {
            "kind": "strategy_research",
            "category": "frontier_papers",
            "title": "Quality factor robustness",
            "summary": "Out-of-sample quality factor review.",
            "url": "https://example.com/quality",
            "source": "example.com",
            "quality": "institutional",
            "tags": ["quality", "factor"],
            "as_of": "2026-06-01",
        },
        {
            "kind": "daily_read",
            "category": "macro_strategy",
            "title": "Policy update",
            "summary": "Macro policy context.",
            "url": "https://example.com/policy",
            "source": "example.com",
            "quality": "media",
            "tags": ["macro"],
            "as_of": "2026-06-01",
        },
    ])
    result = search_research_intelligence(query="quality factor", repository=repository)
    assert result["items"][0]["title"] == "Quality factor robustness"
    assert repository.stats()["total_documents"] == 2


def test_refresh_collects_public_metadata_and_local_reference(monkeypatch, tmp_path):
    repository = ResearchIntelligenceRepository(tmp_path / "intelligence.db")
    monkeypatch.setattr(
        intelligence,
        "collect_daily_reads",
        lambda max_items_per_section=5: {
            "sections": [{"id": "macro_strategy", "items": [{
                "title": "Macro source",
                "summary": "summary",
                "url": "https://example.com/macro",
                "source": "example.com",
                "quality": "media",
                "tags": ["macro"],
                "as_of": "2026-06-01",
            }]}],
        },
    )
    monkeypatch.setattr(
        intelligence,
        "collect_strategy_research",
        lambda max_items_per_section=5: {"sections": []},
    )
    overview = refresh_research_intelligence(repository=repository)
    assert overview["stats"]["total_documents"] == 2
    assert any(item["kind"] == "local_reference" for item in overview["documents"])


def test_context_retrieval_returns_typed_evidence(tmp_path):
    repository = ResearchIntelligenceRepository(tmp_path / "intelligence.db")
    repository.upsert_documents([{
        "kind": "strategy_research",
        "category": "market_views",
        "title": "AAPL valuation review",
        "summary": "Public valuation context.",
        "url": "https://example.com/aapl",
        "source": "example.com",
        "quality": "institutional",
        "tags": ["valuation"],
        "as_of": "2026-06-01",
    }])
    evidence = retrieve_research_context("AAPL valuation", repository=repository)
    assert evidence[0].channel == "channel_analysis"
    assert evidence[0].query == "local_research_intelligence"


def test_overview_exposes_versioned_skill_packs(tmp_path):
    repository = ResearchIntelligenceRepository(tmp_path / "intelligence.db")
    overview = intelligence_overview(repository=repository)
    assert {skill["id"] for skill in overview["skills"]} >= {
        "source-ranked-research",
        "fixed-income-framework",
        "publication-gate",
    }


def test_auto_refresh_interval_is_enforced(monkeypatch, tmp_path):
    repository = ResearchIntelligenceRepository(tmp_path / "intelligence.db")
    monkeypatch.setattr(
        intelligence,
        "get_settings",
        lambda: SimpleNamespace(
            intelligence_auto_refresh_enabled=True,
            intelligence_refresh_hours=12,
        ),
    )
    assert should_auto_refresh_research_intelligence(repository)
    repository.record_refresh(datetime.now().isoformat(), "completed", 1)
    assert not should_auto_refresh_research_intelligence(repository)
