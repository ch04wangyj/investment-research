"""Fixed-income research framework and local-first market product directory."""

from __future__ import annotations

import math
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError, as_completed
from datetime import date, datetime, timedelta
from typing import Any, Callable

from loguru import logger

from src.data.cache import get_cache

TENORS = ["3月", "6月", "1年", "3年", "5年", "7年", "10年", "30年"]
LIVE_QUERY_TIMEOUT_SECONDS = 16

REFERENCE_NOTE = {
    "title": "华泰固收分析框架合集2025版",
    "local_reference": True,
    "usage": "提炼为系统自有分析框架；不复制原文，不替代持牌机构产品适当性评估。",
}

FIXED_INCOME_AGENT_ROLES = [
    {
        "id": "fixed-income-planner",
        "name": "固收问题规划员",
        "mission": "把总问题拆成宏观、政策、曲线、供需、信用、产品六组可核验问题。",
        "output": "3-5 个互斥维度、10-15 个原子问题、每个问题的数据需求。",
        "guardrail": "不得先写结论再选择证据；缺失数据必须显式标记。",
    },
    {
        "id": "macro-cycle-analyst",
        "name": "宏观周期研究员",
        "mission": "跟踪增长、通胀、地产、财政和外部环境，形成周期位置判断。",
        "output": "周期阶段、核心变量、历史可比区间、反证条件。",
        "guardrail": "宏观叙事至少绑定一个高频指标和一个历史比较锚。",
    },
    {
        "id": "liquidity-policy-analyst",
        "name": "政策与资金面研究员",
        "mission": "区分狭义流动性与广义信用，追踪政策利率、回购利率和信用传导。",
        "output": "政策取向、资金松紧、期限影响、未来观察窗口。",
        "guardrail": "政策新闻、实际操作与市场定价必须分开陈述。",
    },
    {
        "id": "rates-strategist",
        "name": "利率债研究员",
        "mission": "分析期限结构、久期赔率、骑乘收益和关键期限风险。",
        "output": "曲线形态、关键利差、久期建议区间、失效条件。",
        "guardrail": "禁止把单日利率变化外推成长期趋势。",
    },
    {
        "id": "credit-convertible-analyst",
        "name": "信用与转债研究员",
        "mission": "区分信用风险、信用利差和转债股债属性，识别产品暴露。",
        "output": "信用层级、利差观察、转债底部约束、风险清单。",
        "guardrail": "产品名称分类只能作为初筛，不能替代底层持仓穿透。",
    },
    {
        "id": "investor-behavior-analyst",
        "name": "机构行为研究员",
        "mission": "跟踪银行、理财、公募、保险、外资和交易盘的配置行为。",
        "output": "供需变化、拥挤度、季节性、潜在赎回压力。",
        "guardrail": "共识与仓位要区分；没有仓位证据时只输出观察项。",
    },
    {
        "id": "fixed-income-director",
        "name": "固收研究总监",
        "mission": "合并并复核章节，输出面向资产配置的固收研究摘要。",
        "output": "事实、推断、争议、风险提示、待验证问题五段式摘要。",
        "guardrail": "对冲突证据进行保留，不生成个性化产品买卖建议。",
    },
]

