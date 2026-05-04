"""
Shared UI helpers — global CSS, page headers, KPI cards, badges.

Streamlit'in default görünümünü kapatıp tutarlı bir endüstriyel/koyu
tema veriyoruz. Her sayfa init'inde ``inject_css()`` çağrılır.
"""

from __future__ import annotations

import base64
from html import escape
from pathlib import Path

import streamlit as st


_GLOBAL_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

/* ------------------------------------------------------------------ */
/* Reset & globals                                                    */
/* ------------------------------------------------------------------ */
#MainMenu, footer, [data-testid="stToolbar"] { visibility: hidden; }

html, body, [class*="css"], button, input, textarea, select {
    font-family: 'Inter', -apple-system, "Segoe UI", system-ui, sans-serif !important;
    -webkit-font-smoothing: antialiased;
    -moz-osx-font-smoothing: grayscale;
    font-size: 16px;
}

.block-container {
    padding-top: 2rem !important;
    padding-bottom: 4rem !important;
    padding-left: 2.5rem !important;
    padding-right: 2.5rem !important;
    max-width: 1700px;
}

h1, h2, h3, h4 {
    letter-spacing: -0.025em;
    color: #f1f5f9;
}
h1 { font-weight: 800; font-size: 2.3rem; }
h2 { font-weight: 700; font-size: 1.7rem; }
h3 {
    font-weight: 700;
    font-size: 1.32rem;
    margin-top: 1.75rem !important;
    margin-bottom: 1rem !important;
    padding-bottom: 0.5rem;
    border-bottom: 1px solid rgba(148, 163, 184, 0.10);
    position: relative;
}
h3::before {
    content: "";
    position: absolute;
    left: 0; bottom: -1px;
    width: 36px;
    height: 2px;
    background: linear-gradient(90deg, #3b82f6, #6366f1);
    border-radius: 2px;
}
h4 { font-weight: 600; font-size: 1.18rem; }

p, span, div { color: #cbd5e1; }
p { font-size: 1rem; line-height: 1.6; }

/* Markdown body text */
.stMarkdown p, .stMarkdown li {
    font-size: 1rem;
    line-height: 1.65;
}

hr {
    border: none;
    border-top: 1px solid #1f2937;
    margin: 2rem 0 !important;
}

/* ------------------------------------------------------------------ */
/* App genel arka plan                                                */
/* ------------------------------------------------------------------ */
[data-testid="stAppViewContainer"]:not(:has(.login-wrap)) {
    background:
        radial-gradient(ellipse 1200px 500px at 50% -20%, rgba(99, 102, 241, 0.08), transparent 60%),
        radial-gradient(ellipse 800px 400px at 100% 100%, rgba(59, 130, 246, 0.06), transparent 60%),
        #060a14 !important;
}

/* ------------------------------------------------------------------ */
/* Page header                                                        */
/* ------------------------------------------------------------------ */
.norm-header {
    background:
        radial-gradient(circle at 15% 0%, rgba(99, 102, 241, 0.28), transparent 55%),
        radial-gradient(circle at 90% 100%, rgba(59, 130, 246, 0.22), transparent 55%),
        radial-gradient(circle at 50% 50%, rgba(139, 92, 246, 0.10), transparent 70%),
        linear-gradient(135deg, #0c1424 0%, #131c2f 100%);
    padding: 1.5rem 1.75rem;
    border-radius: 14px;
    margin-bottom: 1.5rem;
    border: 1px solid rgba(99, 102, 241, 0.16);
    box-shadow:
        0 1px 0 rgba(255, 255, 255, 0.05) inset,
        0 0 0 1px rgba(99, 102, 241, 0.05),
        0 12px 40px rgba(0, 0, 0, 0.4),
        0 4px 16px rgba(99, 102, 241, 0.10);
    position: relative;
    overflow: hidden;
}
.norm-header::before {
    content: "";
    position: absolute;
    top: 0; left: 5%; right: 5%;
    height: 1px;
    background: linear-gradient(90deg, transparent, rgba(99, 102, 241, 0.6), transparent);
}
.norm-header::after {
    content: "";
    position: absolute;
    inset: 0;
    background: linear-gradient(135deg, transparent 0%, transparent 60%, rgba(99, 102, 241, 0.04) 100%);
    pointer-events: none;
}
.norm-header h1 {
    margin: 0 !important;
    font-size: 1.9rem !important;
    font-weight: 800 !important;
    line-height: 1.15;
    letter-spacing: -0.035em;
    background: linear-gradient(135deg, #f8fafc 0%, #cbd5e1 100%);
    -webkit-background-clip: text;
    background-clip: text;
    -webkit-text-fill-color: transparent;
    position: relative;
    z-index: 1;
}
.norm-header p {
    margin: 0.45rem 0 0 0 !important;
    color: #94a3b8 !important;
    font-size: 0.98rem !important;
    font-weight: 400;
    line-height: 1.55;
    position: relative;
    z-index: 1;
}

/* ------------------------------------------------------------------ */
/* KPI card                                                           */
/* ------------------------------------------------------------------ */
.kpi-card {
    position: relative;
    background:
        radial-gradient(circle at 100% 0%, rgba(99, 102, 241, 0.10), transparent 50%),
        linear-gradient(180deg, #0f172a 0%, #0b1220 100%);
    border: 1px solid rgba(99, 102, 241, 0.10);
    border-radius: 10px;
    padding: 1.05rem 1.15rem;
    height: 100%;
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
    overflow: hidden;
    box-shadow:
        0 1px 0 rgba(255, 255, 255, 0.04) inset,
        0 4px 16px rgba(0, 0, 0, 0.25);
}
.kpi-card::before {
    content: "";
    position: absolute;
    top: 0; left: 0; right: 0;
    height: 2px;
    background: linear-gradient(90deg, #3b82f6, #6366f1, #8b5cf6);
    opacity: 0;
    transition: opacity 0.25s ease;
}
.kpi-card::after {
    content: "";
    position: absolute;
    bottom: -50%;
    right: -30%;
    width: 200px;
    height: 200px;
    background: radial-gradient(circle, rgba(99, 102, 241, 0.06) 0%, transparent 70%);
    pointer-events: none;
}
.kpi-card:hover {
    transform: translateY(-2px);
    border-color: rgba(99, 102, 241, 0.4);
    background:
        radial-gradient(circle at 100% 0%, rgba(99, 102, 241, 0.16), transparent 50%),
        linear-gradient(180deg, #131c2f 0%, #0c1424 100%);
    box-shadow:
        0 1px 0 rgba(255, 255, 255, 0.06) inset,
        0 16px 40px rgba(0, 0, 0, 0.45),
        0 0 0 1px rgba(99, 102, 241, 0.18),
        0 8px 24px rgba(99, 102, 241, 0.18);
}
.kpi-card:hover::before { opacity: 1; }

.kpi-label {
    color: #94a3b8;
    font-size: 0.72rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    margin-bottom: 0.55rem;
    position: relative;
    z-index: 1;
}
.kpi-value {
    color: #f8fafc;
    font-size: 1.9rem;
    font-weight: 800;
    line-height: 1.05;
    letter-spacing: -0.03em;
    font-feature-settings: "tnum";
    position: relative;
    z-index: 1;
}
.kpi-sub {
    color: #94a3b8;
    font-size: 0.82rem;
    margin-top: 0.45rem;
    font-weight: 500;
    position: relative;
    z-index: 1;
}
.kpi-delta {
    margin-top: 0.5rem;
    font-size: 0.8rem;
    font-weight: 600;
    display: inline-flex;
    align-items: center;
    padding: 0.25rem 0.6rem;
    border-radius: 6px;
}
.kpi-delta.pos {
    color: #fca5a5;
    background: rgba(239, 68, 68, 0.12);
    border: 1px solid rgba(239, 68, 68, 0.22);
}
.kpi-delta.neg {
    color: #6ee7b7;
    background: rgba(16, 185, 129, 0.12);
    border: 1px solid rgba(16, 185, 129, 0.22);
}
.kpi-delta.neutral {
    color: #94a3b8;
    background: rgba(148, 163, 184, 0.10);
    border: 1px solid rgba(148, 163, 184, 0.20);
}

/* ------------------------------------------------------------------ */
/* Quick action card (dashboard)                                      */
/* ------------------------------------------------------------------ */
.qa-card {
    display: block;
    position: relative;
    background:
        radial-gradient(circle at 50% -20%, rgba(99, 102, 241, 0.10), transparent 60%),
        linear-gradient(180deg, #0f172a 0%, #0b1220 100%);
    border: 1px solid rgba(99, 102, 241, 0.10);
    border-radius: 16px;
    padding: 2rem 1.4rem 1.6rem;
    text-align: center;
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
    overflow: hidden;
    box-shadow:
        0 1px 0 rgba(255, 255, 255, 0.04) inset,
        0 4px 16px rgba(0, 0, 0, 0.25);
    text-decoration: none !important;
    cursor: pointer;
}
.qa-card::before {
    content: "";
    position: absolute;
    top: 0; left: 30%; right: 30%;
    height: 1px;
    background: linear-gradient(90deg, transparent, rgba(99, 102, 241, 0.5), transparent);
    opacity: 0;
    transition: opacity 0.3s ease;
}
.qa-card:hover {
    transform: translateY(-5px);
    border-color: rgba(99, 102, 241, 0.45);
    background:
        radial-gradient(circle at 50% -20%, rgba(99, 102, 241, 0.18), transparent 60%),
        linear-gradient(180deg, #131c2f 0%, #0c1424 100%);
    box-shadow:
        0 1px 0 rgba(255, 255, 255, 0.06) inset,
        0 20px 50px rgba(99, 102, 241, 0.22),
        0 0 0 1px rgba(99, 102, 241, 0.2);
}
.qa-card:hover::before { opacity: 1; }
.qa-card:hover .qa-icon { transform: scale(1.1); }

.qa-icon {
    font-size: 3rem;
    line-height: 1;
    margin-bottom: 1rem;
    transition: transform 0.3s ease;
    display: inline-block;
}
.qa-title {
    color: #f1f5f9;
    font-weight: 700;
    font-size: 1.2rem;
    margin-bottom: 0.5rem;
    letter-spacing: -0.01em;
}
.qa-desc {
    color: #94a3b8;
    font-size: 0.95rem;
    line-height: 1.55;
}
.qa-card:focus-visible {
    outline: 2px solid #93c5fd;
    outline-offset: 3px;
}

/* ------------------------------------------------------------------ */
/* Status pill                                                        */
/* ------------------------------------------------------------------ */
.status-pill {
    display: inline-block;
    padding: 0.35rem 0.95rem;
    border-radius: 999px;
    font-size: 0.85rem;
    font-weight: 600;
    border: 1px solid transparent;
}
.status-open    { background: rgba(16, 185, 129, 0.12); color: #34d399; border-color: rgba(16,185,129,0.4); }
.status-late    { background: rgba(245, 158, 11, 0.12); color: #fbbf24; border-color: rgba(245,158,11,0.4); }
.status-locked  { background: rgba(148, 163, 184, 0.12); color: #cbd5e1; border-color: rgba(148,163,184,0.4); }

/* ------------------------------------------------------------------ */
/* Sidebar                                                            */
/* ------------------------------------------------------------------ */
[data-testid="stSidebar"] {
    background: #060b14;
    border-right: 1px solid #111827;
}
[data-testid="stSidebarCollapseButton"],
[data-testid="collapsedControl"] {
    display: none !important;
    pointer-events: none !important;
}
[data-testid="stSidebar"] .block-container {
    padding-top: 5.85rem !important;
}
[data-testid="stSidebarNav"] {
    padding-top: 0 !important;
}
[data-testid="stSidebarNav"] ul {
    padding-top: 0 !important;
}
[data-testid="stSidebarNav"] li a {
    border-radius: 8px !important;
    min-height: 2.15rem !important;
    margin: 0.15rem 0.65rem !important;
    color: #cbd5e1 !important;
    transition: background 0.16s ease, color 0.16s ease;
}
[data-testid="stSidebarNav"] li a:hover {
    background: rgba(148, 163, 184, 0.10) !important;
    color: #f8fafc !important;
}
[data-testid="stSidebarNav"] li a[aria-current="page"] {
    background: rgba(59, 130, 246, 0.16) !important;
    color: #f8fafc !important;
}
.sidebar-brand-card {
    display: flex;
    align-items: center;
    gap: 0.8rem;
    position: fixed;
    z-index: 20;
    top: 0.8rem;
    left: 0.85rem;
    width: calc(100% - 1.7rem);
    max-width: 14.8rem;
    padding: 0.65rem 0.7rem;
    background: rgba(6, 11, 20, 0.92);
    border: 1px solid rgba(148, 163, 184, 0.12);
    border-radius: 12px;
    box-shadow: 0 12px 28px rgba(0, 0, 0, 0.24);
    backdrop-filter: blur(12px);
}
.sidebar-brand-logo {
    width: 38px;
    height: 38px;
    object-fit: contain;
    flex: 0 0 auto;
    padding: 0.35rem;
    border-radius: 12px;
    background:
        radial-gradient(circle at 30% 25%, rgba(59, 130, 246, 0.20), transparent 70%),
        linear-gradient(135deg, #0f172a 0%, #0b1220 100%);
    border: 1px solid rgba(148, 163, 184, 0.16);
    box-shadow: 0 10px 24px rgba(0, 0, 0, 0.22);
}
.sidebar-brand-title {
    color: #f8fafc;
    font-size: 0.84rem;
    font-weight: 800;
    letter-spacing: 0.07em;
    line-height: 1.1;
}
.sidebar-brand-subtitle {
    color: #94a3b8;
    font-size: 0.68rem;
    font-weight: 600;
    margin-top: 0.2rem;
    letter-spacing: 0.02em;
}
.sidebar-user-card {
    background: rgba(15, 23, 42, 0.62);
    border: 1px solid rgba(148, 163, 184, 0.14);
    border-radius: 10px;
    padding: 0.9rem;
    margin: 1rem 0.7rem 0.75rem;
    position: relative;
    overflow: hidden;
}
.sidebar-user-card::before {
    content: "";
    position: absolute;
    top: 0; left: 0; right: 0;
    height: 2px;
    background: linear-gradient(90deg, #3b82f6, #8b5cf6);
}
.sidebar-user-name {
    color: #f1f5f9;
    font-weight: 600;
    font-size: 0.93rem;
    line-height: 1.2;
    display: flex;
    align-items: center;
    gap: 0.5rem;
}
.sidebar-user-role {
    display: inline-block;
    color: #93c5fd;
    font-size: 0.75rem;
    font-weight: 500;
    margin-top: 0.45rem;
    padding: 0.2rem 0.6rem;
    background: rgba(59, 130, 246, 0.14);
    border-radius: 7px;
    border: 1px solid rgba(59, 130, 246, 0.3);
}

/* ------------------------------------------------------------------ */
/* Buttons                                                            */
/* ------------------------------------------------------------------ */
.stButton > button {
    border-radius: 10px !important;
    font-weight: 600 !important;
    font-size: 1rem !important;
    transition: all 0.18s ease;
    border: 1px solid #1f2937;
    background: #0f172a;
    color: #e2e8f0;
    padding: 0.65rem 1.15rem;
}
.stButton > button:hover {
    border-color: #3b82f6;
    background: #111c33;
    transform: translateY(-1px);
    box-shadow: 0 6px 14px rgba(59, 130, 246, 0.18);
}
.stButton > button[kind="primary"] {
    background: linear-gradient(135deg, #3b82f6 0%, #2563eb 100%) !important;
    border: none !important;
    color: white !important;
    box-shadow: 0 4px 14px rgba(59, 130, 246, 0.35);
}
.stButton > button[kind="primary"]:hover {
    box-shadow: 0 6px 22px rgba(59, 130, 246, 0.55);
    transform: translateY(-1px);
}

/* ------------------------------------------------------------------ */
/* Form inputs                                                        */
/* ------------------------------------------------------------------ */
.stTextInput input, .stNumberInput input, .stDateInput input,
.stTimeInput input, .stTextArea textarea {
    border-radius: 10px !important;
    border: 1px solid #1f2937 !important;
    background: #0a101c !important;
    color: #e2e8f0 !important;
    transition: border-color 0.18s ease, box-shadow 0.18s ease;
    font-size: 1rem !important;
    padding: 0.65rem 0.85rem !important;
}
.stTextInput input:focus, .stNumberInput input:focus,
.stDateInput input:focus, .stTimeInput input:focus,
.stTextArea textarea:focus {
    border-color: #3b82f6 !important;
    box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.15) !important;
}
.stTextInput label, .stNumberInput label, .stDateInput label,
.stTimeInput label, .stTextArea label, .stSelectbox label, .stRadio label {
    color: #cbd5e1 !important;
    font-size: 0.95rem !important;
    font-weight: 500 !important;
}

/* Selectbox */
[data-baseweb="select"] > div {
    border-radius: 10px !important;
    border-color: #1f2937 !important;
    background: #0a101c !important;
}

/* ------------------------------------------------------------------ */
/* Tabs                                                               */
/* ------------------------------------------------------------------ */
.stTabs [data-baseweb="tab-list"] {
    gap: 0.4rem;
    border-bottom: 1px solid #1f2937;
    padding-bottom: 0;
}
.stTabs [data-baseweb="tab"] {
    background: transparent;
    border-radius: 10px 10px 0 0;
    padding: 0.65rem 1.15rem;
    font-weight: 500;
    color: #64748b;
    transition: all 0.15s ease;
}
.stTabs [data-baseweb="tab"]:hover {
    background: rgba(59, 130, 246, 0.06);
    color: #e2e8f0;
}
.stTabs [aria-selected="true"] {
    background: rgba(59, 130, 246, 0.08) !important;
    color: #93c5fd !important;
    border-bottom: 2px solid #3b82f6;
    font-weight: 600;
}

/* ------------------------------------------------------------------ */
/* Expander                                                           */
/* ------------------------------------------------------------------ */
.streamlit-expanderHeader, [data-testid="stExpander"] summary {
    background: #0f172a !important;
    border-radius: 10px !important;
    border: 1px solid #1f2937 !important;
    font-weight: 600 !important;
    transition: all 0.15s ease;
    padding: 0.85rem 1.1rem !important;
}
[data-testid="stExpander"] summary:hover {
    border-color: #3b82f6 !important;
    background: #111c33 !important;
}

/* ------------------------------------------------------------------ */
/* DataFrame                                                          */
/* ------------------------------------------------------------------ */
.stDataFrame {
    border-radius: 12px;
    border: 1px solid #1f2937;
    width: 100% !important;
}
.stDataFrame [data-testid="stDataFrameResizable"] {
    border-radius: 12px;
    overflow: auto !important;
    width: 100% !important;
    min-height: 320px;
}
/* Tablo hücreleri ve başlıkları daha okunaklı */
.stDataFrame [role="grid"] {
    font-size: 0.95rem !important;
}
.stDataFrame [role="columnheader"] {
    font-size: 0.9rem !important;
    font-weight: 700 !important;
    color: #f1f5f9 !important;
    background: #131c2f !important;
}
.stDataFrame [role="gridcell"] {
    font-size: 0.95rem !important;
    color: #e2e8f0 !important;
    padding: 0.65rem 0.85rem !important;
}

/* ------------------------------------------------------------------ */
/* Alerts (st.success, info, warning, error)                          */
/* ------------------------------------------------------------------ */
.stAlert {
    border-radius: 14px !important;
    border: 1px solid;
    padding: 1.1rem 1.35rem !important;
    font-weight: 500;
    backdrop-filter: blur(12px);
    box-shadow: 0 4px 16px rgba(0, 0, 0, 0.2);
}
[data-baseweb="notification"] { border-radius: 14px; }

/* Info kutusu */
[data-testid="stAlertContentInfo"] {
    background: linear-gradient(135deg, rgba(59, 130, 246, 0.12), rgba(99, 102, 241, 0.08)) !important;
    border-color: rgba(99, 102, 241, 0.3) !important;
}
/* Success */
[data-testid="stAlertContentSuccess"] {
    background: linear-gradient(135deg, rgba(16, 185, 129, 0.12), rgba(5, 150, 105, 0.08)) !important;
    border-color: rgba(16, 185, 129, 0.3) !important;
}
/* Warning */
[data-testid="stAlertContentWarning"] {
    background: linear-gradient(135deg, rgba(245, 158, 11, 0.12), rgba(217, 119, 6, 0.08)) !important;
    border-color: rgba(245, 158, 11, 0.3) !important;
}
/* Error */
[data-testid="stAlertContentError"] {
    background: linear-gradient(135deg, rgba(239, 68, 68, 0.12), rgba(220, 38, 38, 0.08)) !important;
    border-color: rgba(239, 68, 68, 0.3) !important;
}


/* ------------------------------------------------------------------ */
/* Login screen — Canva-style hero + glassmorphism                    */
/* ------------------------------------------------------------------ */
/* Tüm sayfayı saran ışıklı arka plan — orbital gradient'ler */
[data-testid="stAppViewContainer"]:has(.login-wrap) {
    background:
        radial-gradient(circle at 12% 18%, rgba(99, 102, 241, 0.42) 0%, transparent 38%),
        radial-gradient(circle at 88% 12%, rgba(59, 130, 246, 0.35) 0%, transparent 40%),
        radial-gradient(circle at 78% 92%, rgba(139, 92, 246, 0.40) 0%, transparent 42%),
        radial-gradient(circle at 18% 88%, rgba(14, 165, 233, 0.30) 0%, transparent 40%),
        linear-gradient(135deg, #060a14 0%, #0a0f1c 50%, #060814 100%) !important;
    background-attachment: fixed !important;
}

/* Yumuşak yüzen ışık animasyonu */
[data-testid="stAppViewContainer"]:has(.login-wrap)::before {
    content: "";
    position: fixed;
    inset: 0;
    background:
        radial-gradient(circle at 50% 50%, rgba(99, 102, 241, 0.10), transparent 60%);
    animation: norm-pulse 12s ease-in-out infinite;
    pointer-events: none;
    z-index: 0;
}
@keyframes norm-pulse {
    0%, 100% { transform: translate(-3%, -2%) scale(1); opacity: 0.7; }
    50%      { transform: translate(3%, 2%) scale(1.08); opacity: 1; }
}

/* Login kartı — glassmorphism */
.login-wrap {
    max-width: 460px;
    margin: 4.5rem auto 1.25rem;
    background: linear-gradient(180deg, rgba(15, 23, 42, 0.82) 0%, rgba(11, 18, 32, 0.78) 100%);
    backdrop-filter: blur(28px) saturate(1.2);
    -webkit-backdrop-filter: blur(28px) saturate(1.2);
    border: 1px solid rgba(148, 163, 184, 0.14);
    border-radius: 24px;
    padding: 2.5rem 2.5rem 2rem;
    box-shadow:
        0 1px 0 rgba(255, 255, 255, 0.06) inset,
        0 0 0 1px rgba(99, 102, 241, 0.08),
        0 40px 100px rgba(0, 0, 0, 0.55),
        0 12px 40px rgba(99, 102, 241, 0.18);
    position: relative;
    overflow: hidden;
    z-index: 1;
}
.login-wrap::before {
    content: "";
    position: absolute;
    top: 0; left: 10%; right: 10%;
    height: 1px;
    background: linear-gradient(90deg, transparent, rgba(255, 255, 255, 0.4), transparent);
}
.login-wrap::after {
    content: "";
    position: absolute;
    top: -50%; left: -50%;
    width: 200%;
    height: 200%;
    background: radial-gradient(circle, rgba(99, 102, 241, 0.06) 0%, transparent 50%);
    pointer-events: none;
}

.login-logo {
    text-align: center;
    margin-bottom: 1.75rem;
    position: relative;
    z-index: 2;
}
.login-brand {
    font-size: 1.55rem;
    font-weight: 800;
    letter-spacing: 0.22em;
    text-transform: uppercase;
    margin-bottom: 1.5rem;
    background: linear-gradient(90deg, #c7d2fe, #93c5fd 50%, #c7d2fe);
    -webkit-background-clip: text;
    background-clip: text;
    -webkit-text-fill-color: transparent;
    text-shadow: 0 0 40px rgba(99, 102, 241, 0.2);
}
.login-logo .login-img {
    display: block;
    width: 120px;
    height: 120px;
    object-fit: contain;
    margin: 0 auto 1.5rem;
    padding: 1rem;
    border-radius: 28px;
    background:
        radial-gradient(circle at 30% 30%, rgba(99, 102, 241, 0.25), transparent 70%),
        linear-gradient(135deg, rgba(30, 41, 59, 0.9) 0%, rgba(15, 23, 42, 0.9) 100%);
    border: 1px solid rgba(148, 163, 184, 0.16);
    box-shadow:
        0 0 0 1px rgba(99, 102, 241, 0.18),
        0 20px 50px rgba(99, 102, 241, 0.30),
        inset 0 1px 0 rgba(255, 255, 255, 0.06);
    transition: transform 0.4s cubic-bezier(0.4, 0, 0.2, 1);
}
.login-wrap:hover .login-img {
    transform: translateY(-3px) scale(1.02);
}
.login-logo .icon {
    width: 96px;
    height: 96px;
    margin: 0 auto 1.5rem;
    background: linear-gradient(135deg, #3b82f6 0%, #6366f1 50%, #8b5cf6 100%);
    border-radius: 24px;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 2.5rem;
    box-shadow:
        0 0 0 1px rgba(255, 255, 255, 0.1) inset,
        0 20px 50px rgba(99, 102, 241, 0.5);
}
.login-logo h1 {
    color: #f8fafc !important;
    font-size: 1.55rem !important;
    font-weight: 800 !important;
    margin: 0 !important;
    letter-spacing: -0.02em;
    line-height: 1.2;
    background: linear-gradient(135deg, #f8fafc 0%, #cbd5e1 100%);
    -webkit-background-clip: text;
    background-clip: text;
    -webkit-text-fill-color: transparent;
}
.login-divider {
    height: 1px;
    background: linear-gradient(90deg, transparent, rgba(148, 163, 184, 0.18), transparent);
    margin: 1.75rem 0 1rem;
}
.login-footer {
    text-align: center;
    color: #475569;
    font-size: 0.78rem;
    margin-top: 1.25rem;
    letter-spacing: 0.03em;
}

/* ------------------------------------------------------------------ */
/* Caption & subtle text                                              */
/* ------------------------------------------------------------------ */
.stCaption, [data-testid="stCaptionContainer"] {
    color: #64748b !important;
    font-size: 0.85rem !important;
}
</style>
"""


def _esc(value: object) -> str:
    """HTML içinde güvenle basmak için metni kaçır."""
    return escape(str(value), quote=True)


def inject_css() -> None:
    """Sayfa init'inde çağır — global CSS'i sayfaya enjekte eder."""
    st.markdown(_GLOBAL_CSS, unsafe_allow_html=True)


def render_sidebar_brand(logo_path: str | Path) -> None:
    """Sidebar menüsünün üstünde marka alanı göster."""
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


def page_header(title: str, subtitle: str = "", icon: str = "") -> None:
    """Banner-style sayfa başlığı."""
    icon_html = f'<span style="margin-right:0.7rem;">{_esc(icon)}</span>' if icon else ""
    sub_html = f'<p>{_esc(subtitle)}</p>' if subtitle else ""
    st.markdown(
        f'<div class="norm-header"><h1>{icon_html}{_esc(title)}</h1>{sub_html}</div>',
        unsafe_allow_html=True,
    )


def kpi_card(
    label: str,
    value: str,
    sub: str = "",
    delta: str = "",
    delta_kind: str = "neutral",
) -> str:
    """Bir KPI kartının HTML string'ini döndürür."""
    sub_html = f'<div class="kpi-sub">{_esc(sub)}</div>' if sub else ""
    delta_html = f'<div class="kpi-delta {_esc(delta_kind)}">{_esc(delta)}</div>' if delta else ""
    return (
        f'<div class="kpi-card">'
        f'  <div class="kpi-label">{_esc(label)}</div>'
        f'  <div class="kpi-value">{_esc(value)}</div>'
        f'  {sub_html}{delta_html}'
        f'</div>'
    )


def render_kpis(cards: list[str]) -> None:
    """Bir liste KPI HTML'i alır, eşit genişlikte sütunlara koyar."""
    cols = st.columns(len(cards))
    for col, html in zip(cols, cards):
        col.markdown(html, unsafe_allow_html=True)


def quick_action_card(icon: str, title: str, desc: str, href: str = "") -> str:
    """Dashboard'da hızlı eylem kartı."""
    tag = "a" if href else "div"
    href_attr = f' href="{_esc(href)}"' if href else ""
    return (
        f'<{tag} class="qa-card"{href_attr}>'
        f'  <div class="qa-icon">{_esc(icon)}</div>'
        f'  <div class="qa-title">{_esc(title)}</div>'
        f'  <div class="qa-desc">{_esc(desc)}</div>'
        f'</{tag}>'
    )


def status_pill(status: str) -> str:
    """Status (open/late/locked) için pill HTML'i döndürür."""
    labels = {
        "open":   "📝 Açık",
        "late":   "⏰ Geç giriş",
        "locked": "🔒 Kapalı",
    }
    label = labels.get(status, status)
    return f'<span class="status-pill status-{_esc(status)}">{_esc(label)}</span>'


def render_sidebar_user(full_name: str, role: str) -> None:
    """Sidebar üstüne kullanıcı kart'ı."""
    role_label = "Yönetici" if role == "admin" else "Kullanıcı"
    st.sidebar.markdown(
        f'<div class="sidebar-user-card">'
        f'  <div class="sidebar-user-name">👤 {_esc(full_name)}</div>'
        f'  <span class="sidebar-user-role">{_esc(role_label)}</span>'
        f'</div>',
        unsafe_allow_html=True,
    )
