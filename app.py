"""
Norm Konteyner Sayım Portalı — entry point.

Streamlit yüklenirken bu dosya çalışır. Login durumuna göre login
formu veya dashboard gösterilir.
"""

from __future__ import annotations

import base64
import time
from pathlib import Path

import streamlit as st
from sqlalchemy.exc import OperationalError, SQLAlchemyError

from db.connection import get_session
from utils.auth import (
    authenticate,
    is_authenticated,
    login_user,
    restore_session_from_cookie,
)
from utils.performance import page_timer
from utils.ui import (
    dashboard_hero,
    inject_css,
    kpi_card,
    quick_action_card,
    render_kpis,
    render_sidebar_brand,
    render_sidebar_user,
    section_header,
    status_panel,
    timeline_panel,
)
from utils.week import (
    current_week_iso,
    format_week_human,
    get_submission_status,
)


_LOGO_PATH = Path(__file__).parent / "assets" / "logo.png"


def _logo_base64() -> str:
    """Logo dosyasını base64 olarak oku — HTML'e inline embed için."""
    try:
        return base64.b64encode(_LOGO_PATH.read_bytes()).decode()
    except Exception:
        return ""


st.set_page_config(
    page_title="Norm Fasteners — Konteyner Portalı",
    page_icon=str(_LOGO_PATH) if _LOGO_PATH.exists() else "📦",
    layout="wide",
    initial_sidebar_state="expanded",
)
inject_css()