FRAMEWORK_SECTIONS = [
    {
        "id": "macro_cycle",
        "title": "宏观周期",
        "question": "增长、通胀、地产、财政和外部环境处于什么组合？",
        "signals": ["PMI 与高频开工", "通胀与价格链", "地产销售与融资", "财政发行与支出", "汇率与海外利率"],
        "agent": "macro-cycle-analyst",
        "interpretation": "决定长端利率的方向锚，并为信用和资产配置提供背景约束。",
    },
    {
        "id": "policy_liquidity",
        "title": "政策与资金面",
        "question": "央行操作、银行间资金与信用传导是否一致？",
        "signals": ["逆回购与政策利率", "FDR001 / FDR007", "DR007 偏离", "信贷与社融", "存款迁移"],
        "agent": "liquidity-policy-analyst",
        "interpretation": "区分短端流动性扰动和中期宽信用变化，避免把资金面噪声误判为趋势。",
    },
    {
        "id": "yield_curve",
        "title": "收益率曲线",
        "question": "曲线形态、期限利差和信用利差反映了哪些预期差？",
        "signals": ["国债 10Y-1Y", "国债 10Y-3Y", "AAA 中票-国债利差", "骑乘空间", "久期拥挤度"],
        "agent": "rates-strategist",
        "interpretation": "把方向、久期和曲线策略拆开评估，不用单一收益率替代全部判断。",
    },
    {
        "id": "supply_demand",
        "title": "供需与机构行为",
        "question": "债券供给、机构配置和产品申赎如何影响定价？",
        "signals": ["政府债发行", "银行配置盘", "保险季节性", "理财与债基申赎", "ETF 产品化"],
        "agent": "investor-behavior-analyst",
        "interpretation": "识别基本面之外的定价力量，特别关注产品扩容和赎回反馈。",
    },
    {
        "id": "credit_convertible",
        "title": "信用与转债",
        "question": "信用层级、行业风险和转债股债属性是否匹配组合承受力？",
        "signals": ["信用利差", "评级迁移", "行业景气", "转债平价", "纯债底与赎回条款"],
        "agent": "credit-convertible-analyst",
        "interpretation": "信用债强调风险识别，转债强调股债联动和底部约束，两者不能混用评分。",
    },
    {
        "id": "allocation_products",
        "title": "配置与产品",
        "question": "产品风险预算、流动性和底层暴露是否与配置目标一致？",
        "signals": ["回撤预算", "权益上限", "久期暴露", "信用暴露", "申赎与流动性"],
        "agent": "fixed-income-director",
        "interpretation": "产品目录用于研究初筛；最终决策仍需穿透持仓、费率、适当性和最新披露。",
    },
]

ALLOCATION_PROFILES = [
    {
        "id": "cash_management",
        "title": "现金管理",
        "risk_level": "低",
        "equity_cap_pct": 0,
        "drawdown_guardrail_pct": 0.5,
        "focus": "流动性优先，关注货币基金、短债与同业存单类工具。",
    },
    {
        "id": "steady_income",
        "title": "稳健固收",
        "risk_level": "中低",
        "equity_cap_pct": 15,
        "drawdown_guardrail_pct": 2,
        "focus": "以固收为底仓，可观察低权益暴露的固收增强产品。",
    },
    {
        "id": "balanced_income",
        "title": "均衡增强",
        "risk_level": "中",
        "equity_cap_pct": 25,
        "drawdown_guardrail_pct": 3.5,
        "focus": "强调多资产分散、回撤控制与风险预算，不追求单一收益目标。",
    },
    {
        "id": "multi_asset",
        "title": "多资产配置",
        "risk_level": "中高",
        "equity_cap_pct": 40,
        "drawdown_guardrail_pct": 5,
        "focus": "组合可包含权益、黄金、商品、REITs 和海外资产，需要完整适当性判断。",
    },
]

PRODUCT_CATEGORIES = [
    {
        "id": "money_market",
        "title": "货币基金",
        "risk_level": "低",
        "liquidity": "高",
        "focus": "万份收益、7 日年化、规模稳定性和赎回规则。",
        "warning": "7 日年化是短期观察值，不代表未来收益。",
    },
    {
        "id": "pure_bond_short",
        "title": "短债基金",
        "risk_level": "中低",
        "liquidity": "中高",
        "focus": "久期、信用下沉、回撤、费率与申赎成本。",
        "warning": "净值仍会波动，短债不等于保本。",
    },
    {
        "id": "pure_bond_medium_long",
        "title": "中长期纯债",
        "risk_level": "中低",
        "liquidity": "中",
        "focus": "久期暴露、利率敏感度、信用分布与历史回撤。",
        "warning": "利率快速上行时，长久期产品回撤会放大。",
    },
    {
        "id": "bond_index",
        "title": "债券指数与 ETF",
        "risk_level": "中低",
        "liquidity": "中",
        "focus": "跟踪指数、久期、成交活跃度、折溢价和产品规模。",
        "warning": "工具属性较强，交易前需要检查流动性与折溢价。",
    },
    {
        "id": "fixed_income_plus",
        "title": "固收增强",
        "risk_level": "中",
        "liquidity": "中",
        "focus": "权益、转债、信用和衍生品暴露，重点看最大回撤。",
        "warning": "必须穿透底层仓位；名称不能代表实际风险。",
    },
    {
        "id": "convertible_bond",
        "title": "可转债基金",
        "risk_level": "中高",
        "liquidity": "中",
        "focus": "平价、溢价率、权益 Beta、信用事件与条款风险。",
        "warning": "同时受权益与债券风险影响，不应视为普通纯债替代。",
    },
    {
        "id": "fof_multi_asset",
        "title": "多资产 FOF / 理财",
        "risk_level": "按产品",
        "liquidity": "按产品",
        "focus": "风险预算、底层资产、费率嵌套、开放周期和适当性。",
        "warning": "公开排行不足以完成判断，应以最新产品说明书和持仓披露为准。",
    },
]


