"""
Shared UI helpers for the Streamlit portal.

Soft-dark design system. The public API (function names + signatures) is
preserved from the prior light theme so pages keep working unchanged; only
the CSS and the HTML wrappers were rewritten.
"""

from __future__ import annotations

import base64
from html import escape
from pathlib import Path

import streamlit as st


# ---------------------------------------------------------------------------
# Design tokens (soft dark, slate / sky)
# ---------------------------------------------------------------------------
_GLOBAL_CSS = """
<style>
:root {
    --bg:            #F8FAFC;
    --surface:       #FFFFFF;
    --surface-2:     #F1F5F9;
    --surface-3:     #E2E8F0;
    --border:        #CBD5E1;
    --border-soft:   #E2E8F0;
    --text:          #0F172A;
    --text-muted:    #475569;
    --text-faint:    #94A3B8;
    --primary:       #2563EB;
    --primary-soft:  rgba(37, 99, 235, 0.10);
    --primary-line:  rgba(37, 99, 235, 0.30);
    --success:       #16A34A;
    --success-soft:  rgba(22, 163, 74, 0.10);
    --warning:       #D97706;
    --warning-soft:  rgba(217, 119, 6, 0.10);
    --danger:        #DC2626;
    --danger-soft:   rgba(220, 38, 38, 0.10);
    --radius:        10px;
    --radius-sm:     6px;
    --font:          'Inter', system-ui, -apple-system, "Segoe UI", sans-serif;
}

@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

/* ---------- Base ---------- */
html, body, [data-testid="stAppViewContainer"], [data-testid="stApp"] {
    background: var(--bg) !important;
    color: var(--text) !important;
    font-family: var(--font) !important;
    font-size: 15.5px;
}
.block-container {
    padding-top: 2rem !important;
    padding-bottom: 4rem !important;
    max-width: 1280px !important;
}
#MainMenu, footer, [data-testid="stToolbar"], [data-testid="stDecoration"] {
    visibility: hidden;
}
h1, h2, h3, h4, h5, h6 {
    color: var(--text); font-family: var(--font);
    letter-spacing: -0.01em; font-weight: 700;
}
p, span, label, li { color: var(--text); font-weight: 450; }
strong, b { font-weight: 700; }
small, .caption, .stCaption { color: var(--text-muted); }
hr { border-color: var(--border-soft); }
a { color: var(--primary); text-decoration: none; }
a:hover { color: var(--text); }

/* ---------- Sidebar ---------- */
[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #EEF4FB 0%, #E5EEF8 100%) !important;
    border-right: 1px solid #D8E4F2 !important;
}
[data-testid="stSidebar"] * { color: var(--text); }

/* Streamlit'in otomatik (pages/ klasör tabanlı) sidebar nav'ını gizle.
   st.navigation hâlâ routing yapıyor, biz aşağıda elle st.page_link
   listesi çiziyoruz; aynı linklerin iki kez görünmesini engelliyoruz. */
[data-testid="stSidebar"] [data-testid="stSidebarNav"] {
    display: none !important;
}

/* Sidebar'ı sabit aç tut — gizleme butonu yok. Kullanıcılar kapatıp
   açamasın, hep aynı yerde kalsın. (845d40b'de çalışan orijinal
   yapı; sonradan "savaş" diye sadeleştirmeye kalkıştım, sidebar tamamen
   kayboldu — geri getirdim.) */
[data-testid="stSidebar"] {
    min-width: 230px !important;
    max-width: 230px !important;
    width: 230px !important;
    transform: translateX(0) !important;
    visibility: visible !important;
}
/* Sadece KAPATMA butonunu gizle (sidebar açıkken görünen `<` oku).
   AÇMA butonu (stSidebarCollapsedControl — sidebar kapalıyken görünen
   `>` oku) görünür kalsın: eğer Streamlit veya kullanıcı bir şekilde
   sidebar'ı kapatırsa, geri açabilsin. */
[data-testid="stSidebarCollapseButton"],
[aria-label="Close sidebar"],
[aria-label="Collapse sidebar"],
button[kind="header"][data-testid="baseButton-header"] {
    display: none !important;
}
/* Aç butonu görünürlüğü güçlendir — Streamlit bazen z-index ile
   kaybediyor. */
[data-testid="stSidebarCollapsedControl"],
[data-testid="collapsedControl"] {
    display: flex !important;
    visibility: visible !important;
    opacity: 1 !important;
    z-index: 1000 !important;
    pointer-events: auto !important;
}

/* Brand card sits at the natural top of the sidebar now that we
   render the page-link nav ourselves below it (no Streamlit auto-nav
   to fight). Just a clean header with bottom divider. */
.sidebar-brand-card {
    display: flex; align-items: center; gap: 0.75rem;
    padding: 1.1rem 0.9rem 1rem;
    border-bottom: 1px solid var(--border-soft);
    margin: 0 -1rem 0.5rem;
}

/* Manual page-link nav section */
.sidebar-nav-section {
    display: flex; flex-direction: column; gap: 0.15rem;
    margin: 0.5rem 0 1rem;
}
[data-testid="stSidebar"] [data-testid="stPageLink-NavLink"] {
    color: var(--text-muted) !important;
    border-radius: var(--radius-sm) !important;
    padding: 0.55rem 0.85rem !important;
    text-decoration: none !important;
    font-size: 0.92rem !important;
    transition: background 0.15s ease, color 0.15s ease;
}
[data-testid="stSidebar"] [data-testid="stPageLink-NavLink"]:hover {
    background: var(--surface) !important;
    color: var(--text) !important;
}
[data-testid="stSidebar"] [data-testid="stPageLink-NavLink"][aria-current="page"],
[data-testid="stSidebar"] [data-testid="stPageLink-NavLink"].active {
    background: var(--primary-soft) !important;
    color: var(--primary) !important;
    font-weight: 600;
}
.sidebar-brand-logo { width: 38px; height: 38px; border-radius: 9px; background: var(--surface-2); padding: 4px; }
.sidebar-brand-title {
    font-weight: 700; font-size: 0.85rem; letter-spacing: 0.08em; color: var(--text);
}
.sidebar-brand-subtitle { font-size: 0.72rem; color: var(--text-muted); }

.sidebar-user-card {
    background: var(--surface);
    border: 1px solid var(--border-soft);
    border-radius: var(--radius-sm);
    padding: 0.75rem 0.85rem;
    margin: 0.75rem 0 0.5rem;
}
.sidebar-user-name { font-weight: 600; font-size: 0.9rem; color: var(--text); }
.sidebar-user-role {
    display: inline-block; margin-top: 0.35rem;
    background: var(--primary-soft); color: var(--primary);
    border-radius: 999px; padding: 0.15rem 0.55rem;
    font-size: 0.7rem; font-weight: 600;
}

/* Sidebar navigation links rendered by st.navigation */
[data-testid="stSidebarNavItems"] a,
section[data-testid="stSidebar"] a[data-testid^="stPageLink"] {
    color: var(--text-muted) !important;
    border-radius: var(--radius-sm) !important;
    padding: 0.55rem 0.85rem !important;
}
[data-testid="stSidebarNavItems"] a:hover,
section[data-testid="stSidebar"] a[data-testid^="stPageLink"]:hover {
    background: var(--surface) !important;
    color: var(--text) !important;
}
[data-testid="stSidebarNavItems"] a[aria-current="page"],
section[data-testid="stSidebar"] a[aria-current="page"] {
    background: var(--primary-soft) !important;
    color: var(--primary) !important;
    font-weight: 600;
}

/* ---------- Inputs ---------- */
[data-baseweb="input"] > div, [data-baseweb="select"] > div,
.stTextInput input, .stNumberInput input, .stDateInput input, .stTimeInput input,
.stSelectbox div[role="combobox"], .stTextArea textarea {
    background: var(--surface) !important;
    border: 1px solid var(--border) !important;
    border-radius: var(--radius-sm) !important;
    color: var(--text) !important;
}
.stTextInput input::placeholder, .stNumberInput input::placeholder,
.stTextArea textarea::placeholder { color: var(--text-faint) !important; }
[data-baseweb="input"]:focus-within > div, [data-baseweb="select"]:focus-within > div {
    border-color: var(--primary) !important;
    box-shadow: 0 0 0 3px var(--primary-soft) !important;
}
/* Hide the "Press Enter to submit form" hint that Streamlit overlays
   on focused inputs — it overlaps long values and looks broken. */
[data-testid="InputInstructions"],
[data-testid="stWidgetInstructions"] {
    display: none !important;
}

/* Number input: hide the +/- spinner buttons so the field reads as a
   single clean cell. Operators on the floor will type the number. */
.stNumberInput button,
.stNumberInput [data-testid="stNumberInputStepDown"],
.stNumberInput [data-testid="stNumberInputStepUp"] {
    display: none !important;
}
/* Sade dikdörtgen kutu — sadece DIŞ wrapper'a çerçeve uygula. İç
   input element'ine ayrıca border vermiyoruz; iç içe iki çerçeve
   "çift çizgi" görünümüne sebep oluyordu. */
.stNumberInput [data-baseweb="input"] > div {
    border: 1px solid var(--border) !important;
    border-radius: var(--radius-sm) !important;
    background: var(--surface) !important;
    padding: 0.5rem 0.65rem !important;
}
.stNumberInput input {
    border: none !important;
    background: transparent !important;
    box-shadow: none !important;
    outline: none !important;
    font-size: 1rem !important;
    text-align: center !important;
    color: var(--text) !important;
    padding: 0 !important;
}
.stNumberInput [data-baseweb="input"] {
    width: 100% !important;
}
.stNumberInput:focus-within [data-baseweb="input"] > div {
    border-color: var(--primary) !important;
    box-shadow: 0 0 0 2px var(--primary-soft) !important;
}
.stNumberInput [data-baseweb="input"][aria-disabled="true"] > div {
    background: var(--surface-2) !important;
}
.stNumberInput input:disabled {
    color: var(--text-faint) !important;
}

/* Sayım sayfasındaki bilgi satırı (tonaj hedefi + yetkili notu) */
.dept-meta-row {
    display: flex; gap: 1.5rem; flex-wrap: wrap;
    padding: 0.75rem 0;
    border-bottom: 1px solid var(--border-soft);
    margin: 0.25rem 0 1.25rem;
    font-size: 0.85rem;
    color: var(--text-muted);
}
.dept-meta-row strong { color: var(--text); font-weight: 600; }
.dept-meta-row .meta-warn { color: var(--warning); }
.dept-meta-row .meta-warn::before { content: "⚠ "; }

/* Renk tablosu: başlık satırı vurgulu, satırlar hafif vurgulu */
.color-table-caption {
    background: var(--surface-2);
    border: 1px solid var(--border-soft);
    border-radius: var(--radius-sm);
    padding: 0.85rem 1rem;
    margin: 0.5rem 0 1rem;
    color: var(--text-muted); font-size: 0.88rem; line-height: 1.55;
}
.color-table-caption strong { color: var(--text); }

.example-grid {
    margin-top: 0.75rem;
    padding-top: 0.75rem;
    border-top: 1px solid var(--border-soft);
    display: flex; flex-direction: column; gap: 0.85rem;
}
/* Her örnek (satır + açıklama) ayrı bir blok */
.example-block {
    background: var(--surface);
    border: 1px solid var(--border-soft);
    border-radius: var(--radius-sm);
    padding: 0.7rem 0.85rem;
}
.example-row {
    display: flex; flex-wrap: wrap; gap: 0.5rem;
    align-items: center;
}
.example-row .ex-label {
    color: var(--primary); font-size: 0.7rem; font-weight: 700;
    letter-spacing: 0.12em; text-transform: uppercase;
    margin-right: 0.4rem;
}
.example-row .ex-cell {
    background: var(--surface-2);
    border: 1px solid var(--border-soft);
    border-radius: var(--radius-sm);
    padding: 0.4rem 0.7rem;
    display: flex; flex-direction: column; gap: 0.1rem;
    text-align: center;
    min-width: 80px;
}
.example-row .ex-cell b {
    color: var(--text); font-size: 1.05rem; font-weight: 700;
}
.example-row .ex-cell small {
    color: var(--text-muted); font-size: 0.7rem;
}
.example-note {
    margin-top: 0.55rem;
    font-size: 0.82rem;
    line-height: 1.45;
    padding: 0.5rem 0.7rem;
    border-radius: var(--radius-sm);
    border-left: 3px solid;
}
.example-note--include {
    background: var(--success-soft);
    border-left-color: var(--success);
    color: #065F46;
}
.example-note--include strong { color: var(--success); font-weight: 700; }
.example-note--exclude {
    background: var(--danger-soft);
    border-left-color: var(--danger);
    color: #991B1B;
}
.example-note--exclude strong { color: var(--danger); font-weight: 700; }
.color-table-head {
    color: var(--text-muted) !important;
    font-size: 0.78rem !important;
    font-weight: 600 !important;
    letter-spacing: 0.04em;
    text-transform: uppercase;
    padding-bottom: 0.4rem;
    border-bottom: 1px solid var(--border-soft);
}
.stSelectbox div[role="listbox"], [data-baseweb="popover"] div[role="listbox"] {
    background: var(--surface-2) !important; border: 1px solid var(--border) !important;
}
[data-baseweb="popover"] li:hover { background: var(--surface-3) !important; }

/* Labels above inputs */
.stTextInput label, .stNumberInput label, .stSelectbox label,
.stDateInput label, .stTimeInput label, .stRadio label, .stCheckbox label,
.stTextArea label {
    color: var(--text-muted) !important;
    font-weight: 500 !important;
    font-size: 0.85rem !important;
}

/* ---------- Buttons ---------- */
.stButton > button, .stDownloadButton > button, .stFormSubmitButton > button {
    background: var(--surface-2);
    color: var(--text);
    border: 1px solid var(--border);
    border-radius: var(--radius-sm);
    padding: 0.55rem 1rem;
    font-weight: 500;
    transition: all 0.15s ease;
}
.stButton > button:hover, .stDownloadButton > button:hover, .stFormSubmitButton > button:hover {
    background: var(--surface-3);
    border-color: var(--primary-line);
    color: var(--text);
}
.stButton > button[kind="primary"], .stFormSubmitButton > button[kind="primary"] {
    background: var(--primary);
    color: #FFFFFF;
    border-color: var(--primary);
    font-weight: 600;
}
.stButton > button[kind="primary"]:hover, .stFormSubmitButton > button[kind="primary"]:hover {
    background: #1D4ED8;
    border-color: #1D4ED8;
    color: #FFFFFF;
}
.stButton > button:disabled, .stFormSubmitButton > button:disabled {
    background: var(--surface) !important;
    color: var(--text-faint) !important;
    border-color: var(--border-soft) !important;
}

/* ---------- Tables / DataFrames ---------- */
[data-testid="stDataFrame"], [data-testid="stTable"] {
    background: var(--surface) !important;
    border: 1px solid var(--border-soft) !important;
    border-radius: var(--radius) !important;
    overflow: hidden;
}
[data-testid="stDataFrame"] table, [data-testid="stTable"] table { background: var(--surface) !important; }
[data-testid="stDataFrame"] th, [data-testid="stTable"] th {
    background: var(--surface-2) !important;
    color: var(--text-muted) !important;
    font-weight: 600 !important;
    border-color: var(--border-soft) !important;
}
[data-testid="stDataFrame"] td, [data-testid="stTable"] td {
    color: var(--text) !important;
    border-color: var(--border-soft) !important;
}

/* ---------- Streamlit-native widgets ---------- */
[data-testid="stMetric"] {
    background: var(--surface);
    border: 1px solid var(--border-soft);
    border-radius: var(--radius);
    padding: 1rem 1.1rem;
}
[data-testid="stMetricLabel"] { color: var(--text-muted) !important; }
[data-testid="stMetricValue"] { color: var(--text) !important; font-weight: 700 !important; }
[data-testid="stMetricDelta"] { color: var(--success) !important; }

[data-testid="stExpander"] {
    background: var(--surface);
    border: 1px solid var(--border-soft);
    border-radius: var(--radius);
}
[data-testid="stExpander"] summary { color: var(--text); }

[data-testid="stTabs"] button[role="tab"] {
    color: var(--text-muted);
    background: transparent;
    border: none;
    padding: 0.6rem 1rem;
}
[data-testid="stTabs"] button[role="tab"][aria-selected="true"] {
    color: var(--primary) !important;
    border-bottom: 2px solid var(--primary) !important;
}

[data-testid="stAlert"], .stAlert {
    background: var(--surface) !important;
    border: 1px solid var(--border-soft) !important;
    border-left: 3px solid var(--primary) !important;
    border-radius: var(--radius-sm) !important;
    color: var(--text) !important;
}
[data-testid="stAlert"][data-baseweb="notification"][kind="success"] { border-left-color: var(--success) !important; }
[data-testid="stAlert"][data-baseweb="notification"][kind="warning"] { border-left-color: var(--warning) !important; }
[data-testid="stAlert"][data-baseweb="notification"][kind="error"] { border-left-color: var(--danger) !important; }

/* Form container */
[data-testid="stForm"] {
    background: var(--surface);
    border: 1px solid var(--border-soft);
    border-radius: var(--radius);
    padding: 1.5rem;
}

/* ---------- Custom components ---------- */
.norm-header {
    display: flex; flex-direction: column; gap: 0.35rem;
    padding: 0.5rem 0 1rem;
    border-bottom: 1px solid var(--border-soft);
    margin-bottom: 1.5rem;
}
.norm-header h1 { font-size: 1.6rem; font-weight: 700; margin: 0; color: var(--text); }
.norm-header p { color: var(--text-muted); margin: 0; font-size: 0.95rem; }
.norm-header-meta { display: flex; gap: 0.4rem; margin-top: 0.6rem; flex-wrap: wrap; }
.norm-header-badge {
    background: var(--surface);
    border: 1px solid var(--border-soft);
    color: var(--text-muted);
    border-radius: 999px;
    padding: 0.2rem 0.7rem;
    font-size: 0.72rem;
    font-weight: 500;
}
.norm-header-badge.success { color: var(--success); border-color: var(--success); background: var(--success-soft); }
.norm-header-badge.warning { color: var(--warning); border-color: var(--warning); background: var(--warning-soft); }
.norm-header-badge.danger  { color: var(--danger);  border-color: var(--danger);  background: var(--danger-soft); }
.norm-header-badge.info    { color: var(--primary); border-color: var(--primary-line); background: var(--primary-soft); }

.section-header {
    display: flex; align-items: baseline; justify-content: space-between;
    margin: 1.5rem 0 0.75rem;
}
.section-header span { font-weight: 600; font-size: 1rem; color: var(--text); }
.section-header small { color: var(--text-muted); font-size: 0.8rem; }

.section-gap { height: 0.5rem; }

/* Hero (dashboard) — simple flat card, no gradient */
.dashboard-hero {
    border-bottom: 1px solid var(--border-soft);
    padding: 0.5rem 0 1.5rem;
    display: flex; flex-direction: column; gap: 0.6rem;
    margin-bottom: 1rem;
}
.dashboard-eyebrow {
    color: var(--text-muted);
    font-size: 0.7rem;
    letter-spacing: 0.14em;
    font-weight: 600;
    text-transform: uppercase;
}
.dashboard-hero h1 {
    font-size: 1.6rem; font-weight: 600; margin: 0; color: var(--text);
    letter-spacing: -0.015em;
}
.dashboard-hero p { color: var(--text-muted); font-size: 0.92rem; max-width: 720px; margin: 0; line-height: 1.5; }
.dashboard-hero-badges {
    display: flex; gap: 1.5rem; margin-top: 0.6rem; flex-wrap: wrap;
}
.hero-badge {
    display: flex; flex-direction: column; gap: 0.15rem;
}
.hero-badge span { color: var(--text-muted); font-size: 0.72rem; }
.hero-badge strong { color: var(--text); font-size: 0.95rem; font-weight: 600; }

/* KPI cards — minimal: label + value, no icons */
.kpi-card {
    background: var(--surface);
    border: 1px solid var(--border-soft);
    border-radius: var(--radius);
    padding: 0.95rem 1.1rem;
    display: flex; flex-direction: column; gap: 0.35rem;
    height: 100%;
}
.kpi-card-top { display: flex; align-items: center; }
.kpi-label { color: var(--text-muted); font-size: 0.78rem; font-weight: 500; }
.kpi-icon { display: none; }
.kpi-value { color: var(--text); font-size: 1.4rem; font-weight: 600; line-height: 1.2; }
.kpi-card-bottom { display: flex; justify-content: space-between; align-items: end; gap: 0.5rem; }
.kpi-sub { color: var(--text-faint); font-size: 0.76rem; line-height: 1.35; }
.kpi-delta { font-size: 0.76rem; font-weight: 600; }
.kpi-delta.positive { color: var(--success); }
.kpi-delta.negative { color: var(--danger); }
.kpi-delta.neutral  { color: var(--text-muted); }

/* Status panel */
.status-panel {
    background: var(--surface);
    border: 1px solid var(--border-soft);
    border-left: 3px solid var(--primary);
    border-radius: var(--radius);
    padding: 1.15rem 1.25rem;
}
.status-panel-success { border-left-color: var(--success); }
.status-panel-warning { border-left-color: var(--warning); }
.status-panel-danger,
.status-panel-locked  { border-left-color: var(--danger); }
.status-panel-info,
.status-panel-open    { border-left-color: var(--primary); }
.status-panel-late    { border-left-color: var(--warning); }
.status-panel-top {
    display: flex; justify-content: space-between; align-items: center;
    margin-bottom: 0.5rem;
}
.status-panel-top span { color: var(--text-muted); font-size: 0.7rem; letter-spacing: 0.1em; text-transform: uppercase; }
.status-panel-top strong { color: var(--text); font-size: 0.78rem; font-weight: 600; }
.status-panel h4 { font-size: 1.05rem; margin: 0 0 0.3rem; color: var(--text); }
.status-panel p { color: var(--text-muted); margin: 0; font-size: 0.88rem; line-height: 1.5; }
.status-panel-items { margin-top: 0.7rem; display: flex; flex-direction: column; gap: 0.3rem; }
.status-panel-items small { color: var(--text-muted); font-size: 0.78rem; }
.status-panel-items strong { color: var(--text); }
.status-panel-footer {
    display: flex; justify-content: space-between; align-items: center;
    margin-top: 0.85rem; padding-top: 0.75rem;
    border-top: 1px solid var(--border-soft);
}
.status-panel-footer small { color: var(--text-faint); font-size: 0.72rem; }
.status-panel-action {
    color: var(--primary); font-size: 0.82rem; font-weight: 600;
    background: var(--primary-soft); padding: 0.35rem 0.8rem;
    border-radius: 999px; border: 1px solid var(--primary-line);
}
.status-panel-action:hover { background: var(--primary); color: #FFFFFF; }

/* Timeline (weekly flow) */
.flow-panel {
    background: var(--surface);
    border: 1px solid var(--border-soft);
    border-radius: var(--radius);
    padding: 1.15rem 1.25rem;
    display: flex; flex-direction: column; gap: 0.85rem;
}
.flow-step { display: flex; align-items: flex-start; gap: 0.75rem; }
.flow-step span {
    flex-shrink: 0;
    width: 26px; height: 26px;
    border-radius: 50%;
    background: var(--primary-soft);
    color: var(--primary);
    font-weight: 700; font-size: 0.78rem;
    display: flex; align-items: center; justify-content: center;
}
.flow-step strong { display: block; color: var(--text); font-size: 0.88rem; font-weight: 600; }
.flow-step small { color: var(--text-muted); font-size: 0.78rem; line-height: 1.4; }

/* Process diagram — 3 yatay adım, şu anki adım vurgulu */
.process-diagram {
    display: grid;
    grid-template-columns: 1fr auto 1fr auto 1fr;
    gap: 0;
    align-items: stretch;
    background: var(--surface);
    border: 1px solid var(--border-soft);
    border-radius: var(--radius);
    padding: 1.5rem 1.25rem;
}
@media (max-width: 720px) {
    .process-diagram { grid-template-columns: 1fr; }
    .process-arrow { display: none; }
}
.process-step {
    display: flex; flex-direction: column; align-items: center; gap: 0.5rem;
    padding: 0.85rem 0.75rem;
    border-radius: var(--radius);
    text-align: center;
    border: 1px solid transparent;
    transition: all 0.15s ease;
}
.process-step .icon {
    width: 48px; height: 48px;
    border-radius: 50%;
    background: var(--surface-2);
    color: var(--text-muted);
    display: flex; align-items: center; justify-content: center;
    font-size: 1.4rem; font-weight: 700;
    border: 2px solid var(--border);
}
.process-step .label {
    color: var(--text-muted); font-size: 0.95rem; font-weight: 600;
}
.process-step .when {
    color: var(--text-faint); font-size: 0.8rem;
}
.process-step .badge {
    display: inline-block;
    padding: 0.15rem 0.6rem;
    border-radius: 999px;
    font-size: 0.68rem; font-weight: 700;
    letter-spacing: 0.08em; text-transform: uppercase;
    background: transparent; color: var(--text-faint);
    border: 1px solid var(--border);
    margin-top: 0.15rem;
}
/* Past step — muted, tamamlandı */
.process-step.is-done .icon {
    background: var(--surface-2); color: var(--text-muted);
    border-color: var(--border);
}
.process-step.is-done .label  { color: var(--text-muted); }
.process-step.is-done .badge  { color: var(--text-faint); }
/* Active step — büyük ve renkli */
.process-step.is-active {
    background: var(--primary-soft);
    border-color: var(--primary-line);
}
.process-step.is-active .icon {
    background: var(--primary); color: #FFFFFF;
    border-color: var(--primary);
    box-shadow: 0 0 0 6px var(--primary-soft);
}
.process-step.is-active .label { color: var(--text); font-size: 1rem; }
.process-step.is-active .badge {
    background: var(--primary); color: #FFFFFF;
    border-color: var(--primary);
}
/* Active "geç giriş" varyantı — sarı */
.process-step.is-active.is-late {
    background: var(--warning-soft);
    border-color: var(--warning);
}
.process-step.is-active.is-late .icon {
    background: var(--warning); color: #FFFFFF;
    border-color: var(--warning);
    box-shadow: 0 0 0 6px var(--warning-soft);
}
.process-step.is-active.is-late .badge {
    background: var(--warning); color: #FFFFFF;
    border-color: var(--warning);
}
/* Future step — soluk, henüz gelmedi */
.process-step.is-future .icon {
    background: transparent; color: var(--text-faint);
    border-style: dashed;
}
.process-step.is-future .label { color: var(--text-faint); }

.process-arrow {
    display: flex; align-items: center; justify-content: center;
    color: var(--text-faint); font-size: 1.1rem;
    padding: 0 0.4rem;
}

/* Quick action cards — flat, no transforms */
.qa-card {
    display: flex; flex-direction: column; gap: 0.35rem;
    background: var(--surface);
    border: 1px solid var(--border-soft);
    border-radius: var(--radius);
    padding: 1rem 1.1rem;
    text-decoration: none !important;
    height: 100%;
}
.qa-card:hover { border-color: var(--primary-line); background: var(--surface-2); }
.qa-icon { display: none; }
.qa-title { color: var(--text); font-weight: 600; font-size: 0.95rem; }
.qa-desc  { color: var(--text-muted); font-size: 0.8rem; line-height: 1.4; }
.qa-cta   { color: var(--primary); font-size: 0.78rem; font-weight: 500; margin-top: 0.5rem; }

/* Status badges & pills */
.status-badge, .status-pill {
    display: inline-flex; align-items: center; gap: 0.3rem;
    border-radius: 999px;
    padding: 0.2rem 0.65rem;
    font-size: 0.72rem;
    font-weight: 600;
    border: 1px solid var(--border-soft);
    background: var(--surface);
    color: var(--text-muted);
}
.status-badge.success, .status-pill.status-open    { background: var(--success-soft); color: var(--success); border-color: var(--success); }
.status-badge.warning, .status-pill.status-late    { background: var(--warning-soft); color: var(--warning); border-color: var(--warning); }
.status-badge.danger,  .status-pill.status-locked  { background: var(--danger-soft);  color: var(--danger);  border-color: var(--danger); }
.status-badge.info                                  { background: var(--primary-soft); color: var(--primary); border-color: var(--primary-line); }

/* Empty state */
.empty-state {
    background: var(--surface);
    border: 1px dashed var(--border);
    border-radius: var(--radius);
    padding: 2rem 1.5rem;
    text-align: center;
    display: flex; flex-direction: column; gap: 0.5rem; align-items: center;
}
.empty-state h3 { color: var(--text); margin: 0; font-size: 1.05rem; }
.empty-state p  { color: var(--text-muted); font-size: 0.88rem; margin: 0; max-width: 480px; }
.empty-state.warning { border-color: var(--warning); }
.empty-state.danger  { border-color: var(--danger); }

/* Headings used before tables / forms / filter bars */
.data-panel-head, .form-panel-head, .filter-bar {
    display: flex; flex-direction: column; gap: 0.2rem;
    margin: 0.5rem 0 0.85rem;
    padding: 0.75rem 0;
    border-bottom: 1px solid var(--border-soft);
}
.data-panel-head h3, .form-panel-head h3, .filter-bar h3 {
    color: var(--text); font-size: 1rem; font-weight: 600; margin: 0;
}
.data-panel-head p, .form-panel-head p, .filter-bar p {
    color: var(--text-muted); font-size: 0.82rem; margin: 0;
}

.table-note { color: var(--text-faint); font-size: 0.78rem; margin: 0.4rem 0 0; }

/* Progress summary */
.progress-summary { display: flex; flex-direction: column; gap: 0.4rem; margin: 0.4rem 0; }
.progress-summary-top { display: flex; justify-content: space-between; align-items: center; }
.progress-summary-top span { color: var(--text-muted); font-size: 0.85rem; font-weight: 500; }
.progress-summary-top span:last-child { color: var(--text); font-weight: 700; }
.progress-track { height: 6px; background: var(--surface-2); border-radius: 3px; overflow: hidden; }
.progress-fill { height: 100%; background: var(--primary); border-radius: 3px; transition: width 0.4s ease; }

/* ---------- Login screen — full-bleed soft gradient, single centered column ---------- */
[data-testid="stAppViewContainer"]:has(.login-brand-pane) {
    background:
        radial-gradient(ellipse 90% 70% at 80% 0%, rgba(37, 99, 235, 0.10) 0%, transparent 55%),
        radial-gradient(ellipse 80% 80% at 10% 100%, rgba(37, 99, 235, 0.06) 0%, transparent 60%),
        linear-gradient(160deg, #F8FAFC 0%, #EEF2F7 100%) !important;
}
/* Center the middle column vertically on the page so the whole stack
   (brand block + form + footer) sits in the visual middle. */
[data-testid="stAppViewContainer"]:has(.login-brand-pane) [data-testid="stHorizontalBlock"],
[data-testid="stAppViewContainer"]:has(.login-brand-pane) [data-testid="horizontalBlock"] {
    min-height: 88vh !important;
    align-items: center !important;
}
[data-testid="stAppViewContainer"]:has(.login-brand-pane) [data-testid="column"],
[data-testid="stAppViewContainer"]:has(.login-brand-pane) [data-testid="stColumn"],
[data-testid="stAppViewContainer"]:has(.login-brand-pane) div[class*="stColumn"] {
    display: flex !important;
    flex-direction: column !important;
    justify-content: center !important;
}

.login-brand-pane {
    position: relative;
    padding: 0 0 1.5rem;
    margin-bottom: 1.5rem;
    text-align: center;
    display: flex; flex-direction: column; align-items: center;
}

/* Faint grid pattern only over the brand pane */
.login-brand-pane::before {
    content: ""; position: absolute; inset: 0;
    background-image:
        linear-gradient(rgba(37, 99, 235, 0.06) 1px, transparent 1px),
        linear-gradient(90deg, rgba(37, 99, 235, 0.06) 1px, transparent 1px);
    background-size: 32px 32px;
    pointer-events: none;
    mask-image: radial-gradient(ellipse at center, black 25%, transparent 85%);
}
.login-brand-pane > * { position: relative; z-index: 1; }

.login-brand-mark {
    display: inline-flex; align-items: center; gap: 0.7rem;
    color: var(--text); font-weight: 700;
    letter-spacing: 0.18em; text-transform: uppercase; font-size: 0.85rem;
    margin-bottom: 1.5rem;
}
.login-brand-mark img {
    width: 44px; height: 44px; border-radius: 10px;
    background: var(--surface); padding: 5px;
    border: 1px solid var(--border-soft);
}

.login-brand-eyebrow {
    color: var(--primary);
    letter-spacing: 0.22em; text-transform: uppercase;
    font-size: 0.74rem; font-weight: 600;
    margin-bottom: 0.85rem;
}
.login-brand-instruction {
    color: var(--text-muted); font-size: 0.95rem; font-weight: 400;
    line-height: 1.55; max-width: 36ch;
    margin: 0 auto;
}

/* Form footer — security badge + copyright row */
.login-form-foot {
    margin-top: 1.25rem; padding-top: 1rem;
    border-top: 1px solid var(--border-soft);
    display: flex; justify-content: space-between; align-items: center;
    color: var(--text-faint); font-size: 0.72rem;
}
.login-form-foot .badge {
    display: inline-flex; align-items: center; gap: 0.4rem;
    color: var(--text-muted);
}
.login-form-foot .badge::before {
    content: "🔒"; filter: grayscale(0.5);
}

/* Tonaj giriş alanı — sayım formundaki tek-değer kritik input.
   :has() ile sadece aria-label'ında "tonaj" geçen input'u yakalayıp
   etrafındaki dış wrapper'a vurgu veriyoruz. Ayrı div sarmaya gerek
   yok (Streamlit input'u markdown'la sardığında kart boş kalıyordu). */
[data-testid="stForm"] .stNumberInput:has(input[aria-label*="tonaj"]) [data-baseweb="input"] > div,
[data-testid="stForm"] .stNumberInput:has(input[aria-label*="Tonaj"]) [data-baseweb="input"] > div {
    border: 2px solid var(--primary) !important;
    background: #FAFCFF !important;
    box-shadow: 0 2px 6px rgba(37, 99, 235, 0.08) !important;
    padding: 0.85rem 1rem !important;
}
[data-testid="stForm"] .stNumberInput:has(input[aria-label*="tonaj"]) input,
[data-testid="stForm"] .stNumberInput:has(input[aria-label*="Tonaj"]) input {
    font-size: 1.35rem !important;
    font-weight: 700 !important;
    background: transparent !important;
}
[data-testid="stForm"] .stNumberInput:has(input[aria-label*="tonaj"]) label,
[data-testid="stForm"] .stNumberInput:has(input[aria-label*="Tonaj"]) label {
    font-size: 0.95rem !important;
    font-weight: 600 !important;
    color: var(--primary) !important;
    margin-bottom: 0.4rem !important;
}

/* Süreç diyagramı başlığı + sağ üstte "şu an X. adım" badge'i */
/* İki durumlu (Sayım Açık / Sayım Kapalı) diyagramda ortalı + yan yana */
.process-diagram--two-state {
    display: grid !important;
    grid-template-columns: 1fr 1fr;
    gap: 1rem;
}
.process-header {
    display: flex; align-items: flex-end; justify-content: space-between;
    gap: 1rem; margin-bottom: 0.85rem;
}
.process-header-titles { display: flex; flex-direction: column; gap: 0.15rem; }
.process-header-titles .section-header-title {
    font-size: 1.05rem; font-weight: 700; color: var(--text);
}
.process-header-titles .section-header-sub {
    font-size: 0.82rem; color: var(--text-muted);
}
.process-current-step {
    display: inline-flex; align-items: center; gap: 0.4rem;
    padding: 0.5rem 0.85rem;
    border-radius: 999px;
    font-size: 0.85rem; font-weight: 600;
    border: 1.5px solid;
    white-space: nowrap;
}
.process-current-step--success {
    background: var(--success-soft); color: var(--success);
    border-color: var(--success);
}
.process-current-step--warning {
    background: var(--warning-soft); color: var(--warning);
    border-color: var(--warning);
}
.process-current-step--info {
    background: var(--surface-2); color: var(--text-muted);
    border-color: var(--border);
}

/* Login error banner — formun üstünde, dikkat çekici kırmızı kart */
.login-error-banner {
    display: flex; align-items: flex-start; gap: 0.7rem;
    margin: 0 auto 1rem auto;
    padding: 0.85rem 1rem;
    background: var(--danger-soft);
    border: 1px solid var(--danger);
    border-left: 4px solid var(--danger);
    border-radius: var(--radius);
    color: var(--danger);
    font-size: 0.9rem; font-weight: 500;
    box-shadow: 0 4px 14px rgba(220, 38, 38, 0.18);
    animation: login-error-pop 0.25s ease-out;
}
.login-error-banner .login-error-icon {
    font-size: 1.05rem; line-height: 1.3;
}
.login-error-banner .login-error-text {
    color: #991B1B; line-height: 1.4;
}
@keyframes login-error-pop {
    from { opacity: 0; transform: translateY(-6px); }
    to   { opacity: 1; transform: translateY(0); }
}

</style>
"""


