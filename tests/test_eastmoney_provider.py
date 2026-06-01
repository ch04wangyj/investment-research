from src.data.providers import akshare_provider
from src.data.providers.akshare_provider import EastmoneyAshareProvider, EastmoneyHkProvider


def test_eastmoney_ashare_snapshot_exposes_quote_and_valuation(monkeypatch):
    monkeypatch.setattr(
        akshare_provider,
        "_eastmoney_snapshot",
        lambda symbol, market: {
            "f43": 130960,
            "f44": 132700,
            "f45": 130131,
            "f46": 132700,
            "f47": 43845,
            "f48": 5741133268.0,
            "f57": "600519",
            "f58": "贵州茅台",
            "f59": 2,
            "f60": 132600,
            "f116": 1637106864669.6,
            "f162": 1502,
            "f167": 604,
            "f170": -124,
            "f173": 10.57,
        },
    )

    provider = EastmoneyAshareProvider()
    quote = provider.get_quotes(["600519"])
    fundamentals = provider.get_fundamentals("600519")

    assert quote.payload[0]["close"] == 1309.6
    assert quote.payload[0]["change_pct"] == -1.24
    assert fundamentals.payload["pe_ratio"] == 15.02
    assert fundamentals.payload["pb_ratio"] == 6.04
    assert fundamentals.payload["roe"] == 10.57


def test_eastmoney_hk_symbol_uses_hk_security_id():
    assert akshare_provider._eastmoney_security_id("00700", "hk") == "116.00700"
    assert EastmoneyHkProvider().market == "hk"
