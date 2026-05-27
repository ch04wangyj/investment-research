"""Agent Reports — Browse historical AI-generated analysis reports."""

import streamlit as st
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from src.dashboard.components import (
    apply_custom_css,
    fmt_price,
    get_market_from_symbol,
    market_badge,
    rating_badge,
    render_sidebar,
    t,
)
from src.storage.models import AgentReport

# ── Page Config ──
st.set_page_config(
    page_title=t("reports.title"),
    page_icon="📝",
    layout="wide",
    initial_sidebar_state="expanded",
)

apply_custom_css()

# ── Sidebar ──
llm_config = render_sidebar()

st.sidebar.markdown("---")
st.sidebar.markdown("### 🔗 Navigation")
st.sidebar.page_link("app.py", label=t("nav.back_home"))
st.sidebar.page_link("pages/01_Stock_Analysis.py", label=t("nav.stock_analysis"))
st.sidebar.page_link("pages/03_Watchlist.py", label=t("nav.watchlist"))


# ── Data Loading ──

def load_all_reports() -> list[dict]:
    """Load all reports from the database."""
    engine = create_engine(
        "sqlite:///./data/sqlite/operational.db",
        connect_args={"check_same_thread": False},
    )
    with Session(engine) as session:
        rows = session.execute(
            select(AgentReport)
            .order_by(AgentReport.created_at.desc())
        ).scalars().all()

        results = []
        for r in rows:
            content = r.content or {}
            data = content.get("data", {}) if isinstance(content, dict) else {}
            results.append({
                "id": r.id,
                "agent_name": r.agent_name,
                "run_id": r.run_id,
                "ticker": r.ticker,
                "report_type": r.report_type,
                "created_at": r.created_at,
                "trigger_type": r.trigger_type,
                "content": content,
                "data": data,
                "rating": data.get("rating", t("common.na")) if isinstance(data, dict) else t("common.na"),
                "company_name": data.get("company_name", "") if isinstance(data, dict) else "",
                "confidence": data.get("confidence", "") if isinstance(data, dict) else "",
                "current_price": data.get("current_price") if isinstance(data, dict) else None,
                "price_target": data.get("price_target_6mo") if isinstance(data, dict) else None,
            })
        return results


# ── Main Page ──

st.title(t("reports.title"))
st.markdown(t("reports.subtitle"))
st.markdown("---")

# Load data
with st.spinner(t("common.loading")):
    reports = load_all_reports()

if not reports:
    st.info(t("reports.none"))
    st.link_button(t("reports.go_analysis"), url="/01_Stock_Analysis")
