"""
Shared UI helpers — global CSS, page headers, KPI cards, badges.

Streamlit'in default görünümünü kapatıp tutarlı bir endüstriyel/koyu
tema veriyoruz. Her sayfa init'inde ``inject_css()`` çağrılır.
"""

from __future__ import annotations

import streamlit as st


# ---------------------------------------------------------------------------
# Color tokens (CSS değişkenlerine paralel; debugging için tek noktada)
# ---------------------------------------------------------------------------
COLORS = {
    "bg":            "#0a0e14",
    "bg_card":       "#161b22",
    "bg_card_hover": "#1c2330",
    "border":        "#21262d",
    "border_strong": "#30363d",
    "text":          "#e6edf3",
    "text_muted":    "#8b949e",
    "primary":       "#3b82f6",
    "primary_dark":  "#1d4ed8",
    "success":       "#10b981",
    "warning":       "#f59e0b",
    "danger":        "#ef4444",
    "info":          "#06b6d4",
}


_GLOBAL_CSS = """
<style>
/* ---- Reset & global ---- */
#MainMenu, footer, [data-testid="stToolbar"] {visibility: hidden;}

html, body, [class*="css"] {
    font-family: -apple-system, "Segoe UI", "SF Pro Display", system-ui, sans-serif;
}

.block-container {
    padding-top: 1.5rem !important;
    padding-bottom: 3rem !important;
    max-width: 1480px;
}

h1, h2, h3 { letter-spacing: -0.02em; }
h1 { font-weight: 700; }
h2 { font-weight: 600; }

hr {
    border: none;
    border-top: 1px solid #21262d;
    margin: 2rem 0 !important;
}

/* ---- Page header banner ---- */
.norm-header {
    background: linear-gradient(135deg, #1e3a8a 0%, #1e40af 60%, #2563eb 100%);
    padding: 1.5rem 2rem;
    border-radius: 14px;
    margin-bottom: 1.75rem;
    box-shadow: 0 6px 24px rgba(37, 99, 235, 0.18);
    border: 1px solid rgba(255, 255, 255, 0.06);
}
.norm-header h1 {
    margin: 0 !important;
    color: #ffffff !important;
    font-size: 1.7rem;
    font-weight: 700;
    line-height: 1.2;
}
.norm-header p {
    margin: 0.35rem 0 0 0 !important;
    color: rgba(226, 232, 240, 0.85) !important;
    font-size: 0.92rem;
    font-weight: 400;
}

/* ---- KPI card ---- */
.kpi-card {
    background: #161b22;
    border: 1px solid #21262d;
    border-radius: 12px;
    padding: 1.1rem 1.25rem;
    height: 100%;
    transition: transform 0.18s ease, border-color 0.18s ease, background 0.18s ease;
}
.kpi-card:hover {
    transform: translateY(-2px);
    border-color: #3b82f6;
    background: #1c2330;
}
.kpi-label {
    color: #8b949e;
    font-size: 0.78rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    margin-bottom: 0.4rem;
}
.kpi-value {
    color: #e6edf3;
    font-size: 1.85rem;
    font-weight: 700;
    line-height: 1.1;
    font-feature-settings: "tnum";
}
.kpi-sub {
    color: #8b949e;
    font-size: 0.82rem;
    margin-top: 0.4rem;
}
.kpi-delta {
    margin-top: 0.4rem;
    font-size: 0.85rem;
    font-weight: 600;
    display: inline-block;
    padding: 0.15rem 0.5rem;
    border-radius: 5px;
}
.kpi-delta.pos {
    color: #ef4444;
    background: rgba(239, 68, 68, 0.12);
}
.kpi-delta.neg {
    color: #10b981;
    background: rgba(16, 185, 129, 0.12);
}
.kpi-delta.neutral {
    color: #8b949e;
    background: rgba(139, 148, 158, 0.12);
}

/* ---- Status pill ---- */
.status-pill {
    display: inline-block;
    padding: 0.3rem 0.85rem;
    border-radius: 999px;
    font-size: 0.85rem;
    font-weight: 600;
    border: 1px solid transparent;
}
.status-open    { background: rgba(16, 185, 129, 0.12); color: #34d399; border-color: rgba(16,185,129,0.4); }
.status-late    { background: rgba(245, 158, 11, 0.12); color: #fbbf24; border-color: rgba(245,158,11,0.4); }
.status-locked  { background: rgba(139, 148, 158, 0.12); color: #cbd5e1; border-color: rgba(139,148,158,0.4); }

/* ---- Sidebar ---- */
[data-testid="stSidebar"] {
    background: #0d1117;
    border-right: 1px solid #21262d;
}
[data-testid="stSidebar"] .block-container {
    padding-top: 1.5rem !important;
}
.sidebar-user-card {
    background: linear-gradient(135deg, #1e293b 0%, #161b22 100%);
    border: 1px solid #2d3748;
    border-radius: 12px;
    padding: 1rem;
    margin-bottom: 1rem;
}
.sidebar-user-name {
    color: #e6edf3;
    font-weight: 600;
    font-size: 1rem;
    line-height: 1.2;
}
.sidebar-user-role {
    color: #94a3b8;
    font-size: 0.78rem;
    margin-top: 0.3rem;
    display: inline-block;
    padding: 0.15rem 0.55rem;
    background: rgba(59, 130, 246, 0.15);
    border-radius: 999px;
    border: 1px solid rgba(59, 130, 246, 0.3);
}

/* ---- Buttons ---- */
.stButton > button {
    border-radius: 9px !important;
    font-weight: 600 !important;
    transition: all 0.15s ease;
    border: 1px solid #30363d;
}
.stButton > button:hover {
    border-color: #3b82f6;
    transform: translateY(-1px);
}
.stButton > button[kind="primary"] {
    background: linear-gradient(135deg, #3b82f6, #1d4ed8) !important;
    border: none !important;
    box-shadow: 0 2px 8px rgba(59, 130, 246, 0.3);
}
.stButton > button[kind="primary"]:hover {
    box-shadow: 0 4px 14px rgba(59, 130, 246, 0.45);
}

/* ---- Form inputs ---- */
.stTextInput input, .stNumberInput input, .stDateInput input,
.stTimeInput input, .stTextArea textarea {
    border-radius: 9px !important;
    border: 1px solid #21262d !important;
    background: #0d1117 !important;
    color: #e6edf3 !important;
    transition: border-color 0.15s ease;
}
.stTextInput input:focus, .stNumberInput input:focus,
.stDateInput input:focus, .stTimeInput input:focus,
.stTextArea textarea:focus {
    border-color: #3b82f6 !important;
}

/* Selectbox */
[data-baseweb="select"] > div {
    border-radius: 9px !important;
    border-color: #21262d !important;
    background: #0d1117 !important;
}

/* ---- Tabs ---- */
.stTabs [data-baseweb="tab-list"] {
    gap: 0.4rem;
    border-bottom: 1px solid #21262d;
}
.stTabs [data-baseweb="tab"] {
    background: transparent;
    border-radius: 8px 8px 0 0;
    padding: 0.6rem 1.1rem;
    font-weight: 500;
    color: #8b949e;
    transition: all 0.15s ease;
}
.stTabs [data-baseweb="tab"]:hover {
    background: rgba(59, 130, 246, 0.06);
    color: #e6edf3;
}
.stTabs [aria-selected="true"] {
    background: #161b22 !important;
    color: #3b82f6 !important;
    border-bottom: 2px solid #3b82f6;
}

/* ---- Expander ---- */
.streamlit-expanderHeader, [data-testid="stExpander"] summary {
    background: #161b22 !important;
    border-radius: 9px !important;
    border: 1px solid #21262d !important;
    font-weight: 600 !important;
    transition: all 0.15s ease;
}
[data-testid="stExpander"] summary:hover {
    border-color: #3b82f6 !important;
}

/* ---- DataFrame ---- */
.stDataFrame {
    border-radius: 10px;
    overflow: hidden;
    border: 1px solid #21262d;
}

/* ---- Metric (varsayılanı koruyalım, ama renkleri tutarlı yapalım) ---- */
[data-testid="stMetricValue"] {
    font-weight: 700;
}

/* ---- Alert kutuları (st.success / info / warning / error) ---- */
.stAlert {
    border-radius: 10px;
    border: 1px solid;
}

/* ---- Login screen özel ---- */
.login-wrap {
    max-width: 440px;
    margin: 4rem auto;
    background: #161b22;
    border: 1px solid #21262d;
    border-radius: 16px;
    padding: 2.5rem 2rem;
    box-shadow: 0 20px 50px rgba(0, 0, 0, 0.4);
}
.login-logo {
    text-align: center;
    margin-bottom: 1.5rem;
}
.login-logo h1 {
    color: #e6edf3;
    font-size: 1.5rem;
    font-weight: 700;
    margin: 0;
}
.login-logo p {
    color: #8b949e;
    font-size: 0.9rem;
    margin-top: 0.3rem;
}
.login-divider {
    height: 1px;
    background: #21262d;
    margin: 1.5rem 0 1rem;
}
</style>
"""


