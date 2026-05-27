"""AI Investment Research — Home Page / Market Overview.

Shows market indices, important news, watchlist quotes, and recent reports.
"""

from datetime import date

import pandas as pd
import streamlit as st

from src.dashboard.components import (
    apply_custom_css,
    fmt_market_cap,
    fmt_price,
    get_market_from_symbol,
    market_badge,
    market_color,
    pct_html,
    rating_badge,
    render_index_card,
    render_news_card,
    render_page_header,
    render_sidebar,
    t,
)
from src.data.dal import get_dal
from src.data.indices import fetch_all_indices
from src.data.news_fetcher import fetch_financial_news
from src.storage.repository import AgentReportRepository, TrackedSymbolRepository

# ── Page Config ──
st.set_page_config(
    page_title="AI Investment Research",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

apply_custom_css()

# ── Sidebar ──
llm_config = render_sidebar()

st.sidebar.markdown("---")
st.sidebar.caption(t("sidebar.footer"))
st.sidebar.caption(t("sidebar.data_hint"))


# ── Helpers ──

@st.cache_data(ttl=120, show_spinner=False)
def load_watchlist():
    """Load tracked symbols from DB."""
    repo = TrackedSymbolRepository("./data/sqlite/operational.db")
    return repo.get_active()


@st.cache_data(ttl=300, show_spinner=False)
def load_indices():
    """Load market indices (cached 5 min)."""
    return fetch_all_indices()


@st.cache_data(ttl=600, show_spinner=False)
def load_news():
    """Load financial news (cached 10 min)."""
    return fetch_financial_news(max_items=8)


@st.cache_data(ttl=120, show_spinner=False)
def load_recent_reports(limit: int = 5):
    """Load recent agent reports summary."""
    from sqlalchemy import create_engine, select
    from sqlalchemy.orm import Session
    from src.storage.models import AgentReport

    engine = create_engine(
        "sqlite:///./data/sqlite/operational.db",
        connect_args={"check_same_thread": False},
    )
    with Session(engine) as session:
        rows = session.execute(
            select(AgentReport)
            .order_by(AgentReport.created_at.desc())
            .limit(limit)
        ).scalars().all()
        return [
            {
                "id": r.id,
                "agent_name": r.agent_name,
                "ticker": r.ticker,
                "report_type": r.report_type,
                "created_at": r.created_at,
                "content": r.content,
            }
            for r in rows
        ]


def load_watchlist_quotes(symbols: list[str]) -> pd.DataFrame:
    """Fetch quotes for all tracked symbols."""
    dal = get_dal()
    rows = []
    for sym in symbols:
        try:
            q = dal.get_quotes(sym)
            if q and "error" not in q:
                fund = dal.get_fundamentals(sym)
                rows.append({
                    "Symbol": sym,
                    "Name": q.get("name", fund.get("company_name", sym)),
                    "Price": q.get("close", q.get("current_price")),
                    "Change %": q.get("change_pct", 0),
                    "PE": fund.get("pe_ratio"),
                    "Market Cap": fund.get("market_cap"),
                    "Exchange": fund.get("exchange", q.get("exchange", "")),
                })
        except Exception:
            rows.append({
                "Symbol": sym, "Name": sym, "Price": None,
                "Change %": 0, "PE": None, "Market Cap": None, "Exchange": "",
            })
    return pd.DataFrame(rows)


# ── Main Page ──

render_page_header(
    t("home.title"),
    t("home.subtitle"),
)

# ===================================================================
# SECTION 1: KPI Cards
# ===================================================================

watchlist = load_watchlist()
reports = load_recent_reports(5)

k1, k2, k3, k4 = st.columns(4)

with k1:
    st.metric(t("home.kpi.tracked"), len(watchlist) if watchlist else 0)
with k2:
    today_count = sum(
        1 for r in reports
        if r["created_at"] and r["created_at"].date() == date.today()
    )
    st.metric(t("home.kpi.today_reports"), today_count)
with k3:
    last_date = (
        reports[0]["created_at"].strftime("%m/%d %H:%M")
        if reports else t("common.none")
    )
    st.metric(t("home.kpi.last_analysis"), last_date)
with k4:
    st.metric(t("home.kpi.recent_7d"), min(len(reports), 99))

st.markdown("---")

# ===================================================================
# SECTION 2: Market Indices (NEW)
# ===================================================================

st.subheader(t("home.indices.title"))

indices = load_indices()

if indices:
    # Separate by market for organized display
    ashare_idx = [i for i in indices if i.get("market") == "ashare"]
    hk_idx = [i for i in indices if i.get("market") == "hk"]
    us_idx = [i for i in indices if i.get("market") == "us"]

    # Row 1: A-share indices (5 cards)
    cols = st.columns(5)
    for i, idx in enumerate(ashare_idx):
        with cols[i]:
            st.markdown(render_index_card(idx), unsafe_allow_html=True)

    # Row 2: US + HK indices (3 + 3 cards)
    all_global = us_idx + hk_idx
    cols = st.columns(len(all_global))
    for i, idx in enumerate(all_global):
        with cols[i]:
            st.markdown(render_index_card(idx), unsafe_allow_html=True)
else:
    st.info(t("home.indices.error"))

st.markdown("---")

# ===================================================================
# SECTION 3: Important News & Policy (NEW)
# ===================================================================

st.subheader(t("home.news.title"))

news_items = load_news()

if news_items:
    # Render news as timeline
    news_html = '<div class="news-list">'
    for item in news_items:
        news_html += render_news_card(item)
    news_html += "</div>"
    st.markdown(news_html, unsafe_allow_html=True)
    st.caption(t("home.news.source"))
elif news_items is not None and len(news_items) == 0:
    st.info(t("home.news.empty"))
else:
    st.info(t("home.news.error"))

st.markdown("---")

# ===================================================================
# SECTION 4: Quick Analysis
# ===================================================================

col_input, col_btn = st.columns([4, 1])
with col_input:
    quick_ticker = st.text_input(
        t("home.quick_analysis"),
        placeholder=t("home.quick_placeholder"),
        key="home_ticker",
        label_visibility="collapsed",
    )
with col_btn:
    if st.button(t("home.quick_btn"), type="primary", use_container_width=True):
        if quick_ticker.strip():
            st.session_state.analysis_ticker = quick_ticker.strip().upper()
            st.switch_page("pages/01_Stock_Analysis.py")
        else:
            st.warning(t("home.quick_warning"))

# ===================================================================
# SECTION 5: Watchlist Table (with market colors)
# ===================================================================

st.subheader(t("home.watchlist.title"))

if watchlist:
    symbols = [s.symbol for s in watchlist]
    df_quotes = load_watchlist_quotes(symbols)

    if not df_quotes.empty:
        headers = [
            t("table.symbol"), t("table.name"), t("table.price"),
            t("table.change"), t("table.pe"), t("table.mkt_cap"),
            t("table.exchange"),
        ]
        table_rows = []
        for _, row in df_quotes.iterrows():
            sym = row.get("Symbol", "")
            mkt = get_market_from_symbol(str(sym))
            col = market_color(mkt)

            cells = []
            for col_key in headers:
                val = row.get(col_key)
                if col_key == t("table.price"):
                    cells.append(f"<td>{fmt_price(val)}</td>")
                elif col_key == t("table.change"):
                    cells.append(f"<td>{pct_html(val)}</td>")
                elif col_key == t("table.pe"):
                    cells.append(
                        f"<td>{val:.1f if val and isinstance(val, (int, float)) else t('common.na')}</td>"
                    )
                elif col_key == t("table.mkt_cap"):
                    cells.append(f"<td>{fmt_market_cap(val)}</td>")
                elif col_key == t("table.symbol"):
                    badge = market_badge(mkt)
                    cells.append(
                        f'<td style="border-left:3px solid {col}; padding-left:10px;">'
                        f'<a href="/01_Stock_Analysis?ticker={sym}" '
                        f'style="color:{col};font-weight:600;text-decoration:none;">'
                        f'{badge} {sym}</a></td>'
                    )
                elif col_key == t("table.exchange"):
                    cells.append(f"<td>{market_badge(mkt)}</td>")
                else:
                    cells.append(f"<td>{str(val) if val else ''}</td>")
            table_rows.append("<tr>" + "".join(cells) + "</tr>")

        html_table = f"""
        <table style="width:100%;border-collapse:collapse;font-size:0.9rem;">
        <thead>
            <tr style="background:#1a1c23;border-bottom:2px solid #30363d;">
                {''.join(f'<th style="padding:10px 14px;text-align:left;color:#8b949e;">{h}</th>' for h in headers)}
            </tr>
        </thead>
        <tbody>
            {''.join(table_rows)}
        </tbody>
        </table>
        """
        st.markdown(html_table, unsafe_allow_html=True)
    else:
        st.info(t("home.watchlist.no_data"))
else:
    st.info(t("home.watchlist.empty"))

st.markdown("---")

# ===================================================================
# SECTION 6: Recent Reports
# ===================================================================

st.subheader(t("home.reports.title"))

if reports:
    for r in reports[:5]:
        content = r.get("content") or {}
        data = content.get("data", {}) if isinstance(content, dict) else {}

        ticker = r["ticker"]
        mkt = get_market_from_symbol(ticker)

        with st.expander(
            f"{ticker} — {data.get('company_name', 'Company')}  |  "
            f"Rating: {data.get('rating', t('common.na'))}  |  "
            f"{r['created_at'].strftime('%Y-%m-%d %H:%M') if r['created_at'] else 'Unknown'}",
        ):
            c1, c2 = st.columns([2, 1])
            with c1:
                st.markdown(
                    f"**Rating**: {rating_badge(data.get('rating', ''))}",
                    unsafe_allow_html=True,
                )
                st.markdown(
                    f"**Price Target (6mo)**: {data.get('price_target_6mo', t('common.na'))}"
                )
                st.markdown(
                    f"**Current Price**: {data.get('current_price', t('common.na'))}"
                )
                st.markdown(
                    f"**Confidence**: {data.get('confidence', t('common.na'))}"
                )
            with c2:
                st.markdown("**Key Metrics**")
                metrics = data.get("key_metrics", {})
                for k, v in metrics.items():
                    label = k.replace("_", " ").title()
                    st.metric(label=label, value=v if v else t("common.na"))

            st.markdown("**Bull Case**: " + data.get("bull_case", t("common.na")))
            st.markdown("**Bear Case**: " + data.get("bear_case", t("common.na")))

            st.link_button(
                t("home.reports.view_full").format(ticker=ticker),
                url=f"/01_Stock_Analysis?ticker={ticker}",
                type="secondary",
            )
else:
    st.info(t("home.reports.empty"))
