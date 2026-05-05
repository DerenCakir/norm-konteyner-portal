"""
Shared UI helpers for the Streamlit portal.

This module owns the single enterprise dashboard design system used by all
pages: global CSS, sidebar fragments, headers, KPI cards, status panels,
empty states, filter/form/data panel headers and small utility badges.
"""

from __future__ import annotations

import base64
from html import escape
from pathlib import Path

import streamlit as st


_GLOBAL_CSS = """
<style>
:root {
    --bg: #f3f6fa;
    --surface: #ffffff;
    --surface-muted: #f8fafc;
    --surface-raised: #ffffff;
    --border: #d8e0ea;
    --border-strong: #b8c5d6;
    --text: #111827;
    --muted: #64748b;
    --primary: #2563eb;
    --primary-strong: #1d4ed8;
    --primary-soft: #e8f0ff;
    --success: #0f766e;
    --success-soft: #ecfdf5;
    --warning: #b45309;
    --warning-soft: #fffbeb;
    --danger: #b91c1c;
    --danger-soft: #fef2f2;
    --sidebar: #0f172a;
    --sidebar-border: #1e293b;
    --radius-sm: 8px;
    --radius-md: 12px;
    --radius-lg: 16px;
    --shadow-sm: 0 1px 2px rgba(15, 23, 42, 0.06);
    --shadow-md: 0 12px 28px rgba(15, 23, 42, 0.08);
}

#MainMenu, footer, [data-testid="stToolbar"] {
    visibility: hidden;
}

html, body, [class*="css"], button, input, textarea, select {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Inter, system-ui, sans-serif !important;
    -webkit-font-smoothing: antialiased;
}

[data-testid="stAppViewContainer"]:not(:has(.login-wrap)) {
    background: var(--bg) !important;
}

.block-container {
    max-width: 1360px !important;
    padding: 1.45rem 2rem 4rem !important;
}

h1, h2, h3, h4, h5, h6 {
    color: var(--text) !important;
    letter-spacing: 0 !important;
}

p, span, div, label {
    color: inherit;
}

hr {
    border: none;
    border-top: 1px solid var(--border);
    margin: 1.5rem 0 !important;
}

/* Login */
.login-wrap {
    max-width: 420px;
    margin: 8vh auto 0;
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius-lg);
    box-shadow: var(--shadow-md);
    padding: 1.5rem;
}
.login-logo {
    display: flex;
    align-items: center;
    gap: 0.8rem;
    margin-bottom: 0.85rem;
}
.login-img {
    width: 42px;
    height: 42px;
    object-fit: contain;
    border-radius: 10px;
}
.login-brand {
    color: var(--text);
    font-weight: 850;
    letter-spacing: 0.02em;
}
.login-divider {
    height: 1px;
    background: var(--border);
    margin: 1rem 0;
}
.login-footer {
    color: var(--muted);
    font-size: 0.78rem;
    margin-top: 1rem;
    text-align: center;
}

/* Sidebar */
[data-testid="stSidebar"] {
    background: var(--sidebar) !important;
    border-right: 1px solid var(--sidebar-border) !important;
    display: block !important;
    visibility: visible !important;
    min-width: 15.75rem !important;
    max-width: 15.75rem !important;
    transform: translateX(0) !important;
    left: 0 !important;
}
[data-testid="stSidebar"][aria-expanded="false"] {
    min-width: 15.75rem !important;
    max-width: 15.75rem !important;
    transform: translateX(0) !important;
}
[data-testid="stSidebarCollapseButton"],
[data-testid="collapsedControl"] {
    display: none !important;
    pointer-events: none !important;
}
[data-testid="stSidebar"] * {
    color: #dbeafe !important;
}
[data-testid="stSidebar"] .block-container {
    padding: 0.75rem 1rem 1.5rem !important;
}
[data-testid="stSidebarNav"] {
    margin-top: 0.5rem !important;
}
[data-testid="stSidebarNav"] ul {
    gap: 0.25rem !important;
}
[data-testid="stSidebarNav"] li a {
    border-radius: 9px !important;
    padding: 0.55rem 0.75rem !important;
    font-weight: 700 !important;
    color: #dbeafe !important;
}
[data-testid="stSidebarNav"] li a:hover {
    background: rgba(148, 163, 184, 0.14) !important;
}
[data-testid="stSidebarNav"] li a[aria-current="page"] {
    background: #1e3a8a !important;
    color: #ffffff !important;
}
.sidebar-brand-card,
.sidebar-user-card {
    background: #111c31;
    border: 1px solid #26364f;
    border-radius: 12px;
    padding: 0.75rem;
    box-shadow: 0 1px 0 rgba(255, 255, 255, 0.04) inset;
}
.sidebar-brand-card {
    display: flex;
    align-items: center;
    gap: 0.7rem;
    margin-bottom: 0.8rem;
}
.sidebar-brand-logo {
    width: 38px;
    height: 38px;
    border-radius: 10px;
    object-fit: contain;
}
.sidebar-brand-title {
    color: #ffffff !important;
    font-size: 0.84rem;
    font-weight: 850;
    letter-spacing: 0.02em;
}
.sidebar-brand-subtitle {
    color: #93a4bd !important;
    font-size: 0.72rem;
    margin-top: 0.1rem;
}
.sidebar-user-card {
    margin-top: 1rem;
}
.sidebar-user-name {
    color: #ffffff !important;
    font-weight: 800;
    font-size: 0.9rem;
}
.sidebar-user-role {
    display: inline-flex;
    width: fit-content;
    margin-top: 0.45rem;
    border-radius: 999px;
    padding: 0.22rem 0.55rem;
    background: #1d4ed8;
    border: 1px solid #3b82f6;
    color: #ffffff !important;
    font-size: 0.72rem;
    font-weight: 750;
}
[data-testid="stSidebar"] button {
    background: #111c31 !important;
    border: 1px solid #26364f !important;
    border-radius: 10px !important;
    color: #ffffff !important;
    font-weight: 750 !important;
}

/* Page composition */
.norm-header,
.dashboard-hero,
.kpi-card,
.status-panel,
.flow-panel,
.qa-card,
.empty-state,
.data-panel-head,
.form-panel-head,
.filter-bar,
.progress-summary {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius-lg);
    box-shadow: var(--shadow-sm);
}

.norm-header {
    padding: 1.35rem 1.5rem;
    margin-bottom: 1.1rem;
    background:
        linear-gradient(135deg, rgba(37, 99, 235, 0.09), rgba(15, 118, 110, 0.05)),
        var(--surface);
}
.norm-header h1 {
    font-size: clamp(1.45rem, 2.4vw, 1.9rem);
    line-height: 1.15;
    font-weight: 850;
    margin: 0;
}
.norm-header p {
    color: var(--muted);
    max-width: 820px;
    margin: 0.55rem 0 0;
    font-size: 0.95rem;
}
.norm-header-meta {
    display: flex;
    flex-wrap: wrap;
    gap: 0.5rem;
    margin-top: 1rem;
}

.dashboard-hero {
    display: grid;
    grid-template-columns: minmax(0, 1fr) minmax(280px, 420px);
    gap: 1rem;
    align-items: stretch;
    padding: 1.45rem;
    margin-bottom: 1.05rem;
    background:
        linear-gradient(135deg, rgba(37, 99, 235, 0.96), rgba(14, 165, 233, 0.78)),
        #2563eb;
    border-color: rgba(37, 99, 235, 0.28);
    box-shadow: 0 14px 34px rgba(30, 64, 175, 0.18);
}
.dashboard-hero-copy,
.dashboard-hero-copy * {
    color: #ffffff !important;
}
.dashboard-eyebrow {
    font-size: 0.74rem;
    font-weight: 850;
    opacity: 0.86;
    margin-bottom: 0.55rem;
}
.dashboard-hero h1 {
    margin: 0 !important;
    font-size: clamp(1.65rem, 2.5vw, 2.25rem) !important;
    line-height: 1.12;
}
.dashboard-hero p {
    margin: 0.7rem 0 0;
    max-width: 720px;
    font-size: 0.96rem;
}
.dashboard-hero-badges {
    display: grid;
    gap: 0.65rem;
}
.hero-badge {
    background: rgba(255, 255, 255, 0.14);
    border: 1px solid rgba(255, 255, 255, 0.26);
    border-radius: 12px;
    padding: 0.8rem 0.9rem;
}
.hero-badge span {
    display: block;
    color: rgba(255, 255, 255, 0.78) !important;
    font-size: 0.74rem;
    font-weight: 750;
}
.hero-badge strong {
    display: block;
    color: #ffffff !important;
    font-size: 1.05rem;
    margin-top: 0.2rem;
}

.section-gap {
    height: 1rem;
}
.section-header {
    margin: 1.4rem 0 0.75rem;
    padding-bottom: 0.65rem;
    border-bottom: 1px solid var(--border);
}
.section-header span {
    display: block;
    color: var(--text);
    font-weight: 850;
    font-size: 1.17rem;
}
.section-header small {
    display: block;
    color: var(--muted);
    font-size: 0.88rem;
    margin-top: 0.25rem;
}

/* Cards and panels */
.kpi-card {
    min-height: 126px;
    padding: 1rem;
    position: relative;
    overflow: hidden;
}
.kpi-card::before {
    content: "";
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    height: 3px;
    background: var(--primary);
}
.kpi-tone-green::before { background: var(--success); }
.kpi-tone-amber::before { background: var(--warning); }
.kpi-tone-red::before { background: var(--danger); }
.kpi-label {
    color: var(--muted);
    font-size: 0.72rem;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    font-weight: 850;
}
.kpi-value {
    color: var(--text);
    font-size: clamp(1.35rem, 2vw, 2rem);
    line-height: 1.08;
    margin-top: 0.55rem;
    font-weight: 850;
}
.kpi-sub {
    color: var(--muted);
    font-size: 0.84rem;
    margin-top: 0.55rem;
}
.kpi-delta {
    font-size: 0.78rem;
    font-weight: 750;
    margin-top: 0.35rem;
}
.kpi-delta.pos { color: var(--danger); }
.kpi-delta.neg { color: var(--success); }
.kpi-delta.neutral { color: var(--muted); }

.status-panel {
    padding: 1.1rem 1.2rem;
    border-left: 4px solid var(--primary);
}
.status-panel-open,
.status-panel-success { border-left-color: var(--success); }
.status-panel-late,
.status-panel-warning { border-left-color: var(--warning); }
.status-panel-locked,
.status-panel-danger { border-left-color: var(--danger); }
.status-panel-top,
.status-panel-footer {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 0.8rem;
}
.status-panel-top span {
    color: var(--muted);
    font-size: 0.75rem;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    font-weight: 850;
}
.status-panel-top strong,
.status-badge,
.norm-header-badge {
    display: inline-flex;
    align-items: center;
    width: fit-content;
    border-radius: 999px;
    padding: 0.28rem 0.62rem;
    background: var(--surface-muted);
    border: 1px solid var(--border);
    color: var(--muted);
    font-size: 0.76rem;
    font-weight: 800;
}
.status-badge.info,
.norm-header-badge.info { background: var(--primary-soft); color: var(--primary-strong); border-color: #bfdbfe; }
.status-badge.success,
.norm-header-badge.success { background: var(--success-soft); color: var(--success); border-color: #a7f3d0; }
.status-badge.warning,
.norm-header-badge.warning { background: var(--warning-soft); color: var(--warning); border-color: #fde68a; }
.status-badge.danger,
.norm-header-badge.danger { background: var(--danger-soft); color: var(--danger); border-color: #fecaca; }
.status-panel h4 {
    margin: 0.45rem 0 0.35rem !important;
    font-size: 1.08rem !important;
    font-weight: 850 !important;
}
.status-panel p {
    margin: 0;
    color: #334155;
    font-size: 0.92rem;
}
.status-panel-footer {
    margin-top: 0.85rem;
}
.status-panel-footer small,
.status-panel-items small {
    color: var(--muted);
}
.status-panel-action {
    color: var(--primary-strong) !important;
    font-weight: 800;
    text-decoration: none !important;
}
.status-panel-items {
    display: flex;
    flex-wrap: wrap;
    gap: 0.75rem;
    margin-top: 0.75rem;
}

.flow-panel {
    padding: 0.9rem;
    display: grid;
    gap: 0.55rem;
}
.flow-step {
    display: grid;
    grid-template-columns: 34px minmax(0, 1fr);
    gap: 0.7rem;
    align-items: start;
    padding: 0.65rem;
    border-radius: 10px;
    background: var(--surface-muted);
    border: 1px solid var(--border);
}
.flow-step > span {
    display: grid;
    place-items: center;
    height: 28px;
    width: 28px;
    border-radius: 999px;
    background: var(--primary-soft);
    color: var(--primary-strong);
    font-weight: 850;
    font-size: 0.76rem;
}
.flow-step strong {
    display: block;
    color: var(--text);
    font-size: 0.9rem;
}
.flow-step small {
    display: block;
    color: var(--muted);
    margin-top: 0.15rem;
}

.qa-card {
    display: block;
    min-height: 124px;
    padding: 1rem;
    text-decoration: none !important;
    transition: border-color 0.15s ease, box-shadow 0.15s ease, transform 0.15s ease;
}
.qa-card:hover {
    border-color: #93b4e8;
    box-shadow: 0 8px 20px rgba(37, 99, 235, 0.10);
    transform: translateY(-1px);
}
.qa-icon {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    min-width: 30px;
    height: 26px;
    padding: 0 0.55rem;
    border-radius: 999px;
    background: var(--primary-soft);
    border: 1px solid #bfdbfe;
    color: var(--primary-strong);
    font-size: 0.72rem;
    font-weight: 850;
}
.qa-title {
    display: block;
    color: var(--text);
    font-weight: 850;
    margin-top: 0.85rem;
}
.qa-desc {
    display: block;
    color: var(--muted);
    font-size: 0.86rem;
    margin-top: 0.3rem;
}
.qa-cta {
    display: inline-flex;
    gap: 0.25rem;
    color: var(--primary-strong);
    font-size: 0.82rem;
    font-weight: 850;
    margin-top: 0.85rem;
}

.empty-state {
    padding: 1.25rem 1.35rem;
    display: grid;
    gap: 0.65rem;
    border-left: 4px solid var(--primary);
}
.empty-state.warning { border-left-color: var(--warning); }
.empty-state.danger { border-left-color: var(--danger); }
.empty-state.success { border-left-color: var(--success); }
.empty-state h3 {
    margin: 0 !important;
    color: var(--text) !important;
    font-size: 1.1rem !important;
    font-weight: 850 !important;
}
.empty-state p {
    margin: 0 !important;
    color: var(--muted) !important;
    font-size: 0.92rem;
}

.data-panel-head,
.form-panel-head,
.filter-bar {
    padding: 0.95rem 1.05rem;
    margin: 0.8rem 0 0.75rem;
}
.data-panel-head h3,
.form-panel-head h3,
.filter-bar h3 {
    margin: 0 !important;
    color: var(--text) !important;
    border: 0 !important;
    padding: 0 !important;
    font-size: 1.02rem !important;
    font-weight: 850 !important;
}
.data-panel-head h3::before,
.form-panel-head h3::before,
.filter-bar h3::before {
    display: none !important;
}
.data-panel-head p,
.form-panel-head p,
.filter-bar p,
.table-note {
    margin: 0.3rem 0 0 !important;
    color: var(--muted) !important;
    font-size: 0.86rem !important;
}

.progress-summary {
    padding: 0.95rem 1.05rem;
    margin: 0.85rem 0 1rem;
}
.progress-summary-top {
    display: flex;
    justify-content: space-between;
    gap: 1rem;
    color: var(--text);
    font-weight: 850;
    margin-bottom: 0.65rem;
}
.progress-track {
    height: 10px;
    border-radius: 999px;
    background: #e2e8f0;
    overflow: hidden;
}
.progress-fill {
    height: 100%;
    border-radius: inherit;
    background: linear-gradient(90deg, var(--primary), var(--success));
}

/* Streamlit components */
[data-testid="stDataFrame"] {
    border: 1px solid var(--border) !important;
    border-radius: var(--radius-md) !important;
    box-shadow: var(--shadow-sm) !important;
    overflow: hidden !important;
    background: var(--surface) !important;
}
div[data-testid="stForm"] {
    background: var(--surface) !important;
    border: 1px solid var(--border) !important;
    border-radius: var(--radius-lg) !important;
    box-shadow: var(--shadow-sm) !important;
    padding: 1rem 1.1rem !important;
}
.stTabs [data-baseweb="tab-list"] {
    gap: 0.35rem !important;
    background: var(--surface-muted) !important;
    border: 1px solid var(--border) !important;
    border-radius: 999px !important;
    padding: 0.28rem !important;
}
.stTabs [data-baseweb="tab"] {
    border-radius: 999px !important;
    padding: 0.55rem 0.9rem !important;
    color: var(--muted) !important;
    font-weight: 750 !important;
}
.stTabs [aria-selected="true"] {
    background: var(--surface) !important;
    color: var(--primary) !important;
    box-shadow: var(--shadow-sm) !important;
}
div[data-baseweb="select"] > div,
div[data-baseweb="input"] input,
textarea {
    border-color: var(--border) !important;
    border-radius: 10px !important;
}
.stButton button,
.stDownloadButton button,
[data-testid="stFormSubmitButton"] button {
    border-radius: 10px !important;
    font-weight: 800 !important;
    border: 1px solid var(--border) !important;
}
.stButton button[kind="primary"],
[data-testid="stFormSubmitButton"] button[kind="primary"] {
    background: var(--primary) !important;
    color: #ffffff !important;
    border-color: var(--primary) !important;
}
.stCaption, [data-testid="stCaptionContainer"] {
    color: var(--muted) !important;
    font-size: 0.84rem !important;
}

@media (max-width: 980px) {
    .dashboard-hero {
        grid-template-columns: 1fr;
    }
}
@media (max-width: 760px) {
    .block-container {
        padding-left: 1rem !important;
        padding-right: 1rem !important;
    }
    .status-panel-top,
    .status-panel-footer {
        align-items: flex-start;
        flex-direction: column;
    }
}
</style>
"""


