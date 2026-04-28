"""
Norm Konteyner Sayım Portalı — entry point.

Streamlit yüklenirken bu dosya çalışır. Login durumuna göre login
formu veya dashboard gösterilir.
"""

from __future__ import annotations

import streamlit as st
from sqlalchemy.exc import OperationalError, SQLAlchemyError

from db.connection import get_session
from utils.auth import (
    authenticate,
    is_authenticated,
    login_user,
    logout_user,
)
from utils.ui import (
    inject_css,
    kpi_card,
    page_header,
    render_kpis,
    render_sidebar_user,
    status_pill,
)
from utils.week import (
    current_week_iso,
    format_week_human,
    get_submission_status,
)


st.set_page_config(
    page_title="Norm Konteyner Portalı",
    page_icon="📦",
    layout="wide",
    initial_sidebar_state="auto",
)
inject_css()


# ---------------------------------------------------------------------------
# Login screen
# ---------------------------------------------------------------------------
def render_login_form() -> None:
    """Stilize login formu."""
    # Sidebar'ı login ekranında gizle
    st.markdown(
        "<style>[data-testid='stSidebar'] {display: none;}</style>",
        unsafe_allow_html=True,
    )

    st.markdown(
        '<div class="login-wrap">'
        '  <div class="login-logo">'
        '    <div style="font-size: 2.5rem; line-height: 1;">📦</div>'
        '    <h1>Norm Konteyner Portalı</h1>'
        '    <p>Haftalık konteyner sayımı ve analiz sistemi</p>'
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
        title=f"Hoşgeldin, {full_name}",
        subtitle="Konteyner sayım portalına genel bakış",
        icon="🏠",
    )

    week_iso = current_week_iso()
    week_human = format_week_human(week_iso)

    try:
        with get_session() as session:
            status = get_submission_status(week_iso, session)
    except SQLAlchemyError:
        st.error("Sayım durumu okunamadı (veritabanı hatası).")
        return

    # ----- Bilgi kartları -----
    role_text = "Yönetici" if role == "admin" else "Kullanıcı"
    cards = [
        kpi_card("Bu Hafta", week_iso, sub=week_human),
        kpi_card("Sayım Durumu", "—", sub=status_pill(status).replace("<span", "<span style='font-size:0.95rem'")),
        kpi_card("Rolünüz", role_text),
    ]
    render_kpis(cards)

    st.markdown("<br>", unsafe_allow_html=True)

    # ----- Status açıklaması -----
    if status == "open":
        st.success(f"📝 **Sayım girişi açık** — {week_human}. Bu pencerede bölümünüzün sayımını girebilirsiniz.")
    elif status == "late":
        st.warning(f"⏰ **Geç giriş penceresi açık** — {week_human}. Yönetici manuel olarak açtı.")
    else:
        st.info(
            "🔒 **Sayım girişi şu an kapalı.** Bir sonraki pencere: "
            "**Cuma 09:00–12:00** (Türkiye saati). Geç giriş gerekiyorsa yönetici açabilir."
        )

    st.markdown("<br>", unsafe_allow_html=True)

    # ----- Hızlı eylemler -----
    st.markdown("### Hızlı Eylemler")
    qa1, qa2, qa3, qa4 = st.columns(4)

    with qa1:
        st.markdown(
            '<div class="kpi-card" style="text-align:center;">'
            '<div style="font-size:2rem;">📝</div>'
            '<div style="font-weight:600; margin-top:0.5rem;">Sayım Girişi</div>'
            '<div style="color:#8b949e; font-size:0.85rem; margin-top:0.3rem;">Bölümünüzün sayımını girin</div>'
            '</div>',
            unsafe_allow_html=True,
        )
    with qa2:
        st.markdown(
            '<div class="kpi-card" style="text-align:center;">'
            '<div style="font-size:2rem;">📊</div>'
            '<div style="font-weight:600; margin-top:0.5rem;">Anlık Durum</div>'
            '<div style="color:#8b949e; font-size:0.85rem; margin-top:0.3rem;">Tüm bölümlerin son hafta verisi</div>'
            '</div>',
            unsafe_allow_html=True,
        )
    with qa3:
        st.markdown(
            '<div class="kpi-card" style="text-align:center;">'
            '<div style="font-size:2rem;">📈</div>'
            '<div style="font-weight:600; margin-top:0.5rem;">Analiz</div>'
            '<div style="color:#8b949e; font-size:0.85rem; margin-top:0.3rem;">Trend ve sapma analizi</div>'
            '</div>',
            unsafe_allow_html=True,
        )
    with qa4:
        st.markdown(
            '<div class="kpi-card" style="text-align:center;">'
            '<div style="font-size:2rem;">📋</div>'
            '<div style="font-weight:600; margin-top:0.5rem;">Haftalık Takip</div>'
            '<div style="color:#8b949e; font-size:0.85rem; margin-top:0.3rem;">Giren/girmeyen bölümler</div>'
            '</div>',
            unsafe_allow_html=True,
        )

    st.caption("👈 Soldaki menüden ilgili sayfaya geçebilirsiniz.")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if is_authenticated():
    render_dashboard()
else:
    render_login_form()
