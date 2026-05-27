"""i18n — Chinese/English translation system for the investment dashboard.

Usage:
    from src.dashboard.i18n import t

    label = t("home.title", lang="zh")  # -> "市场概览"
    label = t("home.title", lang="en")  # -> "Market Overview"

If `lang` is omitted, it reads `st.session_state.lang` (default "zh").
"""

from typing import Optional

import streamlit as st

LANGUAGES = {"zh": "中文", "en": "English"}

# ── Translation dictionary ──
TRANSLATIONS: dict[str, dict[str, str]] = {
    "zh": {
        # -- Sidebar --
        "sidebar.title": "📊 AI 投资研究",
        "sidebar.llm_settings": "⚙️ LLM 设置",
        "sidebar.api_key": "DeepSeek API Key",
        "sidebar.api_base": "API 地址",
        "sidebar.model": "模型",
        "sidebar.language": "🌐 语言",
        "sidebar.footer": "Phase 1.5 — 多页面仪表盘",
        "sidebar.data_hint": "数据: ./data/sqlite/operational.db",
        # -- Navigation --
        "nav.back_home": "← 返回市场概览",
        "nav.stock_analysis": "个股分析",
        "nav.agent_reports": "分析报告",
        "nav.watchlist": "自选股",
        # -- Home Page --
        "home.title": "市场概览",
        "home.subtitle": "追踪自选股、查看分析报告、研究新股。",
        "home.kpi.tracked": "自选股数量",
        "home.kpi.today_reports": "今日报告",
        "home.kpi.last_analysis": "最近分析",
        "home.kpi.recent_7d": "近7天报告",
        "home.quick_analysis": "快速分析",
        "home.quick_placeholder": "输入代码 (AAPL, 600519, TSLA...) 后点击分析",
        "home.quick_btn": "🚀 分析",
        "home.quick_warning": "请先输入股票代码",
        # -- Home: Indices --
        "home.indices.title": "📊 全球市场指数",
        "home.indices.loading": "正在加载指数数据...",
        "home.indices.error": "部分指数数据不可用",
        # -- Home: News --
        "home.news.title": "📰 重要新闻与政策",
        "home.news.loading": "正在加载新闻...",
        "home.news.empty": "暂无新闻数据",
        "home.news.error": "新闻加载失败，请检查网络连接",
        "home.news.source": "来源: 新浪财经",
        # -- Home: Watchlist --
        "home.watchlist.title": "📈 自选股",
        "home.watchlist.empty": "暂无自选股，请前往自选股页面添加。",
        "home.watchlist.no_data": "无法获取行情数据，请检查网络后刷新。",
        # -- Home: Reports --
        "home.reports.title": "📝 最近分析报告",
        "home.reports.empty": "暂无报告，请先从个股分析页面生成报告！",
        "home.reports.view_full": "查看完整 {ticker} 分析 →",
        # -- Stock Analysis --
        "analysis.title": "🔍 个股分析",
        "analysis.ticker_label": "股票代码",
        "analysis.ticker_placeholder": "输入代码: AAPL, 600519, TSLA, 000858...",
        "analysis.ticker_help": "A股: 6位数字 | 美股: 字母代码 | 港股: 5位数字",
        "analysis.analyze_btn": "🔍 分析",
        "analysis.chart_btn": "📈 图表",
        "analysis.tab.report": "📝 分析报告",
        "analysis.tab.chart": "📈 价格图表",
        "analysis.tab.fundamentals": "📊 基本面",
        "analysis.hint.enter": "👆 输入股票代码，点击 **分析** 开始。",
        "analysis.hint.click": "输入代码 **{ticker}** 后点击 **分析** 生成研究报告。",
        "analysis.report.rating": "评级",
        "analysis.report.price": "当前价格",
        "analysis.report.target": "6个月目标价",
        "analysis.report.pe": "市盈率",
        "analysis.report.confidence": "置信度",
        "analysis.report.export": "📥 导出报告 (Markdown)",
        "analysis.report.saved": "报告已保存到数据库。",
        "analysis.report.not_saved": "报告已显示但保存失败。",
        "analysis.report.raw_fallback": "无法提取结构化报告，显示原始输出：",
        "analysis.error.failed": "分析失败: {error}",
        "analysis.error.hints": "排查建议：\n1. 检查 API Key 是否有效\n2. 确认股票代码格式正确\n3. 检查网络连接\n4. A股请使用6位代码，如 600519",
        "analysis.prev_reports": "📚 历史报告: {ticker}",
        "analysis.prev_reports.empty": "该股票暂无历史报告。",
        "analysis.chart.title": "{symbol} — 6个月价格走势",
        "analysis.chart.loading": "正在加载 {ticker} 的图表...",
        "analysis.chart.load_btn": "加载图表",
        "analysis.fund.title": "基本面数据: {ticker}",
        "analysis.fund.load_btn": "加载基本面",
        "analysis.fund.loading": "正在获取基本面数据...",
        "analysis.fund.key_metrics": "关键指标",
        "analysis.fund.additional": "其他数据",
        "analysis.fund.no_data": "暂无 {ticker} 的基本面数据",
        "analysis.fund.hint": "A股基本面依赖 AKShare API。美股基本面依赖 Yahoo Finance。",
        # -- Agent Reports --
        "reports.title": "📝 分析报告",
        "reports.subtitle": "浏览 AI 生成的历史投资研究报告。",
        "reports.filter.ticker": "按代码筛选",
        "reports.filter.rating": "按评级筛选",
        "reports.filter.sort": "排序",
        "reports.sort.recent": "最新优先",
        "reports.sort.ticker": "代码 A-Z",
        "reports.sort.rating": "评级",
        "reports.found": "共找到 **{count}** 份报告",
        "reports.no_match": "没有匹配的报告。",
        "reports.none": "暂无报告，请先前往个股分析页面生成报告！",
        "reports.go_analysis": "前往个股分析 →",
        "reports.agent": "分析代理",
        "reports.trigger": "触发方式",
        "reports.run_id": "运行 ID",
        "reports.metrics": "关键指标",
        "reports.no_metrics": "无指标数据",
        "reports.thesis": "投资论点",
        "reports.bull_case": "看涨理由",
        "reports.bear_case": "看跌理由",
        "reports.catalysts": "催化剂",
        "reports.risks": "风险因素",
        "reports.analyze_again": "重新分析 {ticker} →",
        "reports.summary.title": "📊 报告汇总",
        "reports.summary.total": "总报告数",
        "reports.summary.buy": "买入评级",
        "reports.summary.hold": "持有评级",
        "reports.summary.sell": "卖出评级",
        "reports.chart.title": "评级分布",
        # -- Watchlist --
        "watchlist.title": "⭐ 自选股",
        "watchlist.subtitle": "管理您在全球市场的自选标的。",
        "watchlist.add_form": "添加标的",
        "watchlist.symbol": "代码",
        "watchlist.name": "名称 (选填)",
        "watchlist.exchange": "市场",
        "watchlist.sector": "行业",
        "watchlist.add_btn": "➕ 添加到自选",
        "watchlist.add_success": "已添加 {symbol} 到自选股！",
        "watchlist.add_failed": "添加失败: {error}",
        "watchlist.symbol_required": "请输入代码。",
        "watchlist.actions": "操作",
        "watchlist.refresh_btn": "🔄 刷新行情",
        "watchlist.empty": "您的自选股列表为空。请在上方添加标的。",
        "watchlist.suggestions": "快速添加建议",
        "watchlist.manage": "⚙️ 管理自选股",
        "watchlist.remove_btn": "移除",
        "watchlist.remove_success": "已移除 {symbol}",
        "watchlist.remove_failed": "移除失败: {error}",
        # -- Table headers --
        "table.symbol": "代码",
        "table.name": "名称",
        "table.price": "价格",
        "table.change": "涨跌幅",
        "table.pe": "市盈率",
        "table.mkt_cap": "市值",
        "table.exchange": "市场",
        # -- Market labels --
        "market.ashare": "A股",
        "market.us": "美股",
        "market.hk": "港股",
        "market.unknown": "未知",
        # -- Rating labels --
        "rating.buy": "买入",
        "rating.hold": "持有",
        "rating.sell": "卖出",
        # -- Index names --
        "index.sh000001": "上证指数",
        "index.sz399001": "深证成指",
        "index.sh000300": "沪深300",
        "index.sh000905": "中证500",
        "index.sh000688": "科创50",
        "index.int_hsi": "恒生指数",
        "index.int_hscei": "国企指数",
        "index.int_hstech": "恒生科技",
        "index.sp500": "标普500",
        "index.nasdaq": "纳斯达克",
        "index.dji": "道琼斯",
        # -- Common --
        "common.na": "N/A",
        "common.none": "无",
        "common.loading": "加载中...",
        "common.error": "出错了",
        "common.all": "全部",
        "common.filter": "筛选",
        "common.previous_close": "前收盘",
    },
    "en": {
        # -- Sidebar --
        "sidebar.title": "📊 AI Investment Research",
        "sidebar.llm_settings": "⚙️ LLM Settings",
        "sidebar.api_key": "DeepSeek API Key",
        "sidebar.api_base": "API Base URL",
        "sidebar.model": "Model",
        "sidebar.language": "🌐 Language",
        "sidebar.footer": "Phase 1.5 — Multi-Page Dashboard",
        "sidebar.data_hint": "Data: ./data/sqlite/operational.db",
        # -- Navigation --
        "nav.back_home": "← Back to Market Overview",
        "nav.stock_analysis": "Stock Analysis",
        "nav.agent_reports": "Agent Reports",
        "nav.watchlist": "Watchlist",
        # -- Home Page --
        "home.title": "Market Overview",
        "home.subtitle": "Track your watchlist, review analysis reports, and research new stocks.",
        "home.kpi.tracked": "Tracked Symbols",
        "home.kpi.today_reports": "Today's Reports",
        "home.kpi.last_analysis": "Last Analysis",
        "home.kpi.recent_7d": "Recent Reports (7d)",
        "home.quick_analysis": "Quick Analysis",
        "home.quick_placeholder": "Enter ticker (AAPL, 600519, TSLA...) and press Analyze",
        "home.quick_btn": "🚀 Analyze",
        "home.quick_warning": "Enter a ticker first",
        # -- Home: Indices --
        "home.indices.title": "📊 Global Market Indices",
        "home.indices.loading": "Loading index data...",
        "home.indices.error": "Some index data is unavailable",
        # -- Home: News --
        "home.news.title": "📰 Important News & Policy",
        "home.news.loading": "Loading news...",
        "home.news.empty": "No news available",
        "home.news.error": "Failed to load news, check your network",
        "home.news.source": "Source: Sina Finance",
        # -- Home: Watchlist --
        "home.watchlist.title": "📈 Watchlist",
        "home.watchlist.empty": "No tracked symbols. Go to the Watchlist page to add stocks.",
        "home.watchlist.no_data": "No quote data available. Try refreshing or check your internet connection.",
        # -- Home: Reports --
        "home.reports.title": "📝 Recent Analysis Reports",
        "home.reports.empty": "No reports yet. Run an analysis from the Stock Analysis page!",
        "home.reports.view_full": "View Full {ticker} Analysis →",
        # -- Stock Analysis --
        "analysis.title": "🔍 Stock Analysis",
        "analysis.ticker_label": "Stock Ticker",
        "analysis.ticker_placeholder": "Enter ticker: AAPL, 600519, TSLA, 000858...",
        "analysis.ticker_help": "A-shares: 6-digit code | US stocks: letter ticker | HK: 5-digit code",
        "analysis.analyze_btn": "🔍 Analyze",
        "analysis.chart_btn": "📈 Show Chart",
        "analysis.tab.report": "📝 Analysis Report",
        "analysis.tab.chart": "📈 Price Chart",
        "analysis.tab.fundamentals": "📊 Fundamentals",
        "analysis.hint.enter": "👆 Enter a stock ticker above and click **Analyze** to get started.",
        "analysis.hint.click": "Enter ticker **{ticker}** and click **Analyze** to generate a research report.",
        "analysis.report.rating": "Rating",
        "analysis.report.price": "Current Price",
        "analysis.report.target": "6mo Target",
        "analysis.report.pe": "PE Ratio",
        "analysis.report.confidence": "Confidence",
        "analysis.report.export": "📥 Export Report (Markdown)",
        "analysis.report.saved": "Report saved to database.",
        "analysis.report.not_saved": "Report displayed but not saved.",
        "analysis.report.raw_fallback": "Could not extract structured report. Showing raw output:",
        "analysis.error.failed": "Analysis failed: {error}",
        "analysis.error.hints": "Troubleshooting:\n1. Check your API key is valid\n2. Ensure the ticker format is correct\n3. Check internet connection for data APIs\n4. For A-shares, try a 6-digit code like 600519",
        "analysis.prev_reports": "📚 Previous Reports: {ticker}",
        "analysis.prev_reports.empty": "No previous reports for this ticker.",
        "analysis.chart.title": "{symbol} — 6 Month Price History",
        "analysis.chart.loading": "Loading chart for {ticker}...",
        "analysis.chart.load_btn": "Load Chart",
        "analysis.fund.title": "Fundamental Data: {ticker}",
        "analysis.fund.load_btn": "Load Fundamentals",
        "analysis.fund.loading": "Fetching fundamental data...",
        "analysis.fund.key_metrics": "Key Metrics",
        "analysis.fund.additional": "Additional Data",
        "analysis.fund.no_data": "No fundamental data available for {ticker}",
        "analysis.fund.hint": "A-share fundamentals depend on AKShare API availability. US stock fundamentals depend on Yahoo Finance.",
        # -- Agent Reports --
        "reports.title": "📝 Agent Reports",
        "reports.subtitle": "Browse historical AI-generated investment research reports.",
        "reports.filter.ticker": "Filter by Ticker",
        "reports.filter.rating": "Filter by Rating",
        "reports.filter.sort": "Sort by",
        "reports.sort.recent": "Most Recent",
        "reports.sort.ticker": "Ticker A-Z",
        "reports.sort.rating": "Rating",
        "reports.found": "**{count}** reports found",
        "reports.no_match": "No reports match your filters.",
        "reports.none": "No reports found. Run an analysis from the Stock Analysis page first!",
        "reports.go_analysis": "Go to Stock Analysis →",
        "reports.agent": "Agent",
        "reports.trigger": "Trigger",
        "reports.run_id": "Run ID",
        "reports.metrics": "Key Metrics",
        "reports.no_metrics": "No metrics available",
        "reports.thesis": "Thesis",
        "reports.bull_case": "Bull Case",
        "reports.bear_case": "Bear Case",
        "reports.catalysts": "Catalysts",
        "reports.risks": "Risks",
        "reports.analyze_again": "Analyze {ticker} Again →",
        "reports.summary.title": "📊 Report Summary",
        "reports.summary.total": "Total Reports",
        "reports.summary.buy": "BUY Ratings",
        "reports.summary.hold": "HOLD Ratings",
        "reports.summary.sell": "SELL Ratings",
        "reports.chart.title": "Rating Distribution",
        # -- Watchlist --
        "watchlist.title": "⭐ Watchlist",
        "watchlist.subtitle": "Manage your tracked stocks across global markets.",
        "watchlist.add_form": "Add Symbol",
        "watchlist.symbol": "Symbol",
        "watchlist.name": "Name (optional)",
        "watchlist.exchange": "Exchange",
        "watchlist.sector": "Sector",
        "watchlist.add_btn": "➕ Add to Watchlist",
        "watchlist.add_success": "Added {symbol} to watchlist!",
        "watchlist.add_failed": "Failed to add: {error}",
        "watchlist.symbol_required": "Symbol is required.",
        "watchlist.actions": "Actions",
        "watchlist.refresh_btn": "🔄 Refresh All Quotes",
        "watchlist.empty": "Your watchlist is empty. Add symbols above to get started.",
        "watchlist.suggestions": "Quick add suggestions",
        "watchlist.manage": "⚙️ Manage Watchlist",
        "watchlist.remove_btn": "Remove",
        "watchlist.remove_success": "Removed {symbol}",
        "watchlist.remove_failed": "Failed: {error}",
        # -- Table headers --
        "table.symbol": "Symbol",
        "table.name": "Name",
        "table.price": "Price",
        "table.change": "Change %",
        "table.pe": "PE",
        "table.mkt_cap": "Market Cap",
        "table.exchange": "Exchange",
        # -- Market labels --
        "market.ashare": "A-Share",
        "market.us": "US",
        "market.hk": "HK",
        "market.unknown": "Unknown",
        # -- Rating labels --
        "rating.buy": "BUY",
        "rating.hold": "HOLD",
        "rating.sell": "SELL",
        # -- Index names --
        "index.sh000001": "Shanghai Composite",
        "index.sz399001": "SZSE Component",
        "index.sh000300": "CSI 300",
        "index.sh000905": "CSI 500",
        "index.sh000688": "STAR 50",
        "index.int_hsi": "Hang Seng",
        "index.int_hscei": "HSCEI",
        "index.int_hstech": "Hang Seng TECH",
        "index.sp500": "S&P 500",
        "index.nasdaq": "NASDAQ",
        "index.dji": "Dow Jones",
        # -- Common --
        "common.na": "N/A",
        "common.none": "None",
        "common.loading": "Loading...",
        "common.error": "Error",
        "common.all": "All",
        "common.filter": "Filter",
        "common.previous_close": "Prev Close",
    },
}


def t(key: str, lang: Optional[str] = None) -> str:
    """Translate a key to the current language.

    Fallback chain: requested lang → zh → raw key.

    Args:
        key: Translation key, e.g. "home.title"
        lang: Language code ("zh" or "en"). If None, reads st.session_state.lang.

    Returns:
        Translated string.
    """
    if lang is None:
        try:
            lang = st.session_state.get("lang", "zh")
        except Exception:
            lang = "zh"

    if lang in TRANSLATIONS and key in TRANSLATIONS[lang]:
        return TRANSLATIONS[lang][key]
    if key in TRANSLATIONS.get("zh", {}):
        return TRANSLATIONS["zh"][key]
    return key