def _esc(value: object) -> str:
    """Escape text before injecting it into controlled HTML snippets."""
    return escape(str(value), quote=True)


def queue_toast(message: str, icon: str = "✅") -> None:
    """Queue a toast that will fire on the next page render.

    `st.toast` followed by `st.rerun` often loses the toast because the
    rerun cancels the in-flight render. Persist it via session_state and
    `flush_pending_toasts()` reads it back on the next run.
    """
    bucket = st.session_state.setdefault("pending_toasts", [])
    bucket.append({"message": message, "icon": icon})


def flush_pending_toasts() -> None:
    """Render any toasts queued with `queue_toast` and clear the bucket."""
    bucket = st.session_state.pop("pending_toasts", None)
    if not bucket:
        return
    for entry in bucket:
        st.toast(entry["message"], icon=entry.get("icon"))


def _with_session_token(href: str) -> str:
    """Append the current ?s=<token> to an internal href so top-level
    navigation (raw <a> in custom cards) doesn't drop the auth token and
    bounce the user to login on arrival.
    """
    if not href or "://" in href or href.startswith("#"):
        return href
    try:
        token = st.query_params.get("s")
    except Exception:
        token = None
    if not token:
        return href
    sep = "&" if "?" in href else "?"
    return f"{href}{sep}s={token}"


