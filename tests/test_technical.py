from src.analysis.technical import compute_technical_snapshot


def test_compute_technical_snapshot_has_indicators():
    history = [
        {
            "date": f"2026-01-{(i % 28) + 1:02d}",
            "open": 100 + i,
            "high": 101 + i,
            "low": 99 + i,
            "close": 100 + i,
            "volume": 1000 + i,
        }
        for i in range(80)
    ]
    snapshot = compute_technical_snapshot(history)
    assert snapshot["data_quality"] == "high"
    assert snapshot["indicators"]["sma_20"] is not None
    assert snapshot["indicators"]["rsi_14"] is not None
    assert snapshot["indicators"]["trend"] in {"uptrend", "downtrend", "neutral"}