def _esc(value: object) -> str:
    """Escape text before injecting it into controlled HTML snippets."""
    return escape(str(value), quote=True)


def inject_css() -> None:
    """Inject the single global design system."""
    st.markdown(_GLOBAL_CSS, unsafe_allow_html=True)


def render_sidebar_brand(logo_path: str | Path) -> None:
    """Render the Norm Fasteners brand card in the sidebar."""
    logo = Path(logo_path)
    logo_html = ""
    if logo.exists():
        logo_b64 = base64.b64encode(logo.read_bytes()).decode()
        logo_html = (
            f'<img src="data:image/png;base64,{logo_b64}" '
            f'alt="Norm Fasteners" class="sidebar-brand-logo">'
        )

    st.sidebar.markdown(
        f'<div class="sidebar-brand-card">'
        f'  {logo_html}'
        f'  <div>'
        f'    <div class="sidebar-brand-title">NORM FASTENERS</div>'
        f'    <div class="sidebar-brand-subtitle">Konteyner Portalı</div>'
        f'  </div>'
        f'</div>',
        unsafe_allow_html=True,
    )


def page_header(
    title: str,
    subtitle: str = "",
    icon: str = "",
    badges: list[tuple[str, str]] | None = None,
    meta: str | None = None,
) -> None:
    """Render a consistent page header."""
    display_icon = icon if str(icon).isascii() else ""
    icon_html = f'<span style="margin-right:0.7rem;">{_esc(display_icon)}</span>' if display_icon else ""
    sub_html = f'<p>{_esc(subtitle)}</p>' if subtitle else ""
    badge_items: list[tuple[str, str]] = []
    if meta:
        badge_items.append(("info", meta))
    badge_items.extend(badges or [])
    badge_html = ""
    if badge_items:
        badge_html = '<div class="norm-header-meta">' + "".join(
            f'<span class="norm-header-badge {_esc(tone)}">{_esc(text)}</span>'
            for tone, text in badge_items
        ) + '</div>'
    st.markdown(
        f'<div class="norm-header"><h1>{icon_html}{_esc(title)}</h1>{sub_html}{badge_html}</div>',
        unsafe_allow_html=True,
    )


