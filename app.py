"""
Norm Konteyner Sayım Portalı — entry point.

Streamlit yüklenirken bu dosya çalışır. Login durumuna göre login
formu veya dashboard gösterilir.
"""

from __future__ import annotations

import base64
from pathlib import Path

import streamlit as st
from sqlalchemy.exc import OperationalError, SQLAlchemyError

from db.connection import get_session
from utils.auth import (
    authenticate,
    is_authenticated,
    login_user,
    logout_user,
    restore_session_from_cookie,
)
from utils.ui import (
    inject_css,
    kpi_card,
    page_header,
    quick_action_card,
    render_kpis,
    render_sidebar_brand,
    render_sidebar_user,
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
    initial_sidebar_state="auto",
)
inject_css()


# ---------------------------------------------------------------------------
# Login screen
# ---------------------------------------------------------------------------
def render_login_form() -> None:
    """Stilize login formu — ortalanmış kart."""
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
        return

    if not username or not password:
        st.error("Kullanıcı adı ve şifre boş olamaz.")
        return

    try:
        with get_session() as session:
            user = authenticate(username.strip(), password, session)
            if user is None:
                st.error("Kullanıcı adı veya şifre hatalı.")
                return
            login_user(user)
    except OperationalError:
        st.error("Veritabanına bağlanılamıyor. Lütfen yöneticiye bildirin.")
        return
    except SQLAlchemyError:
        st.error("Veritabanı hatası oluştu. Lütfen tekrar deneyin.")
        return
    except Exception:
        st.error("Beklenmeyen bir hata oluştu.")
        return

    st.rerun()


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
def render_sidebar() -> None:
    full_name = st.session_state.get("full_name", "")
    role = st.session_state.get("role", "user")

    render_sidebar_user(full_name, role)

    if st.sidebar.button("🚪 Çıkış Yap", use_container_width=True):
        try:
            with get_session() as session:
                logout_user(session)
        except SQLAlchemyError:
            for key in ("user_id", "username", "role", "full_name", "department_ids"):
                st.session_state.pop(key, None)
        st.rerun()


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------
def render_dashboard() -> None:
    render_sidebar()

    full_name = st.session_state.get("full_name", "")
    role = st.session_state.get("role", "user")

    page_header(
        title=f"Hoş geldin, {full_name}",
        subtitle="Konteyner sayım portalına genel bakış",
            )

    week_iso = current_week_iso()
    week_human = format_week_human(week_iso)

    try:
        with get_session() as session:
            status = get_submission_status(week_iso, session)
    except SQLAlchemyError:
        st.error("Sayım durumu okunamadı (veritabanı hatası).")
        return

    # ----- KPI kartları -----
    role_text = "Yönetici" if role == "admin" else "Kullanıcı"
    status_label = {"open": "Açık", "late": "Geç giriş", "locked": "Kapalı"}[status]
    cards = [
        kpi_card("Aktif Hafta", week_iso, sub=week_human),
        kpi_card("Sayım Durumu", status_label, sub="Cuma 09.00 – 12.00"),
        kpi_card("Rolünüz", role_text),
    ]
    render_kpis(cards)

    st.markdown("<br>", unsafe_allow_html=True)

    # ----- Status açıklaması -----
    if status == "open":
        st.success(
            f"**Sayım girişi açık.** Şu an {week_human} haftası için bölümünüzün "
            "sayımını girebilirsiniz."
        )
    elif status == "late":
        st.warning(
            f"**Geç giriş penceresi açık.** Yönetici {week_human} haftası için "
            "sayım girişini manuel olarak açtı."
        )
    else:
        st.info(
            "**Sayım girişi şu an kapalı.** Bir sonraki pencere: "
            "**Cuma 09.00 – 12.00** (Türkiye saati). "
            "Geç giriş gerekiyorsa yönetici manuel olarak açabilir."
        )

    st.markdown("<br>", unsafe_allow_html=True)

    # ----- Hızlı eylemler -----
    st.markdown("### Hızlı Erişim")
    qa1, qa2, qa3, qa4 = st.columns(4)
    qa1.markdown(
        quick_action_card(
            "📝",
            "Sayım Girişi",
            "Bölümünüzün haftalık sayımını girin",
            "sayim_girisi",
        ),
        unsafe_allow_html=True,
    )
    qa2.markdown(
        quick_action_card(
            "📊",
            "Anlık Durum",
            "Tüm bölümlerin son hafta verisi",
            "anlik_durum",
        ),
        unsafe_allow_html=True,
    )
    qa3.markdown(
        quick_action_card(
            "📈",
            "Analiz",
            "Trend, sapma ve detaylı analiz",
            "analiz",
        ),
        unsafe_allow_html=True,
    )
    qa4.markdown(
        quick_action_card(
            "📋",
            "Haftalık Takip",
            "Giren ve eksik bölümler",
            "haftalik_takip",
        ),
        unsafe_allow_html=True,
    )

    st.markdown(
        '<p style="margin-top:1.5rem; color:#64748b; font-size:0.9rem;">'
        'Soldaki menüden ilgili sayfaya geçebilirsiniz.</p>',
        unsafe_allow_html=True,
    )


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