def inject_css() -> None:
    """Sayfa init'inde çağır — global CSS'i sayfaya enjekte eder."""
    st.markdown(_GLOBAL_CSS, unsafe_allow_html=True)


def page_header(title: str, subtitle: str = "", icon: str = "") -> None:
    """Banner-style sayfa başlığı."""
    icon_html = f'<span style="margin-right:0.6rem;">{icon}</span>' if icon else ""
    sub_html = f'<p>{subtitle}</p>' if subtitle else ""
    st.markdown(
        f'<div class="norm-header"><h1>{icon_html}{title}</h1>{sub_html}</div>',
        unsafe_allow_html=True,
    )


def kpi_card(
    label: str,
    value: str,
    sub: str = "",
    delta: str = "",
    delta_kind: str = "neutral",
) -> str:
    """Bir KPI kartının HTML string'ini döndürür.

    delta_kind: 'pos' (kırmızı, yukarı), 'neg' (yeşil, aşağı/iyi), 'neutral'.
    Birden fazlasını yan yana koymak için st.columns kullan, her column içinde
    st.markdown(kpi_card(...), unsafe_allow_html=True).
    """
    sub_html = f'<div class="kpi-sub">{sub}</div>' if sub else ""
    delta_html = f'<div class="kpi-delta {delta_kind}">{delta}</div>' if delta else ""
    return (
        f'<div class="kpi-card">'
        f'  <div class="kpi-label">{label}</div>'
        f'  <div class="kpi-value">{value}</div>'
        f'  {sub_html}{delta_html}'
        f'</div>'
    )


def render_kpis(cards: list[str]) -> None:
    """Bir liste KPI HTML'i alır, eşit genişlikte sütunlara koyar."""
    cols = st.columns(len(cards))
    for col, html in zip(cols, cards):
        col.markdown(html, unsafe_allow_html=True)


def status_pill(status: str) -> str:
    """Status (open/late/locked) için pill HTML'i döndürür."""
    labels = {
        "open":   "📝 Açık",
        "late":   "⏰ Geç Giriş",
        "locked": "🔒 Kapalı",
    }
    label = labels.get(status, status)
    return f'<span class="status-pill status-{status}">{label}</span>'


def render_sidebar_user(full_name: str, role: str) -> None:
    """Sidebar üstüne kullanıcı kart'ı."""
    role_label = "Yönetici" if role == "admin" else "Kullanıcı"
    st.sidebar.markdown(
        f'<div class="sidebar-user-card">'
        f'  <div class="sidebar-user-name">👤 {full_name}</div>'
        f'  <span class="sidebar-user-role">{role_label}</span>'
        f'</div>',
        unsafe_allow_html=True,
    )