def fixed_income_framework() -> dict[str, Any]:
    """Return the system-owned fixed-income research framework."""

    return {
        "generated_at": datetime.now().isoformat(),
        "reference": REFERENCE_NOTE,
        "positioning": "研究优先的固收与理财产品工作台：先拆问题、验来源、识别风险，再讨论配置。",
        "framework_sections": FRAMEWORK_SECTIONS,
        "agents": FIXED_INCOME_AGENT_ROLES,
        "allocation_profiles": ALLOCATION_PROFILES,
        "product_categories": PRODUCT_CATEGORIES,
        "research_protocol": [
            "先回答总问题，再拆成可核验的原子问题。",
            "事实、推断和争议分开记录；保留冲突证据。",
            "利率债、信用债、转债和理财产品使用不同评分逻辑。",
            "产品排行只用于目录初筛，结论必须回到最新披露和风险适当性。",
        ],
    }


def build_fixed_income_dashboard(max_products_per_category: int = 8) -> dict[str, Any]:
    """Build a fixed-income dashboard with cached live data and graceful degradation."""

    limit = max(1, min(max_products_per_category, 20))
    jobs: dict[str, Callable[[], dict[str, Any]]] = {
        "yield_curve": _fetch_yield_curve,
        "repo_rates": _fetch_repo_rates,
        "bond_funds": lambda: _fetch_bond_funds(limit),
        "money_funds": lambda: _fetch_money_funds(limit),
    }
    live = _run_parallel(jobs)
    yield_payload = live["yield_curve"].get("payload") or {}
    repo_payload = live["repo_rates"].get("payload") or {}
    framework = fixed_income_framework()
    return {
        **framework,
        "market_snapshot": {
            "yield_curve": yield_payload.get("curve", []),
            "curve_signals": yield_payload.get("signals", []),
            "liquidity": repo_payload.get("metrics", []),
            "source_status": [
                {key: value for key, value in item.items() if key != "payload"}
                for item in live.values()
            ],
        },
        "products": [
            *(live["bond_funds"].get("payload") or []),
            *(live["money_funds"].get("payload") or []),
        ],
        "disclaimer": "本模块用于公开信息研究、产品目录初筛和风险教育，不构成投资建议、收益承诺或适当性意见。",
    }


def _run_parallel(jobs: dict[str, Callable[[], dict[str, Any]]]) -> dict[str, dict[str, Any]]:
    results: dict[str, dict[str, Any]] = {}
    executor = ThreadPoolExecutor(max_workers=len(jobs))
    future_map = {executor.submit(job): key for key, job in jobs.items()}
    try:
        for future in as_completed(future_map, timeout=LIVE_QUERY_TIMEOUT_SECONDS):
            key = future_map[future]
            try:
                results[key] = future.result()
            except Exception as exc:
                logger.warning(f"Fixed-income source {key} failed: {exc}")
                results[key] = _source_result(key, None, error=str(exc))
    except FuturesTimeoutError:
        logger.warning("Fixed-income dashboard reached live source timeout")
    finally:
        executor.shutdown(wait=False, cancel_futures=True)

    for key in jobs:
        results.setdefault(key, _source_result(key, None, error="live source timeout"))
    return results


def _fetch_yield_curve() -> dict[str, Any]:
    def loader() -> dict[str, Any]:
        import akshare as ak

        end_date = date.today()
        start_date = end_date - timedelta(days=18)
        frame = ak.bond_china_yield(
            start_date=start_date.strftime("%Y%m%d"),
            end_date=end_date.strftime("%Y%m%d"),
        )
        return _normalize_yield_curve(frame)

    return _cached_source("chinabond_yield_curve", "中债收益率曲线", loader, ttl_seconds=3600)


def _fetch_repo_rates() -> dict[str, Any]:
    def loader() -> dict[str, Any]:
        import akshare as ak

        end_date = date.today()
        start_date = end_date - timedelta(days=18)
        frame = ak.repo_rate_hist(
            start_date=start_date.strftime("%Y%m%d"),
            end_date=end_date.strftime("%Y%m%d"),
        )
        return _normalize_repo_rates(frame)

    return _cached_source("interbank_repo_rates", "中国货币网银行间回购定盘利率", loader, ttl_seconds=900)


