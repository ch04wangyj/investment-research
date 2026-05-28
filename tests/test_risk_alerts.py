from datetime import datetime

from src.risk.alerts import (
    evaluate_symbol_risk_from_payload,
    risk_penalty,
    summarize_alerts,
)


def test_drawdown_alert_triggers_critical():
    history = [
        {"date": f"2026-01-{index + 1:02d}", "close": price}
        for index, price in enumerate([100, 120, 118, 102, 94, 88, 84])
    ]

    alerts = evaluate_symbol_risk_from_payload(
        symbol="AAPL",
        market="us",
        history=history,
        news=[],
        sources=[{"source": "fake", "payload": history, "error": None}],
        now=datetime(2026, 3, 15),
    )

    drawdown = [alert for alert in alerts if alert.category == "drawdown"]
    assert drawdown
    assert drawdown[0].severity == "critical"
    assert risk_penalty(alerts) >= 12


def test_policy_news_and_earnings_alerts_are_structured():
    alerts = evaluate_symbol_risk_from_payload(
        symbol="600519",
        market="ashare",
        history=[{"date": f"2026-04-{index + 1:02d}", "close": 100 + index} for index in range(65)],
        news=[{"title": "央行释放政策信号，监管部门强调资本市场稳定", "summary": ""}],
        sources=[{"source": "fake", "payload": [], "error": None}],
        now=datetime(2026, 4, 20),
    )

    categories = {alert.category for alert in alerts}
    assert "policy_event" in categories
    assert "earnings_season" in categories
    summary = summarize_alerts(alerts)
    assert summary["total"] == len(alerts)
    assert summary["by_category"]["policy_event"] >= 1


def test_invalid_zero_quote_does_not_trigger_crash_drawdown():
    alerts = evaluate_symbol_risk_from_payload(
        symbol="600519",
        market="ashare",
        quote={"close": 0, "change_pct": -100},
        history=[{"date": f"2026-03-{index + 1:02d}", "close": 100 + index} for index in range(10)],
        news=[],
        sources=[{"source": "fake", "payload": [], "error": None}],
        now=datetime(2026, 3, 20),
    )

    assert not any("实时/近实时行情显示跌幅 -100" in alert.message for alert in alerts)