def dashboard_hero(title: str, subtitle: str, badges: list[tuple[str, str]]) -> None:
    """Render the home dashboard hero."""
    badge_html = "".join(
        f'<div class="hero-badge"><span>{_esc(label)}</span><strong>{_esc(value)}</strong></div>'
        for label, value in badges
    )
    st.markdown(
        f'<section class="dashboard-hero">'
        f'  <div class="dashboard-hero-copy">'
        f'    <div class="dashboard-eyebrow">NORM FASTENERS · KONTEYNER OPERASYONLARI</div>'
        f'    <h1>{_esc(title)}</h1>'
        f'    <p>{_esc(subtitle)}</p>'
        f'  </div>'
        f'  <div class="dashboard-hero-badges">{badge_html}</div>'
        f'</section>',
        unsafe_allow_html=True,
    )


def section_header(title: str, subtitle: str = "") -> None:
    """Render a section title with optional helper text."""
    subtitle_html = f'<small>{_esc(subtitle)}</small>' if subtitle else ""
    st.markdown(
        f'<div class="section-header"><span>{_esc(title)}</span>{subtitle_html}</div>',
        unsafe_allow_html=True,
    )


def kpi_card(
    label: str,
    value: str,
    sub: str = "",
    delta: str = "",
    delta_kind: str = "neutral",
    icon: str = "",
    tone: str = "blue",
) -> str:
    """Return KPI card HTML."""
    sub_html = f'<div class="kpi-sub">{_esc(sub)}</div>' if sub else ""
    delta_html = f'<div class="kpi-delta {_esc(delta_kind)}">{_esc(delta)}</div>' if delta else ""
    icon_html = f'<div class="kpi-icon">{_esc(icon)}</div>' if icon else ""
    return (
        f'<div class="kpi-card kpi-tone-{_esc(tone)}">'
        f'  <div class="kpi-card-top">'
        f'    <div class="kpi-label">{_esc(label)}</div>'
        f'    {icon_html}'
        f'  </div>'
        f'  <div class="kpi-value">{_esc(value)}</div>'
        f'  <div class="kpi-card-bottom">{sub_html}{delta_html}</div>'
        f'</div>'
    )