def inject_css() -> None:
    """Inject the global design system stylesheet."""
    st.markdown(_GLOBAL_CSS, unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Logo helpers
# ---------------------------------------------------------------------------
@st.cache_data(show_spinner=False)
def _logo_data_uri(logo_path_str: str) -> str:
    """Read logo from disk once per session and return a data: URI (or empty)."""
    logo = Path(logo_path_str)
    if not logo.exists():
        return ""
    return f"data:image/png;base64,{base64.b64encode(logo.read_bytes()).decode()}"


def render_sidebar_brand(logo_path: str | Path) -> None:
    """Render the Norm Fasteners brand card in the sidebar."""
    data_uri = _logo_data_uri(str(logo_path))
    logo_html = (
        f'<img src="{data_uri}" alt="Norm Fasteners" class="sidebar-brand-logo">'
        if data_uri
        else ""
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


# ---------------------------------------------------------------------------
# Page-level layout components
# ---------------------------------------------------------------------------
def page_header(
    title: str,
    subtitle: str = "",
    icon: str = "",
    badges: list[tuple[str, str]] | None = None,
    meta: str | None = None,
) -> None:
    """Render a consistent page header."""
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
        f'<div class="norm-header"><h1>{_esc(title)}</h1>{sub_html}{badge_html}</div>',
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
        f'  <div class="dashboard-eyebrow">Norm Fasteners · Konteyner Operasyonları</div>'
        f'  <h1>{_esc(title)}</h1>'
        f'  <p>{_esc(subtitle)}</p>'
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


# ---------------------------------------------------------------------------
# KPI cards
# ---------------------------------------------------------------------------
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


# ---------------------------------------------------------------------------
# Status / flow / quick actions
# ---------------------------------------------------------------------------
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
        f'<a class="status-panel-action" href="{_esc(_with_session_token(cta_href))}" target="_self">{_esc(cta_label)}</a>'
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


def process_diagram(status: str, schedule_human: str = "") -> str:
    """2-state horizontal indicator for the weekly submission cycle.

    Just the two states that matter to the user: **Sayım Açık** vs
    **Sayım Kapalı**. The current state is highlighted; the other is
    muted. Late state (admin-opened) is treated as "Açık" here — the
    user-facing diagram does not surface the late distinction.

    ``status`` values: ``"open"``, ``"late"``, ``"locked"``.
    ``schedule_human`` (optional) such as ``"Pazartesi 09:00–12:00"``;
    falls back to a generic label when empty.
    """
    if status in ("open", "late"):
        cls_open = "process-step is-active"
        cls_closed = "process-step is-future"
        badge_open = "Şu an"
        badge_closed = ""
    else:  # locked
        cls_open = "process-step is-future"
        cls_closed = "process-step is-active"
        badge_open = ""
        badge_closed = "Şu an"

    when_open = schedule_human if schedule_human else "Pencere içinde"
    when_closed = (
        f"{schedule_human} dışında" if schedule_human else "Pencere dışında"
    )

    def _step(cls: str, icon: str, label: str, when: str, badge: str) -> str:
        badge_html = f'<span class="badge">{_esc(badge)}</span>' if badge else ""
        return (
            f'<div class="{cls}">'
            f'  <div class="icon">{_esc(icon)}</div>'
            f'  <div class="label">{_esc(label)}</div>'
            f'  <div class="when">{_esc(when)}</div>'
            f'  {badge_html}'
            f'</div>'
        )

    return (
        f'<div class="process-diagram process-diagram--two-state">'
        f'  {_step(cls_open, "✓", "Sayım Açık", when_open, badge_open)}'
        f'  {_step(cls_closed, "✕", "Sayım Kapalı", when_closed, badge_closed)}'
        f'</div>'
    )


def quick_action_card(icon: str, title: str, desc: str, href: str = "", cta: str = "Aç") -> str:
    """Return a clickable quick action card."""
    tag = "a" if href else "div"
    href_attr = f' href="{_esc(_with_session_token(href))}" target="_self"' if href else ""
    return (
        f'<{tag} class="qa-card"{href_attr}>'
        f'  <span class="qa-icon">{_esc(icon)}</span>'
        f'  <span class="qa-title">{_esc(title)}</span>'
        f'  <span class="qa-desc">{_esc(desc)}</span>'
        f'  <span class="qa-cta">{_esc(cta)} ›</span>'
        f'</{tag}>'
    )


# ---------------------------------------------------------------------------
# Inline tags / badges
# ---------------------------------------------------------------------------
def status_pill(status: str) -> str:
    """Return an inline pill for submission window status."""
    labels = {"open": "Açık", "late": "Geç giriş", "locked": "Kapalı"}
    label = labels.get(status, status)
    return f'<span class="status-pill status-{_esc(status)}">{_esc(label)}</span>'


def status_badge(text: str, tone: str = "info") -> str:
    """Return a small status badge."""
    return f'<span class="status-badge {_esc(tone)}">{_esc(text)}</span>'


# ---------------------------------------------------------------------------
# Empty / data / form / filter heads
# ---------------------------------------------------------------------------
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


# ---------------------------------------------------------------------------
# Sidebar user card + logout
# ---------------------------------------------------------------------------
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
