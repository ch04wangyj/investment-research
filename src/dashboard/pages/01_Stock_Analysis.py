"""Stock Analysis Page — Deep single-stock research with AI agent.

Supports URL query param: /01_Stock_Analysis?ticker=AAPL
"""

import json
import uuid
from datetime import datetime

import plotly.graph_objects as go
import streamlit as st
from langchain_openai import ChatOpenAI

from src.agents.analysis.graph import (
    create_analysis_agent,
    extract_report,
    format_report_for_display,
)
from src.core.base_agent import run_agent_sync
from src.dashboard.components import (
    apply_custom_css,
    fmt_price,
    get_market_from_symbol,
    market_color,
    pct_html,
    rating_badge,
    render_sidebar,
    t,
)
from src.data.dal import get_dal
from src.storage.repository import AgentReportRepository

# ── Page Config ──
st.set_page_config(
    page_title=t("analysis.title"),
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded",
)

apply_custom_css()

# ── Sidebar ──
llm_config = render_sidebar()

st.sidebar.markdown("---")
st.sidebar.markdown("### 🔗 Navigation")
st.sidebar.page_link("app.py", label=t("nav.back_home"))
st.sidebar.page_link("pages/02_Agent_Reports.py", label=t("nav.agent_reports"))
st.sidebar.page_link("pages/03_Watchlist.py", label=t("nav.watchlist"))


# ── LLM Factory ──

def get_llm() -> ChatOpenAI:
    key = llm_config["api_key"]
    return ChatOpenAI(
        model=llm_config["model_name"],
        api_key=key,
        base_url=llm_config["api_base"],
        temperature=0.3,
        timeout=180,
        model_kwargs={"extra_body": {"thinking": {"type": "disabled"}}},
    )


# ── Helpers ──

def load_ticker_reports(ticker: str, limit: int = 5):
    """Load historical reports for a ticker."""
    repo = AgentReportRepository("./data/sqlite/operational.db")
    try:
        return repo.get_latest(ticker, limit=limit)
    except Exception:
        return []


def save_report(ticker: str, agent_name: str, report_data: dict, summary: str):
    """Save agent report to database."""
    try:
        repo = AgentReportRepository("./data/sqlite/operational.db")
        repo.save({
            "agent_name": agent_name,
            "run_id": str(uuid.uuid4()),
            "ticker": ticker,
            "report_type": "analysis_report",
            "content": {
                "summary": summary,
                "data": report_data,
            },
            "trigger_type": "manual",
        })
        return True
    except Exception as e:
        st.warning(f"Failed to save report: {e}")
        return False


def plot_price_chart(symbol: str):
    """Interactive OHLC candlestick chart."""
    dal = get_dal()
    df = dal.get_historical_df(symbol, "6mo")

    if df.empty:
        st.warning(f"No historical data available for {symbol}")
        return

    fig = go.Figure(data=[
        go.Candlestick(
            x=df["date"],
            open=df["open"],
            high=df["high"],
            low=df["low"],
            close=df["close"],
            name=symbol,
            increasing_line_color="#4caf50",
            decreasing_line_color="#f44336",
        )
    ])

    fig.add_trace(go.Bar(
        x=df["date"],
        y=df["volume"],
        name="Volume",
        yaxis="y2",
        marker_color="rgba(128,128,128,0.3)",
    ))

    fig.update_layout(
        title=t("analysis.chart.title").format(symbol=symbol),
        yaxis_title="Price",
        xaxis_title="Date",
        template="plotly_dark",
        height=500,
        yaxis2=dict(
            title="Volume",
            overlaying="y",
            side="right",
            showgrid=False,
        ),
        hovermode="x unified",
        margin=dict(l=20, r=20, t=50, b=20),
    )

    st.plotly_chart(fig, use_container_width=True)


# ── Main Page ──

