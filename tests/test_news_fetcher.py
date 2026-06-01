import pandas as pd

from src.data import news_fetcher


def test_news_source_catalog_exposes_mainland_channels():
    sources = news_fetcher.news_source_catalog()
    china_sources = {item["id"] for item in sources if item["region"] == "cn"}
    assert china_sources >= {
        "akshare_stock_news_em",
        "akshare_global_em",
        "akshare_global_ths",
        "akshare_global_sina",
        "sina_roll",
    }


def test_akshare_global_news_normalizes_china_metadata(monkeypatch):
    import akshare as ak

    class FakeCache:
        def get(self, key):
            return None

        def set(self, key, value, ttl_seconds):
            self.value = value

    monkeypatch.setattr(news_fetcher, "get_cache", lambda: FakeCache())
    monkeypatch.setattr(
        ak,
        "stock_info_global_em",
        lambda: pd.DataFrame([{
            "标题": "央行发布政策更新",
            "摘要": "政策工具保持灵活。",
            "发布时间": "2026-06-01 09:00:00",
            "链接": "https://finance.eastmoney.com/example.html",
        }]),
    )

    rows = news_fetcher._fetch_akshare_global_news("em", 2)

    assert rows[0]["source"] == "东方财富财经"
    assert rows[0]["source_region"] == "cn"
    assert rows[0]["source_channel"] == "akshare_global_em"
    assert rows[0]["category"] == "policy"


def test_single_symbol_news_filter_excludes_macro_roll_but_keeps_company_search():
    assert not news_fetcher.is_company_news_item({"source_channel": "sina_roll"})
    assert news_fetcher.is_company_news_item({"source_channel": "google_news_rss"})