def render_kpis(cards: list[str]) -> None:
    """Render KPI cards in equal columns."""
    if not cards:
        return
    cols = st.columns(len(cards))
    for col, html in zip(cols, cards):
        col.markdown(html, unsafe_allow_html=True)


def status_panel(
    title: str = "",
    description: str = "",
    tone: str = "info",
    badge: str | None = None,
    items: list[tuple[str, str]] | None = None,
    *,
    status: str | None = None,
    body: str | None = None,
    meta: str | None = None,
    cta_label: str = "",
    cta_href: str = "",
) -> str:
    """Return a status panel. Backward compatible with the home page call."""
    status_name = status or tone
    body_text = body if body is not None else description
    meta_text = meta if meta is not None else (badge or "")
    item_html = ""
    if items:
        item_html = '<div class="status-panel-items">' + "".join(
            f'<small><strong>{_esc(label)}</strong> {_esc(value)}</small>'
            for label, value in items
        ) + '</div>'
    cta_html = (
        f'<a class="status-panel-action" href="{_esc(cta_href)}" target="_self">{_esc(cta_label)}</a>'
        if cta_label and cta_href else ""
    )
    return (
        f'<div class="status-panel status-panel-{_esc(status_name)}">'
        f'  <div class="status-panel-top">'
        f'    <span>Operasyon Durumu</span>'
        f'    <strong>{_esc(meta_text)}</strong>'
        f'  </div>'
        f'  <h4>{_esc(title)}</h4>'
        f'  <p>{_esc(body_text)}</p>'
        f'  {item_html}'
        f'  <div class="status-panel-footer">'
        f'    <small>Türkiye saati ile haftalık sayım döngüsü</small>'
        f'    {cta_html}'
        f'  </div>'
        f'</div>'
    )


