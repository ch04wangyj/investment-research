"""Shared UI components for the multi-page dashboard.

Every page imports render_sidebar() for consistent LLM config + language selector,
and the formatting helpers for consistent data display.
"""

import os

import streamlit as st

from src.dashboard.i18n import LANGUAGES, t as i18n_t


# ── Helper: get current language ──

def _lang() -> str:
    """Get current language from session state, default zh."""
    try:
        return st.session_state.get("lang", "zh")
    except Exception:
        return "zh"


def t(key: str) -> str:
    """Translate a key using the current session language."""
    return i18n_t(key, _lang())


# ═══════════════════════════════════════════════════════════════
# CSS
# ═══════════════════════════════════════════════════════════════

def apply_custom_css():
    """Dark theme + market color system + professional styling."""
    st.markdown("""
    <style>
    /* ── Market Color System ── */
    :root {
        --market-ashare: #e74c3c;
        --market-ashare-bg: rgba(231, 76, 60, 0.10);
        --market-ashare-border: rgba(231, 76, 60, 0.30);
        --market-us: #2980b9;
        --market-us-bg: rgba(41, 128, 185, 0.10);
        --market-us-border: rgba(41, 128, 185, 0.30);
        --market-hk: #27ae60;
        --market-hk-bg: rgba(39, 174, 96, 0.10);
        --market-hk-border: rgba(39, 174, 96, 0.30);
        --rating-buy: #27ae60;
        --rating-hold: #f39c12;
        --rating-sell: #e74c3c;
        --card-bg: #1a1c23;
        --card-border: #2d3139;
        --text-primary: #e6edf3;
        --text-secondary: #8b949e;
        --accent-blue: #58a6ff;
    }

    /* Dark theme background */
    .stApp {
        background-color: #0e1117;
    }

    /* ── Metric cards ── */
    div[data-testid="stMetric"] {
        background-color: var(--card-bg);
        border: 1px solid var(--card-border);
        border-radius: 8px;
        padding: 12px;
    }
    div[data-testid="stMetric"] label {
        color: var(--text-secondary);
        font-size: 0.8rem;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }

    /* ── Dataframe / Table styling ── */
    div[data-testid="stDataFrame"] {
        border: 1px solid var(--card-border);
        border-radius: 8px;
    }

    /* ── Buttons ── */
    .stButton > button {
        border-radius: 6px;
        font-weight: 500;
    }

    /* ── Expander ── */
    .streamlit-expanderHeader {
        background-color: var(--card-bg);
        border-radius: 6px;
    }

    /* ── Sidebar ── */
    section[data-testid="stSidebar"] {
        background-color: #0d1117;
        border-right: 1px solid #2d3139;
    }

    /* ── Dividers ── */
    hr {
        border-color: #2d3139;
        margin: 0.5rem 0;
    }

    /* ── Positive / Negative ── */
    .positive { color: #4caf50; font-weight: 600; }
    .negative { color: #f44336; font-weight: 600; }
    .neutral { color: #8b949e; }

    /* ═══ Market Badges ═══ */
    .market-badge {
        display: inline-block;
        padding: 2px 8px;
        border-radius: 10px;
        font-size: 0.75rem;
        font-weight: 600;
        color: #fff;
    }
    .market-badge-ashare { background: var(--market-ashare); }
    .market-badge-us { background: var(--market-us); }
    .market-badge-hk { background: var(--market-hk); }

    /* ═══ Rating Badges (gradient enhanced) ═══ */
    .rating-badge {
        display: inline-block;
        padding: 2px 12px;
        border-radius: 12px;
        font-weight: 600;
        font-size: 0.85rem;
        color: #fff;
    }
    .rating-badge-buy  { background: linear-gradient(135deg, #27ae60, #2ecc71); }
    .rating-badge-hold { background: linear-gradient(135deg, #f39c12, #f1c40f); }
    .rating-badge-sell { background: linear-gradient(135deg, #e74c3c, #c0392b); }

    /* ═══ Index Cards ═══ */
    .index-card {
        background: var(--card-bg);
        border: 1px solid var(--card-border);
        border-radius: 8px;
        padding: 14px 16px;
        margin-bottom: 10px;
        transition: border-color 0.2s;
    }
    .index-card:hover { border-color: var(--accent-blue); }
    .index-card .idx-name {
        color: var(--text-secondary);
        font-size: 0.78rem;
        text-transform: uppercase;
        letter-spacing: 0.3px;
        margin-bottom: 4px;
    }
    .index-card .idx-price {
        font-size: 1.5rem;
        font-weight: 700;
        color: var(--text-primary);
    }
    .index-card .idx-change {
        font-weight: 600;
        font-size: 0.9rem;
        margin-top: 2px;
    }
    .index-card .idx-market-dot {
        display: inline-block;
        width: 8px;
        height: 8px;
        border-radius: 50%;
        margin-right: 6px;
    }
    .idx-dot-ashare { background: var(--market-ashare); }
    .idx-dot-us { background: var(--market-us); }
    .idx-dot-hk { background: var(--market-hk); }

    /* ═══ News Timeline ═══ */
    .news-list { }
    .news-item {
        display: flex;
        gap: 14px;
        padding: 10px 0;
        border-bottom: 1px solid rgba(45, 49, 57, 0.5);
    }
    .news-item:last-child { border-bottom: none; }
    .news-time {
        color: var(--text-secondary);
        font-size: 0.8rem;
        white-space: nowrap;
        min-width: 65px;
        padding-top: 2px;
    }
    .news-title {
        color: var(--accent-blue);
        font-weight: 500;
        text-decoration: none;
        line-height: 1.4;
    }
    .news-title:hover { text-decoration: underline; }
    .news-summary {
        color: var(--text-secondary);
        font-size: 0.82rem;
        margin-top: 3px;
        line-height: 1.4;
    }

    /* ═══ Watchlist table rows with market left-border ═══ */
    .wl-row-ashare { border-left: 3px solid var(--market-ashare) !important; }
    .wl-row-us     { border-left: 3px solid var(--market-us) !important; }
    .wl-row-hk      { border-left: 3px solid var(--market-hk) !important; }
    </style>
    """, unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════
# Sidebar
# ═══════════════════════════════════════════════════════════════

def render_language_selector():
    """Render language toggle in sidebar. Persists across page navigation."""
    st.sidebar.markdown("---")
    st.sidebar.subheader(t("sidebar.language"))

    current_lang = _lang()
    lang_labels = ["中文", "English"]
    lang_keys = ["zh", "en"]

    try:
        default_idx = lang_keys.index(current_lang)
    except ValueError:
        default_idx = 0

    selected = st.sidebar.selectbox(
        label=t("sidebar.language"),
        options=lang_keys,
        format_func=lambda k: LANGUAGES.get(k, k),
        index=default_idx,
        key="lang_selector",
        label_visibility="collapsed",
    )
    if selected != st.session_state.get("lang"):
        st.session_state.lang = selected
        st.rerun()


def render_sidebar() -> dict:
    """Render the shared sidebar with LLM configuration + language selector.

    Returns:
        dict with keys: api_key, api_base, model_name
    """
    st.sidebar.title(t("sidebar.title"))
    st.sidebar.markdown("---")

    # LLM Configuration
    st.sidebar.subheader(t("sidebar.llm_settings"))

    # Persist in session state so switching pages doesn't reset
    if "api_key" not in st.session_state:
        st.session_state.api_key = ""
    if "api_base" not in st.session_state:
        st.session_state.api_base = "https://api.deepseek.com/v1"
    if "model_name" not in st.session_state:
        st.session_state.model_name = "deepseek-v4-flash"
    if "lang" not in st.session_state:
        st.session_state.lang = "zh"

    api_key = st.sidebar.text_input(
        t("sidebar.api_key"),
        value=st.session_state.api_key or os.getenv("DEEPSEEK_API_KEY", ""),
        type="password",
        help="Enter your DeepSeek API key (or set DEEPSEEK_API_KEY in .env)",
        key="sidebar_api_key",
    )
    st.session_state.api_key = api_key

    api_base = st.sidebar.text_input(
        t("sidebar.api_base"),
        value=st.session_state.api_base,
        key="sidebar_api_base",
    )
    st.session_state.api_base = api_base

    model_name = st.sidebar.selectbox(
        t("sidebar.model"),
        ["deepseek-v4-flash", "deepseek-v4-pro"],
        index=0 if st.session_state.model_name == "deepseek-v4-flash" else 1,
        key="sidebar_model",
    )
    st.session_state.model_name = model_name

    # Language selector
    render_language_selector()

    return {
        "api_key": api_key or os.getenv("DEEPSEEK_API_KEY", ""),
        "api_base": api_base,
        "model_name": model_name,
    }


def render_page_header(title: str, description: str = ""):
    """Consistent page header with title and optional description."""
    st.title(title)
    if description:
        st.markdown(description)
    st.markdown("---")


# ═══════════════════════════════════════════════════════════════
# Market Helpers
# ═══════════════════════════════════════════════════════════════

def get_market_from_symbol(symbol: str) -> str:
    """Detect market from symbol format.

    Returns: "ashare" | "hk" | "us"
    """
    if symbol.isdigit() and len(symbol) == 6:
        return "ashare"
    elif symbol.isdigit() and len(symbol) == 5:
        return "hk"
    return "us"


def market_color(market: str) -> str:
    """Return hex color for a market type."""
    return {
        "ashare": "#e74c3c",
        "us": "#2980b9",
        "hk": "#27ae60",
    }.get(market, "#8b949e")


def market_badge(market: str) -> str:
    """Return an HTML badge colored by market type.

    Args:
        market: "ashare", "us", "hk", or other.
    """
    label = t(f"market.{market}")
    return (
        f'<span class="market-badge market-badge-{market}">'
        f'{label}</span>'
    )


# ═══════════════════════════════════════════════════════════════
# Formatting Helpers
# ═══════════════════════════════════════════════════════════════

def fmt_price(val) -> str:
    """Format a price value with appropriate precision."""
    if val is None:
        return t("common.na")
    if isinstance(val, (int, float)):
        if abs(val) < 1:
            return f"{val:.4f}"
        elif abs(val) < 1000:
            return f"{val:.2f}"
        else:
            return f"{val:,.2f}"
    return str(val)


def fmt_pct(val) -> str:
    """Format a percentage value with sign."""
    if val is None:
        return t("common.na")
    if isinstance(val, (int, float)):
        sign = "+" if val > 0 else ""
        return f"{sign}{val:.2f}%"
    return str(val)


def fmt_market_cap(val) -> str:
    """Format market cap in human-readable form."""
    if val is None:
        return t("common.na")
    val = float(val)
    if val >= 1e12:
        return f"${val/1e12:.2f}T"
    elif val >= 1e9:
        return f"${val/1e9:.2f}B"
    elif val >= 1e6:
        return f"${val/1e6:.2f}M"
    else:
        return f"${val:,.0f}"


def pct_color(val) -> str:
    """Return color name based on sign."""
    if val is None:
        return "gray"
    if val > 0:
        return "green"
    elif val < 0:
        return "red"
    return "gray"


def pct_html(val) -> str:
    """Return HTML span with color for percentage display."""
    if val is None:
        return f'<span class="neutral">{t("common.na")}</span>'
    color_class = "positive" if val > 0 else ("negative" if val < 0 else "neutral")
    sign = "+" if val > 0 else ""
    return f'<span class="{color_class}">{sign}{val:.2f}%</span>'


def rating_badge(rating: str) -> str:
    """Return gradient-colored HTML badge for BUY/HOLD/SELL rating."""
    if not rating:
        return ""
    r = rating.upper()
    if "BUY" in r:
        cls = "rating-badge-buy"
        label = t("rating.buy") if "BUY" in t("rating.buy") else "BUY"
    elif "SELL" in r:
        cls = "rating-badge-sell"
        label = t("rating.sell") if "SELL" in t("rating.sell") else "SELL"
    else:
        cls = "rating-badge-hold"
        label = t("rating.hold") if "HOLD" in t("rating.hold") else "HOLD"
    return f'<span class="rating-badge {cls}">{label}</span>'


# ═══════════════════════════════════════════════════════════════
# Index Card Renderer
# ═══════════════════════════════════════════════════════════════

def render_index_card(index: dict) -> str:
    """Return HTML for a single market index card.

    Args:
        index: dict with keys: code, name, name_en, price, change_pct, market.
    """
    lang = _lang()
    name = index.get("name_en") if lang == "en" else index.get("name", "")
    price = index.get("price")
    change_pct = index.get("change_pct")
    market = index.get("market", "")

    # Price display
    if price is not None:
        if price >= 10000:
            price_str = f"{price:,.2f}"
        elif price >= 1:
            price_str = f"{price:,.2f}"
        else:
            price_str = f"{price:.4f}"
    else:
        price_str = t("common.na")

    # Change display
    arrow = "▲" if (change_pct or 0) >= 0 else "▼"
    chg_class = "positive" if (change_pct or 0) >= 0 else "negative"
    sign = "+" if (change_pct or 0) > 0 else ""
    chg_str = f"{sign}{change_pct:.2f}%" if change_pct is not None else t("common.na")

    # Pre-close note for US indices
    data_date = index.get("data_date", "")
    note = ""
    if index.get("source") == "akshare_sina" and data_date:
        note = f" ({t('common.previous_close')})"

    return f"""
    <div class="index-card" style="border-left:3px solid {market_color(market)};">
        <div class="idx-name">
            <span class="idx-market-dot idx-dot-{market}"></span>{name}{note}
        </div>
        <div class="idx-price">{price_str}</div>
        <div class="idx-change {chg_class}">{arrow} {chg_str}</div>
    </div>
    """


# ═══════════════════════════════════════════════════════════════
# News Card Renderer
# ═══════════════════════════════════════════════════════════════

def render_news_card(news: dict) -> str:
    """Return HTML for a single news item in timeline layout.

    Args:
        news: dict with keys: title, display_time, summary, url, source.
    """
    title = news.get("title", "")
    time_str = news.get("display_time", "")
    summary = news.get("summary", "")
    url = news.get("url", "")
    source = news.get("source", "")

    # Truncate summary
    if len(summary) > 150:
        summary = summary[:150] + "..."

    title_html = (
        f'<a class="news-title" href="{url}" target="_blank" '
        f'rel="noopener noreferrer">{title}</a>'
    ) if url else f'<span class="news-title">{title}</span>'

    return f"""
    <div class="news-item">
        <div class="news-time">{time_str}</div>
        <div>
            {title_html}
            <div class="news-summary">{summary} <small>{source}</small></div>
        </div>
    </div>
    """