def _fetch_bond_funds(limit: int) -> dict[str, Any]:
    def loader() -> list[dict[str, Any]]:
        import akshare as ak

        frame = ak.fund_open_fund_rank_em(symbol="债券型")
        return _normalize_bond_funds(frame, limit)

    return _cached_source(f"eastmoney_bond_funds:{limit}", "东方财富债券型基金排行", loader, ttl_seconds=3600)


def _fetch_money_funds(limit: int) -> dict[str, Any]:
    def loader() -> list[dict[str, Any]]:
        import akshare as ak

        frame = ak.fund_money_rank_em()
        return _normalize_money_funds(frame, limit)

    return _cached_source(f"eastmoney_money_funds:{limit}", "东方财富货币基金排行", loader, ttl_seconds=3600)


def _cached_source(
    key: str,
    source: str,
    loader: Callable[[], Any],
    *,
    ttl_seconds: int,
) -> dict[str, Any]:
    cache = get_cache()
    cache_key = f"fixed_income:v1:{key}"
    stale_payload = cache.get_stale(cache_key)
    payload = cache.get(cache_key)
    if payload is not None:
        return _source_result(source, payload)
    try:
        payload = loader()
        cache.set(cache_key, payload, ttl_seconds=ttl_seconds)
        return _source_result(source, payload)
    except Exception as exc:
        logger.warning(f"Fixed-income source {source} failed: {exc}")
        if stale_payload is not None:
            return _source_result(source, stale_payload, stale=True, error=str(exc))
        return _source_result(source, None, error=str(exc))


def _source_result(source: str, payload: Any, *, stale: bool = False, error: str | None = None) -> dict[str, Any]:
    return {
        "source": source,
        "as_of": datetime.now().isoformat(),
        "stale": stale,
        "error": error,
        "payload": payload,
    }


def _normalize_yield_curve(frame: Any) -> dict[str, Any]:
    rows = _records(frame)
    if not rows:
        return {"curve": [], "signals": []}
    date_key = _find_key(rows[0], "日期", "date")
    curve_key = _find_key(rows[0], "曲线名称", "曲线", "curve")
    latest_date = max(str(row.get(date_key, "")) for row in rows)
    latest = [row for row in rows if str(row.get(date_key, "")) == latest_date]
    treasury = next(
        (row for row in latest if "国债收益率曲线" in str(row.get(curve_key, ""))),
        {},
    )
    aaa_note = next(
        (
            row
            for row in latest
            if "中短期票据" in str(row.get(curve_key, "")) and "AAA" in str(row.get(curve_key, ""))
        ),
        {},
    )
    curve = []
    for tenor in TENORS:
        treasury_yield = _number(treasury.get(tenor))
        aaa_yield = _number(aaa_note.get(tenor))
        curve.append({
            "tenor": tenor,
            "treasury_yield": treasury_yield,
            "aaa_note_yield": aaa_yield,
            "credit_spread_bp": _spread_bp(aaa_yield, treasury_yield),
            "as_of": latest_date,
        })
    treasury_by_tenor = {item["tenor"]: item["treasury_yield"] for item in curve}
    aaa_by_tenor = {item["tenor"]: item["aaa_note_yield"] for item in curve}
    return {
        "curve": curve,
        "signals": [
            _signal("国债 10Y-1Y", _spread_bp(treasury_by_tenor.get("10年"), treasury_by_tenor.get("1年")), "bp", latest_date),
            _signal("国债 10Y-3Y", _spread_bp(treasury_by_tenor.get("10年"), treasury_by_tenor.get("3年")), "bp", latest_date),
            _signal("AAA 中票 3Y-国债 3Y", _spread_bp(aaa_by_tenor.get("3年"), treasury_by_tenor.get("3年")), "bp", latest_date),
        ],
    }


def _normalize_repo_rates(frame: Any) -> dict[str, Any]:
    rows = _records(frame)
    if not rows:
        return {"metrics": []}
    row = rows[-1]
    as_of = str(row.get("date") or row.get("日期") or "")
    return {
        "metrics": [
            _signal("FDR001", _number(row.get("FDR001")), "%", as_of),
            _signal("FDR007", _number(row.get("FDR007")), "%", as_of),
            _signal("FR007", _number(row.get("FR007")), "%", as_of),
        ],
    }


