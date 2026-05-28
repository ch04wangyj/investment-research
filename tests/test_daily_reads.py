from src.research import daily_reads


def test_daily_reads_uses_fallback_when_search_empty(monkeypatch):
    class FakeCache:
        def get(self, key):
            return None

        def set(self, key, value, ttl_seconds):
            self.value = value

    monkeypatch.setattr(daily_reads, "get_cache", lambda: FakeCache())
    monkeypatch.setattr(daily_reads, "_search_web", lambda query, max_results=3: [])

    payload = daily_reads.collect_daily_reads(max_items_per_section=2)

    assert len(payload["sections"]) == 3
    assert payload["sections"][0]["items"]
    assert payload["sections"][0]["items"][0]["url"].startswith("https://")