def timeline_panel(steps: list[tuple[str, str, str]]) -> str:
    """Return the weekly workflow panel."""
    rows = "".join(
        f'<div class="flow-step">'
        f'  <span>{_esc(number)}</span>'
        f'  <div><strong>{_esc(title)}</strong><small>{_esc(desc)}</small></div>'
        f'</div>'
        for number, title, desc in steps
    )
    return f'<div class="flow-panel">{rows}</div>'


def quick_action_card(icon: str, title: str, desc: str, href: str = "", cta: str = "Aç") -> str:
    """Return a clickable quick action card."""
    tag = "a" if href else "div"
    href_attr = f' href="{_esc(href)}" target="_self"' if href else ""
    fallback_icons = {
        "sayim_girisi": "01",
        "anlik_durum": "02",
        "analiz": "03",
        "haftalik_takip": "04",
    }
    display_icon = icon if str(icon).isascii() else fallback_icons.get(href, "")
    return (
        f'<{tag} class="qa-card"{href_attr}>'
        f'  <span class="qa-icon">{_esc(display_icon)}</span>'
        f'  <span class="qa-title">{_esc(title)}</span>'
        f'  <span class="qa-desc">{_esc(desc)}</span>'
        f'  <span class="qa-cta">{_esc(cta)}<span aria-hidden="true">›</span></span>'
        f'</{tag}>'
    )