def _normalize_bond_funds(frame: Any, limit: int) -> list[dict[str, Any]]:
    products = []
    for row in _records(frame):
        name = str(row.get("基金简称") or "").strip()
        code = str(row.get("基金代码") or "").strip()
        if not code or not name:
            continue
        category = _bond_fund_category(name)
        products.append({
            "id": f"fund:{code}",
            "code": code,
            "name": name,
            "category": category,
            "category_title": _category_title(category),
            "risk_level": _fund_risk_level(category),
            "rank": _integer(row.get("序号")),
            "as_of": str(row.get("日期") or ""),
            "nav": _number(row.get("单位净值")),
            "daily_return_pct": _number(row.get("日增长率")),
            "return_1m_pct": _number(row.get("近1月")),
            "return_6m_pct": _number(row.get("近6月")),
            "return_1y_pct": _number(row.get("近1年")),
            "ytd_return_pct": _number(row.get("今年来")),
            "fee": str(row.get("手续费") or ""),
            "source": "东方财富债券型基金排行",
            "note": "公开排行初筛；需继续核验持仓、久期、信用暴露、回撤和最新基金公告。",
        })
        if len(products) >= limit:
            break
    return products


def _normalize_money_funds(frame: Any, limit: int) -> list[dict[str, Any]]:
    products = []
    for row in _records(frame):
        name = str(row.get("基金简称") or "").strip()
        code = str(row.get("基金代码") or "").strip()
        if not code or not name:
            continue
        products.append({
            "id": f"money:{code}",
            "code": code,
            "name": name,
            "category": "money_market",
            "category_title": _category_title("money_market"),
            "risk_level": "低",
            "rank": _integer(row.get("序号")),
            "as_of": str(row.get("日期") or ""),
            "income_per_10k": _number(row.get("万份收益")),
            "annualized_7d_pct": _number(row.get("年化收益率7日")),
            "annualized_14d_pct": _number(row.get("年化收益率14日")),
            "return_1m_pct": _number(row.get("近1月")),
            "return_1y_pct": _number(row.get("近1年")),
            "source": "东方财富货币基金排行",
            "note": "公开排行初筛；7 日年化会变动，需核验赎回规则、规模和最新公告。",
        })
        if len(products) >= limit:
            break
    return products


def _records(frame: Any) -> list[dict[str, Any]]:
    if frame is None or not hasattr(frame, "to_dict"):
        return []
    repaired = frame.copy()
    repaired.columns = [_repair_text(str(column)) for column in repaired.columns]
    for column in repaired.columns:
        if str(repaired[column].dtype) == "object":
            repaired[column] = repaired[column].map(_repair_text)
    return repaired.to_dict(orient="records")


def _repair_text(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    for encoding in ("latin1", "cp1252"):
        try:
            repaired = value.encode(encoding).decode("utf-8")
            if repaired != value:
                return repaired
        except (UnicodeEncodeError, UnicodeDecodeError):
            continue
    return value


def _find_key(row: dict[str, Any], *candidates: str) -> str:
    for candidate in candidates:
        if candidate in row:
            return candidate
    for key in row:
        if any(candidate.lower() in key.lower() for candidate in candidates):
            return key
    return candidates[0]


def _signal(name: str, value: float | None, unit: str, as_of: str) -> dict[str, Any]:
    return {"name": name, "value": value, "unit": unit, "as_of": as_of}


def _spread_bp(left: float | None, right: float | None) -> float | None:
    if left is None or right is None:
        return None
    return round((left - right) * 100, 2)


def _number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        result = float(value)
        return result if math.isfinite(result) else None
    normalized = str(value).replace(",", "").replace("%", "").strip()
    if normalized in {"", "-", "--", "None", "nan"}:
        return None
    try:
        result = float(normalized)
        return result if math.isfinite(result) else None
    except ValueError:
        return None


def _integer(value: Any) -> int | None:
    number = _number(value)
    return int(number) if number is not None else None


def _bond_fund_category(name: str) -> str:
    if "转债" in name or "可转债" in name:
        return "convertible_bond"
    if "短债" in name or "超短债" in name:
        return "pure_bond_short"
    if "指数" in name or "ETF" in name.upper():
        return "bond_index"
    if "增强" in name or "二级" in name or "混合" in name:
        return "fixed_income_plus"
    return "pure_bond_medium_long"


def _fund_risk_level(category: str) -> str:
    return {
        "convertible_bond": "中高",
        "fixed_income_plus": "中",
        "money_market": "低",
    }.get(category, "中低")


def _category_title(category: str) -> str:
    match = next((item for item in PRODUCT_CATEGORIES if item["id"] == category), None)
    return str(match["title"]) if match else category