qp_ticker = st.query_params.get("ticker", "")
session_ticker = st.session_state.pop("analysis_ticker", "")
initial_ticker = qp_ticker.upper() if qp_ticker else session_ticker

st.title(t("analysis.title"))

# ── Ticker input row ──
col1, col2, col3 = st.columns([3, 1, 1])
with col1:
    ticker = st.text_input(
        t("analysis.ticker_label"),
        value=initial_ticker,
        placeholder=t("analysis.ticker_placeholder"),
        help=t("analysis.ticker_help"),
        key="analysis_ticker",
    )
with col2:
    analyze_btn = st.button(t("analysis.analyze_btn"), type="primary", use_container_width=True)
with col3:
    show_chart_btn = st.button(t("analysis.chart_btn"), use_container_width=True)

st.markdown("---")

# ── Tabs ──

tab1, tab2, tab3 = st.tabs([
    t("analysis.tab.report"),
    t("analysis.tab.chart"),
    t("analysis.tab.fundamentals"),
])

# ── Tab 1: Analysis Report ──

with tab1:
    if analyze_btn and ticker.strip():
        ticker = ticker.strip().upper()
        st.query_params["ticker"] = ticker

        with st.spinner(f"Analyzing {ticker}... This may take 1-2 minutes."):
            try:
                llm = get_llm()
                agent = create_analysis_agent(llm)

                task = (
                    f"Analyze {ticker}. Fetch current quotes, 6-month historical data, "
                    f"fundamentals, and recent news. Provide a complete research report "
                    f"with a structured JSON summary at the end."
                )
                result = run_agent_sync(agent, task, metadata={"ticker": ticker})

                report = extract_report(result)
                if report and report.data:
                    data = report.data

                    # Key metrics row with market color
                    mkt = get_market_from_symbol(ticker)
                    m1, m2, m3, m4, m5 = st.columns(5)
                    with m1:
                        st.metric(t("analysis.report.rating"), data.get("rating", t("common.na")))
                    with m2:
                        st.metric(t("analysis.report.price"), fmt_price(data.get("current_price")))
                    with m3:
                        st.metric(t("analysis.report.target"), fmt_price(data.get("price_target_6mo")))
                    with m4:
                        pe = data.get("key_metrics", {}).get("pe_ratio", t("common.na"))
                        st.metric(t("analysis.report.pe"), f"{pe:.1f}" if isinstance(pe, (int, float)) else pe)
                    with m5:
                        st.metric(t("analysis.report.confidence"), data.get("confidence", t("common.na")).title())

                    st.markdown("---")

                    # Full report text
                    report_text = format_report_for_display(report)
                    st.markdown(report_text)

                    # Export button
                    export_md = f"# {data.get('company_name', ticker)} ({ticker}) Analysis Report\n\n"
                    export_md += report_text
                    st.download_button(
                        label=t("analysis.report.export"),
                        data=export_md,
                        file_name=f"{ticker}_analysis_{datetime.now().strftime('%Y%m%d')}.md",
                        mime="text/markdown",
                    )

                    # Save to DB
                    if save_report(ticker, "FinancialAnalyst", data, report.summary):
                        st.success(t("analysis.report.saved"))
                    else:
                        st.warning(t("analysis.report.not_saved"))

                else:
                    st.warning(t("analysis.report.raw_fallback"))
                    last_msg = result.get("messages", [])[-1] if result.get("messages") else None
                    if last_msg:
                        st.text(last_msg.content if hasattr(last_msg, "content") else str(last_msg))

            except Exception as e:
                st.error(t("analysis.error.failed").format(error=e))
                st.info(t("analysis.error.hints"))

    elif not analyze_btn and ticker.strip():
        st.info(t("analysis.hint.click").format(ticker=ticker.strip().upper()))

    elif not ticker.strip():
        st.info(t("analysis.hint.enter"))

    # ── Historical Reports for this ticker ──
    if ticker.strip():
        ticker = ticker.strip().upper()
        st.markdown("---")
        st.subheader(t("analysis.prev_reports").format(ticker=ticker))

        prev_reports = load_ticker_reports(ticker)
        if prev_reports:
            for pr in prev_reports:
                content = pr.content or {}
                data = content.get("data", {}) if isinstance(content, dict) else {}
                with st.expander(
                    f"{pr.created_at.strftime('%Y-%m-%d %H:%M') if pr.created_at else 'Unknown'} "
                    f"— Rating: {data.get('rating', t('common.na'))}"
                ):
                    st.markdown(
                        f"**Rating**: {rating_badge(data.get('rating', ''))}",
                        unsafe_allow_html=True,
                    )
                    st.markdown(
                        f"**Price**: {data.get('current_price', t('common.na'))} | "
                        f"**Target**: {data.get('price_target_6mo', t('common.na'))} | "
                        f"**Confidence**: {data.get('confidence', t('common.na'))}"
                    )
                    st.markdown(f"**Bull**: {data.get('bull_case', t('common.na'))}")
                    st.markdown(f"**Bear**: {data.get('bear_case', t('common.na'))}")
        else:
            st.caption(t("analysis.prev_reports.empty"))