def status_pill(status: str) -> str:
    """Return an inline pill for submission window status."""
    labels = {"open": "Açık", "late": "Geç giriş", "locked": "Kapalı"}
    label = labels.get(status, status)
    return f'<span class="status-pill status-{_esc(status)}">{_esc(label)}</span>'


def status_badge(text: str, tone: str = "info") -> str:
    """Return a small status badge."""
    return f'<span class="status-badge {_esc(tone)}">{_esc(text)}</span>'


def empty_state(
    title: str,
    description: str,
    action_text: str | None = None,
    tone: str = "info",
    badge: str | None = None,
) -> str:
    """Return an empty/blocked state card."""
    badge_html = status_badge(badge, tone) if badge else ""
    action_html = f'<p><strong>{_esc(action_text)}</strong></p>' if action_text else ""
    return (
        f'<div class="empty-state {_esc(tone)}">'
        f'  {badge_html}'
        f'  <h3>{_esc(title)}</h3>'
        f'  <p>{_esc(description)}</p>'
        f'  {action_html}'
        f'</div>'
    )


def data_panel(title: str | None = None, subtitle: str | None = None) -> None:
    """Render a heading block before a table or chart."""
    if not title and not subtitle:
        return
    subtitle_html = f'<p>{_esc(subtitle)}</p>' if subtitle else ""
    st.markdown(
        f'<div class="data-panel-head"><h3>{_esc(title or "")}</h3>{subtitle_html}</div>',
        unsafe_allow_html=True,
    )


