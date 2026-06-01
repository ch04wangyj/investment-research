from __future__ import annotations

import pandas as pd

from src.research.fixed_income import (
    _bond_fund_category,
    _normalize_bond_funds,
    _normalize_money_funds,
    _normalize_repo_rates,
    _normalize_yield_curve,
    _repair_text,
    build_fixed_income_dashboard,
    fixed_income_framework,
)


def test_fixed_income_framework_has_audited_agent_roles():
    framework = fixed_income_framework()
    assert len(framework["framework_sections"]) == 6
    assert {item["id"] for item in framework["agents"]} >= {
        "fixed-income-planner",
        "macro-cycle-analyst",
        "liquidity-policy-analyst",
        "rates-strategist",
        "fixed-income-director",
    }
    assert framework["reference"]["local_reference"] is True


def test_repair_text_decodes_utf8_mojibake():
    mojibake = "基金代码".encode("utf-8").decode("latin1")
    assert _repair_text(mojibake) == "基金代码"
    assert _repair_text("基金代码") == "基金代码"


def test_normalize_yield_curve_calculates_curve_and_credit_spreads():
    frame = pd.DataFrame([
        {"曲线名称": "中债国债收益率曲线", "日期": "2026-05-29", "1年": 1.2, "3年": 1.5, "10年": 1.8},
        {"曲线名称": "中债中短期票据收益率曲线(AAA)", "日期": "2026-05-29", "1年": 1.6, "3年": 1.9, "10年": 2.2},
    ])
    result = _normalize_yield_curve(frame)
    signal_map = {item["name"]: item["value"] for item in result["signals"]}
    curve_map = {item["tenor"]: item for item in result["curve"]}
    assert signal_map["国债 10Y-1Y"] == 60
    assert signal_map["AAA 中票 3Y-国债 3Y"] == 40
    assert curve_map["3年"]["credit_spread_bp"] == 40


def test_normalize_repo_rates_returns_key_liquidity_metrics():
    frame = pd.DataFrame([
        {"date": "2026-05-29", "FDR001": 1.42, "FDR007": 1.58, "FR007": 1.72},
    ])
    result = _normalize_repo_rates(frame)
    assert {item["name"] for item in result["metrics"]} == {"FDR001", "FDR007", "FR007"}


def test_normalize_fund_products_classifies_and_limits_rows():
    bond_frame = pd.DataFrame([
        {"序号": 1, "基金代码": "000001", "基金简称": "示例短债A", "日期": "2026-05-29", "单位净值": 1.02, "近1年": "2.3%"},
        {"序号": 2, "基金代码": "000002", "基金简称": "示例可转债A", "日期": "2026-05-29", "单位净值": 1.11, "近1年": "6.8%"},
    ])
    money_frame = pd.DataFrame([
        {"序号": 1, "基金代码": "100001", "基金简称": "示例货币A", "日期": "2026-05-29", "万份收益": 0.42, "年化收益率7日": "1.52%"},
    ])
    assert _bond_fund_category("示例短债A") == "pure_bond_short"
    assert _bond_fund_category("示例可转债A") == "convertible_bond"
    assert _normalize_bond_funds(bond_frame, 1)[0]["category"] == "pure_bond_short"
    assert _normalize_money_funds(money_frame, 1)[0]["annualized_7d_pct"] == 1.52


def test_dashboard_merges_live_sources(monkeypatch):
    monkeypatch.setattr(
        "src.research.fixed_income._fetch_yield_curve",
        lambda: {"source": "curve", "as_of": "now", "stale": False, "error": None, "payload": {"curve": [], "signals": []}},
    )
    monkeypatch.setattr(
        "src.research.fixed_income._fetch_repo_rates",
        lambda: {"source": "repo", "as_of": "now", "stale": False, "error": None, "payload": {"metrics": []}},
    )
    monkeypatch.setattr(
        "src.research.fixed_income._fetch_bond_funds",
        lambda limit: {"source": "bond", "as_of": "now", "stale": False, "error": None, "payload": [{"id": "fund:1"}]},
    )
    monkeypatch.setattr(
        "src.research.fixed_income._fetch_money_funds",
        lambda limit: {"source": "money", "as_of": "now", "stale": False, "error": None, "payload": [{"id": "money:1"}]},
    )
    dashboard = build_fixed_income_dashboard(max_products_per_category=2)
    assert [item["id"] for item in dashboard["products"]] == ["fund:1", "money:1"]
    assert len(dashboard["market_snapshot"]["source_status"]) == 4
