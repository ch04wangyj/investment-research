from src.data.dal import DataAccessLayer, detect_market, normalize_symbol
from src.data.cache import TieredCache
from src.data.providers.base import MarketDataProvider, ProviderResult


class FailingProvider(MarketDataProvider):
    def __init__(self, name="failing"):
        super().__init__(name=name, market="us", currency="USD", timezone_name="UTC")

    def get_quotes(self, symbols):
        return ProviderResult.failure(self.name, "boom")

    def get_historical(self, symbol, period="6mo"):
        return ProviderResult.failure(self.name, "boom")

    def get_fundamentals(self, symbol):
        return ProviderResult.failure(self.name, "boom")


class StaticProvider(MarketDataProvider):
    def __init__(self):
        super().__init__(name="static", market="us", currency="USD", timezone_name="UTC")

    def get_quotes(self, symbols):
        return ProviderResult(source=self.name, payload=[{"symbol": symbols[0], "close": 10.0}])

    def get_historical(self, symbol, period="6mo"):
        return ProviderResult(source=self.name, payload=[{"date": "2026-01-01", "close": 10.0}])

    def get_fundamentals(self, symbol):
        return ProviderResult(source=self.name, payload={"symbol": symbol, "pe_ratio": 20})


class IncompleteFundamentalsProvider(MarketDataProvider):
    def __init__(self):
        super().__init__(name="empty_fund", market="us", currency="USD", timezone_name="UTC")

    def get_quotes(self, symbols):
        return ProviderResult(source=self.name, payload=[{"symbol": symbols[0], "close": 10.0}])

    def get_historical(self, symbol, period="6mo"):
        return ProviderResult(source=self.name, payload=[])

    def get_fundamentals(self, symbol):
        return ProviderResult(source=self.name, payload={"symbol": symbol, "pe_ratio": None, "pb_ratio": None})


def test_market_detection_and_normalization():
    assert detect_market("600519") == "ashare"
    assert detect_market("00700") == "hk"
    assert detect_market("AAPL") == "us"
    assert normalize_symbol("700", "hk") == "00700"


def test_provider_fallback_returns_success_payload(tmp_path):
    cache = TieredCache(str(tmp_path / "cache.db"))
    dal = DataAccessLayer(providers={"us": [FailingProvider(), StaticProvider()]}, cache=cache)
    result = dal.get_quote_result("ZZZZ")
    assert result.ok
    assert result.source.startswith("static")
    assert result.payload[0]["close"] == 10.0


def test_legacy_quote_shape_includes_meta(tmp_path):
    cache = TieredCache(str(tmp_path / "cache.db"))
    dal = DataAccessLayer(providers={"us": [StaticProvider()]}, cache=cache)
    quote = dal.get_quotes("YYYY")
    assert quote["symbol"] == "YYYY"
    assert quote["_meta"]["source"].startswith("static")


def test_incomplete_fundamentals_continue_to_fallback(tmp_path):
    cache = TieredCache(str(tmp_path / "cache.db"))
    dal = DataAccessLayer(
        providers={"us": [IncompleteFundamentalsProvider(), StaticProvider()]},
        cache=cache,
    )
    result = dal.get_fundamentals_result("AAPL")
    assert result.ok
    assert result.source.startswith("static")
    assert result.payload["pe_ratio"] == 20