else:
    # ── Filters ──
    filter_col1, filter_col2, filter_col3 = st.columns(3)

    with filter_col1:
        all_tickers = sorted(set(r["ticker"] for r in reports))
        filter_options = [t("common.all")] + all_tickers
        selected_ticker = st.selectbox(
            t("reports.filter.ticker"),
            filter_options,
            key="report_ticker_filter",
        )

    with filter_col2:
        all_ratings = sorted(set(r["rating"] for r in reports))
        rating_options = [t("common.all")] + all_ratings
        selected_rating = st.selectbox(
            t("reports.filter.rating"),
            rating_options,
            key="report_rating_filter",
        )

    with filter_col3:
        sort_options = [
            t("reports.sort.recent"),
            t("reports.sort.ticker"),
            t("reports.sort.rating"),
        ]
        sort_by = st.selectbox(
            t("reports.filter.sort"),
            sort_options,
            key="report_sort",
        )

    # Apply filters
    filtered = reports
    all_label = t("common.all")
    if selected_ticker != all_label:
        filtered = [r for r in filtered if r["ticker"] == selected_ticker]
    if selected_rating != all_label:
        filtered = [r for r in filtered if r["rating"] == selected_rating]

    if sort_by == t("reports.sort.ticker"):
        filtered = sorted(filtered, key=lambda r: r["ticker"])
    elif sort_by == t("reports.sort.rating"):
        rating_order = {"BUY": 0, "HOLD": 1, "SELL": 2}
        filtered = sorted(filtered, key=lambda r: rating_order.get(r["rating"].upper(), 99))

    st.markdown(t("reports.found").format(count=len(filtered)))
    st.markdown("---")

    # ── Report List ──
    if not filtered:
        st.info(t("reports.no_match"))
    else:
        for r in filtered:
            data = r["data"]
            ticker = r["ticker"]
            mkt = get_market_from_symbol(ticker)

            with st.expander(
                f"{market_badge(mkt)} **{ticker}** — {r.get('company_name', 'Company')}  |  "
                f"{rating_badge(r['rating'])}  |  "
                f"{r['created_at'].strftime('%Y-%m-%d %H:%M') if r['created_at'] else 'Unknown'}  |  "
                f"Confidence: {r['confidence'].title() if r['confidence'] else t('common.na')}",
                expanded=(len(filtered) == 1),
            ):
                col1, col2, col3 = st.columns([2, 1, 1])

                with col1:
                    st.markdown(f"**{t('reports.agent')}**: {r['agent_name']}")
                    st.markdown(f"**{t('reports.trigger')}**: {r['trigger_type']}")
                    st.markdown(f"**{t('reports.run_id')}**: `{r['run_id']}`")

                    st.markdown(f"#### {t('reports.metrics')}")
                    metrics = data.get("key_metrics", {})
                    if metrics:
                        m_cols = st.columns(min(len(metrics), 4))
                        for i, (k, v) in enumerate(metrics.items()):
                            label = k.replace("_", " ").title()
                            disp = f"{v:.1f}" if isinstance(v, float) else str(v)
                            m_cols[i % 4].metric(label=label, value=disp)
                    else:
                        st.caption(t("reports.no_metrics"))

                with col2:
                    st.markdown(f"#### {t('reports.thesis')}")
                    st.markdown(f"**Current Price**: {fmt_price(r['current_price'])}")
                    st.markdown(f"**Price Target**: {fmt_price(r['price_target'])}")
                    st.markdown(f"**{t('reports.bull_case')}**:")
                    st.caption(data.get("bull_case", t("common.na")))
                    st.markdown(f"**{t('reports.bear_case')}**:")
                    st.caption(data.get("bear_case", t("common.na")))

                with col3:
                    st.markdown(f"#### {t('reports.catalysts')} & {t('reports.risks')}")
                    st.markdown(f"**{t('reports.catalysts')}**:")
                    for c in data.get("key_catalysts", [])[:3]:
                        st.caption(f"• {c}")
                    st.markdown(f"**{t('reports.risks')}**:")
                    for risk in data.get("risk_factors", [])[:3]:
                        st.caption(f"• {risk}")

                st.link_button(
                    t("reports.analyze_again").format(ticker=ticker),
                    url=f"/01_Stock_Analysis?ticker={ticker}",
                    type="secondary",
                )

    # ── Summary Stats ──
    st.markdown("---")
    st.subheader(t("reports.summary.title"))

    s1, s2, s3, s4 = st.columns(4)
    with s1:
        st.metric(t("reports.summary.total"), len(reports))
    with s2:
        buy_count = sum(1 for r in reports if "BUY" in r["rating"].upper())
        st.metric(t("reports.summary.buy"), buy_count)
    with s3:
        hold_count = sum(1 for r in reports if "HOLD" in r["rating"].upper())
        st.metric(t("reports.summary.hold"), hold_count)
    with s4:
        sell_count = sum(1 for r in reports if "SELL" in r["rating"].upper())
        st.metric(t("reports.summary.sell"), sell_count)

    # Rating distribution chart
    import plotly.express as px

    rating_counts = {}
    for r in reports:
        rtg = r.get("rating", t("common.na"))
        rating_counts[rtg] = rating_counts.get(rtg, 0) + 1

    if rating_counts:
        fig = px.pie(
            values=list(rating_counts.values()),
            names=list(rating_counts.keys()),
            title=t("reports.chart.title"),
            color_discrete_sequence=["#4caf50", "#ff9800", "#f44336", "#8b949e"],
        )
        fig.update_layout(template="plotly_dark", height=300)
        st.plotly_chart(fig, use_container_width=True)
