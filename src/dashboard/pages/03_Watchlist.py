"""Watchlist Management — Manage tracked symbols and view quotes."""

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
    render_sidebar,
    t,
)
from src.data.dal import get_dal
from src.storage.repository import TrackedSymbolRepository

# ── Page Config ──
st.set_page_config(
    page_title=t("watchlist.title"),
    page_icon="⭐",
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
st.sidebar.page_link("pages/02_Agent_Reports.py", label=t("nav.agent_reports"))


# ── Helpers ──

def get_repo():
    return TrackedSymbolRepository("./data/sqlite/operational.db")


def load_watchlist():
    repo = get_repo()
    return repo.get_active()


def load_quotes_df(symbols: list[str]):
    """Batch fetch quotes for watchlist symbols."""
    dal = get_dal()
    rows = []
    for sym in symbols:
        try:
            q = dal.get_quotes(sym)
            fund = dal.get_fundamentals(sym)
            if q and "error" not in q:
                rows.append({
                    "symbol": sym,
                    "name": q.get("name", fund.get("company_name", sym)),
                    "price": q.get("close", q.get("current_price")),
                    "change_pct": q.get("change_pct"),
                    "volume": q.get("volume"),
                    "pe_ratio": fund.get("pe_ratio"),
                    "pb_ratio": fund.get("pb_ratio"),
                    "market_cap": fund.get("market_cap"),
                    "sector": fund.get("sector", ""),
                    "industry": fund.get("industry", ""),
                    "exchange": fund.get("exchange", q.get("exchange", "")),
                })
            else:
                rows.append({
                    "symbol": sym, "name": sym, "price": None, "change_pct": None,
                    "volume": None, "pe_ratio": None, "pb_ratio": None,
                    "market_cap": None, "sector": "", "industry": "",
                    "exchange": "",
                })
        except Exception:
            rows.append({
                "symbol": sym, "name": sym, "price": None, "change_pct": None,
                "volume": None, "pe_ratio": None, "pb_ratio": None,
                "market_cap": None, "sector": "", "industry": "",
                "exchange": "",
            })
    return pd.DataFrame(rows)


# ── Main Page ──

st.title(t("watchlist.title"))
st.markdown(t("watchlist.subtitle"))
st.markdown("---")

watchlist = load_watchlist()
repo = get_repo()

# ── Buttons row ──
c1, c2 = st.columns([1, 1])

with c1:
    with st.form("add_symbol_form", clear_on_submit=True):
        st.markdown(f"#### {t('watchlist.add_form')}")
        add_col1, add_col2, add_col3, add_col4 = st.columns([3, 2, 2, 1])
        with add_col1:
            new_symbol = st.text_input(
                t("watchlist.symbol"),
                placeholder="e.g., 00700, NVDA, 000858",
                key="new_sym",
            )
        with add_col2:
            new_name = st.text_input(
                t("watchlist.name"),
                placeholder="Company name",
                key="new_name",
            )
        with add_col3:
            new_exchange = st.selectbox(
                t("watchlist.exchange"),
                ["us", "ashare", "hk"],
                key="new_ex",
                format_func=lambda x: t(f"market.{x}"),
            )
        with add_col4:
            new_sector = st.text_input(
                t("watchlist.sector"),
                placeholder="e.g., Tech",
                key="new_sector",
            )
        if st.form_submit_button(t("watchlist.add_btn"), type="primary"):
            if new_symbol.strip():
                symbol_clean = new_symbol.strip().upper()
                try:
                    repo.add(
                        symbol=symbol_clean,
                        name=new_name.strip() or symbol_clean,
                        exchange=new_exchange,
                        sector=new_sector.strip(),
                    )
                    st.success(t("watchlist.add_success").format(symbol=symbol_clean))
                    st.cache_data.clear()
                    st.rerun()
                except Exception as e:
                    st.error(t("watchlist.add_failed").format(error=e))
            else:
                st.warning(t("watchlist.symbol_required"))

with c2:
    st.markdown(f"#### {t('watchlist.actions')}")
    if st.button(t("watchlist.refresh_btn"), use_container_width=True):
        st.cache_data.clear()
        st.rerun()

st.markdown("---")

# ── Watchlist Table ──

if not watchlist:
    st.info(t("watchlist.empty"))
    st.markdown(f"**{t('watchlist.suggestions')}**:")
    suggestions = [
        ("AAPL", "us", "Technology"),
        ("TSLA", "us", "Automotive"),
        ("600519", "ashare", "Consumer"),
        ("000858", "ashare", "Consumer"),
        ("00700", "hk", "Technology"),
        ("MSFT", "us", "Technology"),
    ]
    sc1, sc2, sc3 = st.columns(3)
    for i, (sym, ex, sec) in enumerate(suggestions):
        col = [sc1, sc2, sc3][i % 3]
        with col:
            if st.button(f"+ {sym} ({t(f'market.{ex}')})", key=f"suggest_{sym}"):
                repo.add(symbol=sym, name=sym, exchange=ex, sector=sec)
                st.cache_data.clear()
                st.rerun()
else:
    with st.spinner(t("common.loading")):
        symbols = [s.symbol for s in watchlist]
        df = load_quotes_df(symbols)

    wl_data = {s.symbol: s for s in watchlist}

    # Group by sector
    sectors = {}
    for _, row in df.iterrows():
        sector = row.get("sector") or wl_data.get(row["symbol"]).sector or "Other"
        if sector not in sectors:
            sectors[sector] = []
        sectors[sector].append(row)

    # Display by sector
    for sector_name, rows in sorted(sectors.items()):
        st.subheader(f"📂 {sector_name} ({len(rows)})")

        headers = [
            t("table.symbol"), t("table.name"), t("table.price"),
            t("table.change"), t("table.pe"), t("table.mkt_cap"),
            t("table.exchange"),
        ]
        table_rows = []
        for row in rows:
            sym = row["symbol"]
            mkt = get_market_from_symbol(str(sym))
            mkt_color = market_color(mkt)
            price_html = fmt_price(row["price"])
            pct = row["change_pct"]
            change_html = pct_html(pct)
            pe = (
                f"{row['pe_ratio']:.1f}"
                if row["pe_ratio"] and isinstance(row["pe_ratio"], (int, float))
                else t("common.na")
            )
            mcap = fmt_market_cap(row["market_cap"])
            badge = market_badge(mkt)

            table_rows.append(
                f'<tr>'
                f'<td style="border-left:3px solid {mkt_color}; padding-left:10px;">'
                f'<a href="/01_Stock_Analysis?ticker={sym}" '
                f'style="color:{mkt_color};font-weight:600;text-decoration:none;">'
                f'{badge} {sym}</a></td>'
                f'<td>{row.get("name", sym)}</td>'
                f'<td>{price_html}</td>'
                f'<td>{change_html}</td>'
                f'<td>{pe}</td>'
                f'<td>{mcap}</td>'
                f'<td>{badge}</td>'
                f'</tr>'
            )

        html = f"""
        <table style="width:100%;border-collapse:collapse;font-size:0.9rem;">
        <thead>
            <tr style="background:#1a1c23;border-bottom:2px solid #30363d;">
                {''.join(f'<th style="padding:8px 12px;text-align:left;color:#8b949e;">{h}</th>' for h in headers)}
            </tr>
        </thead>
        <tbody>
            {''.join(table_rows)}
        </tbody>
        </table>
        """
        st.markdown(html, unsafe_allow_html=True)
        st.markdown("")

    # ── Manage Watchlist ──
    st.markdown("---")
    st.subheader(t("watchlist.manage"))

    for s in watchlist:
        mc1, mc2, mc3 = st.columns([1, 3, 1])
        with mc1:
            mkt = get_market_from_symbol(s.symbol)
            st.markdown(f"{market_badge(mkt)} **{s.symbol}**", unsafe_allow_html=True)
        with mc2:
            st.write(f"{s.name} | {s.exchange} | {s.sector or 'No sector'}")
        with mc3:
            if st.button(t("watchlist.remove_btn"), key=f"remove_{s.symbol}"):
                try:
                    from sqlalchemy import create_engine, text
                    from sqlalchemy.orm import Session
                    engine = create_engine(
                        "sqlite:///./data/sqlite/operational.db",
                        connect_args={"check_same_thread": False},
                    )
                    with Session(engine) as session:
                        session.execute(
                            text("UPDATE tracked_symbols SET active=0 WHERE symbol=:sym"),
                            {"sym": s.symbol},
                        )
                        session.commit()
                    st.cache_data.clear()
                    st.success(t("watchlist.remove_success").format(symbol=s.symbol))
                    st.rerun()
                except Exception as e:
                    st.error(t("watchlist.remove_failed").format(error=e))