def form_panel(title: str | None = None, subtitle: str | None = None) -> None:
    """Render a heading block before a form."""
    if not title and not subtitle:
        return
    subtitle_html = f'<p>{_esc(subtitle)}</p>' if subtitle else ""
    st.markdown(
        f'<div class="form-panel-head"><h3>{_esc(title or "")}</h3>{subtitle_html}</div>',
        unsafe_allow_html=True,
    )


def filter_bar(title: str = "Filtreler", subtitle: str = "") -> None:
    """Render a compact filter toolbar header."""
    subtitle_html = f'<p>{_esc(subtitle)}</p>' if subtitle else ""
    st.markdown(
        f'<div class="filter-bar"><h3>{_esc(title)}</h3>{subtitle_html}</div>',
        unsafe_allow_html=True,
    )


def table_note(text: str) -> None:
    """Render a subtle table note."""
    st.markdown(f'<p class="table-note">{_esc(text)}</p>', unsafe_allow_html=True)


def progress_summary(label: str, percent: float, helper: str = "") -> None:
    """Render a completion progress summary."""
    bounded = max(0.0, min(100.0, float(percent)))
    helper_html = f'<p class="table-note">{_esc(helper)}</p>' if helper else ""
    st.markdown(
        f'<div class="progress-summary">'
        f'  <div class="progress-summary-top"><span>{_esc(label)}</span><span>%{bounded:.0f}</span></div>'
        f'  <div class="progress-track"><div class="progress-fill" style="width:{bounded:.1f}%"></div></div>'
        f'  {helper_html}'
        f'</div>',
        unsafe_allow_html=True,
    )


def render_sidebar_user(full_name: str, role: str) -> None:
    """Render the current user block and logout button in the sidebar."""
    role_label = "Yönetici" if role == "admin" else "Kullanıcı"
    st.sidebar.markdown(
        f'<div class="sidebar-user-card">'
        f'  <div class="sidebar-user-name">{_esc(full_name)}</div>'
        f'  <span class="sidebar-user-role">{_esc(role_label)}</span>'
        f'</div>',
        unsafe_allow_html=True,
    )
    if st.sidebar.button("Çıkış Yap", use_container_width=True, key="sidebar_logout"):
        from sqlalchemy.exc import SQLAlchemyError

        from db.connection import get_session
        from utils.auth import clear_auth_state, logout_user

        try:
            with get_session() as session:
                logout_user(session)
        except SQLAlchemyError:
            clear_auth_state()
        st.rerun()