# ---------------------------------------------------------------------------
# Login screen
# ---------------------------------------------------------------------------
def render_login_form() -> None:
    """Stilize login formu — ortalanmış kart."""
    timer = page_timer("login")
    # Sidebar'ı login ekranında gizle
    st.markdown(
        "<style>[data-testid='stSidebar'] {display: none;}</style>",
        unsafe_allow_html=True,
    )

    logo_b64 = _logo_base64()
    logo_html = (
        f'<img src="data:image/png;base64,{logo_b64}" alt="Norm Fasteners" class="login-img"/>'
        if logo_b64
        else '<div class="icon">📦</div>'
    )

    st.markdown(
        '<div class="login-wrap">'
        '  <div class="login-logo">'
        '    <div class="login-brand">NORM FASTENERS</div>'
        f'   {logo_html}'
        '    <h1>Konteyner Sayım ve Takip Portalı</h1>'
        '  </div>'
        '  <div class="login-divider"></div>'
        '</div>',
        unsafe_allow_html=True,
    )

    # Form içeriği — kapsayıcı için ortala
    _, mid, _ = st.columns([1, 2, 1])
    with mid:
        with st.form("login_form", clear_on_submit=False):
            username = st.text_input("Kullanıcı adı", placeholder="kullanici_adi")
            password = st.text_input("Şifre", type="password", placeholder="••••••••")
            submitted = st.form_submit_button(
                "Giriş Yap", use_container_width=True, type="primary",
            )

        st.markdown(
            '<div class="login-footer">© 2026 Norm Fasteners · Tüm hakları saklıdır</div>',
            unsafe_allow_html=True,
        )

    if not submitted:
        timer.finish()
        return

    if not username or not password:
        st.error("Kullanıcı adı ve şifre boş olamaz.")
        timer.finish()
        return

    try:
        with get_session() as session:
            user = authenticate(username.strip(), password, session)
            if user is None:
                st.error("Kullanıcı adı veya şifre hatalı.")
                timer.finish()
                return
            login_user(user)
    except OperationalError:
        st.error("Veritabanına bağlanılamıyor. Lütfen yöneticiye bildirin.")
        timer.finish()
        return
    except SQLAlchemyError:
        st.error("Veritabanı hatası oluştu. Lütfen tekrar deneyin.")
        timer.finish()
        return
    except Exception:
        st.error("Beklenmeyen bir hata oluştu.")
        timer.finish()
        return

    st.success("Giriş yapıldı. Oturum hazırlanıyor...")
    timer.finish()
    time.sleep(0.8)
    st.rerun()


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
def render_sidebar() -> None:
    full_name = st.session_state.get("full_name", "")
    role = st.session_state.get("role", "user")

    render_sidebar_user(full_name, role)


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------
def render_dashboard() -> None:
    timer = page_timer("ana_sayfa")
    render_sidebar()

    full_name = st.session_state.get("full_name", "")
    role = st.session_state.get("role", "user")

    week_iso = current_week_iso()
    week_human = format_week_human(week_iso)

    try:
        with get_session() as session:
            status = get_submission_status(week_iso, session)
    except SQLAlchemyError:
        st.error("Sayım durumu okunamadı (veritabanı hatası).")
        timer.finish()
        return

    # ----- KPI kartları -----
    role_text = "Yönetici" if role == "admin" else "Kullanıcı"
    status_label = {"open": "Açık", "late": "Geç giriş", "locked": "Kapalı"}[status]
    status_kind = {"open": "success", "late": "warning", "locked": "info"}[status]
    dashboard_hero(
        "Konteyner Takip Portalı",
        f"Hoş geldin, {full_name}. Haftalık sayım, konteyner durumu ve operasyon takibini tek ekrandan yönetebilirsin.",
        [
            ("Aktif Hafta", week_iso),
            ("Sayım Durumu", status_label),
            ("Rol", role_text),
        ],
    )

    cards = [
        kpi_card("Aktif Hafta", week_iso, sub=week_human, icon="HW", tone="blue"),
        kpi_card("Sayım Penceresi", status_label, sub="Cuma 09.00 – 12.00", icon="SP", tone="amber" if status == "locked" else "green"),
        kpi_card("Kullanıcı Rolü", role_text, sub="Yetkiler admin panelinden yönetilir", icon="RL", tone="slate"),
    ]
    st.markdown('<div class="section-gap"></div>', unsafe_allow_html=True)
    render_kpis(cards)

    st.markdown('<div class="section-gap"></div>', unsafe_allow_html=True)

    status_col, flow_col = st.columns([1.65, 1])
    if status == "open":
        status_title = "Sayım girişi açık"
        status_text = f"{week_human} haftası için yetkili olduğunuz bölümlerde sayım girişi yapabilirsiniz."
        status_meta = "Aktif pencere"
    elif status == "late":
        status_title = "Geç giriş penceresi açık"
        status_text = f"Yönetici {week_human} haftası için manuel geç giriş penceresi açtı."
        status_meta = "Admin onaylı"
    else:
        status_title = "Sayım girişi şu an kapalı"
        status_text = "Bir sonraki normal giriş penceresi Cuma 09.00 – 12.00. Gerekirse yönetici geç giriş açabilir."
        status_meta = "Takip modu"

    with status_col:
        section_header("Bu Haftanın Durumu", "Sayım penceresi ve operasyon mesajı")
        st.markdown(
            status_panel(
                status=status_kind,
                title=status_title,
                body=status_text,
                meta=status_meta,
                cta_label="Sayım ekranına git",
                cta_href="sayim_girisi",
            ),
            unsafe_allow_html=True,
        )

    with flow_col:
        section_header("Haftalık Akış", "Standart sayım döngüsü")
        st.markdown(
            timeline_panel([
                ("1", "Cuma 09.00", "Sayım formları açılır"),
                ("2", "Cuma 12.00", "Normal giriş kapanır"),
                ("3", "Gerekirse", "Admin düzeltme veya geç giriş açar"),
            ]),
            unsafe_allow_html=True,
        )

    st.markdown('<div class="section-gap"></div>', unsafe_allow_html=True)

    # ----- Hızlı eylemler -----
    section_header("Hızlı Erişim", "Operasyonda en sık kullanılan ekranlar")
    qa1, qa2, qa3, qa4 = st.columns(4)
    qa1.markdown(
        quick_action_card(
            "01",
            "Sayım Girişi",
            "Bölümünüzün haftalık sayımını girin",
            "sayim_girisi",
        ),
        unsafe_allow_html=True,
    )
    qa2.markdown(
        quick_action_card(
            "02",
            "Anlık Durum",
            "Tüm bölümlerin son hafta verisi",
            "anlik_durum",
        ),
        unsafe_allow_html=True,
    )
    qa3.markdown(
        quick_action_card(
            "03",
            "Analiz",
            "Trend, sapma ve detaylı analiz",
            "analiz",
        ),
        unsafe_allow_html=True,
    )
    qa4.markdown(
        quick_action_card(
            "04",
            "Haftalık Takip",
            "Giren ve eksik bölümler",
            "haftalik_takip",
        ),
        unsafe_allow_html=True,
    )

    st.markdown(
        '<p style="margin-top:1.25rem; color:#64748b; font-size:0.9rem;">'
        'Sık kullanılan işlemler yukarıda; tüm sayfalara soldaki menüden de ulaşabilirsiniz.</p>',
        unsafe_allow_html=True,
    )
    timer.finish()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
restore_session_from_cookie()

if is_authenticated():
    render_sidebar_brand(_LOGO_PATH)

    pages = [
        st.Page(render_dashboard, title="Ana Sayfa", default=True),
        st.Page("pages/01_sayim_girisi.py", title="Sayım Girişi"),
        st.Page("pages/02_anlik_durum.py", title="Anlık Durum"),
        st.Page("pages/03_haftalik_takip.py", title="Haftalık Takip"),
        st.Page("pages/04_analiz.py", title="Analiz"),
        st.Page("pages/05_yetkililer.py", title="Yetkililer"),
    ]
    if st.session_state.get("role") == "admin":
        pages.append(st.Page("pages/99_admin.py", title="Admin Paneli"))

    selected_page = st.navigation(pages)
    selected_page.run()
else:
    render_login_form()