# ── Tab 2: Price Chart ──

with tab2:
    if show_chart_btn and ticker.strip():
        ticker = ticker.strip().upper()
        with st.spinner(t("analysis.chart.loading").format(ticker=ticker)):
            plot_price_chart(ticker)
    elif ticker.strip():
        if st.button(t("analysis.chart.load_btn"), key="load_chart_tab2"):
            with st.spinner(t("analysis.chart.loading").format(ticker=ticker.strip().upper())):
                plot_price_chart(ticker.strip().upper())
    else:
        st.info(t("analysis.hint.enter"))


# ── Tab 3: Fundamentals ──

with tab3:
    if ticker.strip():
        ticker = ticker.strip().upper()
        st.subheader(t("analysis.fund.title").format(ticker=ticker))

        if st.button(t("analysis.fund.load_btn"), key="load_fund"):
            with st.spinner(t("analysis.fund.loading")):
                dal = get_dal()
                data = dal.get_fundamentals(ticker)

                if data and data.get("error") is None:
                    key_items = {}
                    other_items = {}
                    key_fields = {
                        "pe_ratio", "pb_ratio", "roe", "roa", "market_cap",
                        "revenue", "net_income", "debt_to_equity", "dividend_yield",
                        "current_price", "company_name", "sector", "industry",
                        "52w_high", "52w_low", "eps", "beta",
                    }

                    for k, v in data.items():
                        if k in ("error",):
                            continue
                        if k in key_fields:
                            key_items[k] = v
                        else:
                            other_items[k] = v

                    st.markdown(f"### {t('analysis.fund.key_metrics')}")
                    cols = st.columns(4)
                    for i, (k, v) in enumerate(key_items.items()):
                        col_idx = i % 4
                        label = k.replace("_", " ").title()
                        if isinstance(v, float):
                            disp = f"{v:,.2f}" if abs(v) > 1 else f"{v:.4f}"
                        else:
                            disp = str(v) if v is not None else t("common.na")
                        cols[col_idx].metric(label=label, value=disp)

                    if other_items:
                        st.markdown(f"### {t('analysis.fund.additional')}")
                        c1, c2 = st.columns(2)
                        items = list(other_items.items())
                        mid = len(items) // 2
                        for i, (k, v) in enumerate(items):
                            col = c1 if i < mid else c2
                            label = k.replace("_", " ").title()
                            disp_val = f"{v:,.2f}" if isinstance(v, (int, float)) and abs(v) > 1 else str(v)
                            col.metric(label=label, value=disp_val if v is not None else t("common.na"))
                else:
                    st.warning(t("analysis.fund.no_data").format(ticker=ticker))
                    st.info(t("analysis.fund.hint"))
    else:
        st.info(t("analysis.hint.enter"))
