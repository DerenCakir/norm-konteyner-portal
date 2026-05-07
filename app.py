"""
Norm Konteyner Sayım Portalı — entry point.

Streamlit yüklenirken bu dosya çalışır. Login durumuna göre login
formu veya dashboard gösterilir.
"""

from __future__ import annotations

from pathlib import Path

import streamlit as st
from sqlalchemy.exc import OperationalError, SQLAlchemyError

from db.connection import get_session
from utils.auth import (
    authenticate,
    is_authenticated,
    login_user,
    restore_session_from_query,
)
from utils.performance import page_timer
from utils.ui import (
    _logo_data_uri,
    inject_css,
    render_sidebar_brand,
)


_LOGO_PATH = Path(__file__).parent / "assets" / "logo.png"


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
    # Login ekranında sidebar'ı gizle ama collapsedControl'a (geri açma oku)
    # dokunma — daha önceki sürümde onu da display:none yapınca kullanıcılar
    # sidebar'ı bir kez kapattıktan sonra geri açamıyordu.
    st.markdown(
        """
        <style>
        [data-testid="stSidebar"] {
            transform: translateX(-100%) !important;
            visibility: hidden !important;
            min-width: 0 !important;
            max-width: 0 !important;
            width: 0 !important;
            pointer-events: none !important;
        }
        [data-testid="stAppViewContainer"] { margin-left: 0 !important; }
        .block-container { max-width: 1180px !important; padding-top: 2.5rem !important; }
        </style>
        """,
        unsafe_allow_html=True,
    )

    data_uri = _logo_data_uri(str(_LOGO_PATH))
    logo_img = (
        f'<img src="{data_uri}" alt="Norm Fasteners"/>' if data_uri else ""
    )

    # Önceki rerun'dan kalan hata mesajını al — formun üstünde belirgin
    # bir kutuda göstereceğiz, ayrıca toast ile de bildireceğiz.
    pending_error = st.session_state.pop("login_error", None)
    if pending_error:
        st.toast(f"⚠️ {pending_error}", icon="🚫")

    # Tek kolon — marka bloğu üstte, form altta, hepsi ortada
    _, mid, _ = st.columns([1, 1.2, 1])
    with mid:
        st.markdown(
            f'<div class="login-brand-pane">'
            f'  <div class="login-brand-mark">{logo_img}<span>Norm Fasteners</span></div>'
            f'  <div class="login-brand-eyebrow">Konteyner Operasyon Merkezi</div>'
            f'  <p class="login-brand-instruction">Devam etmek için kullanıcı adınızı ve şifrenizi giriniz.</p>'
            f'</div>',
            unsafe_allow_html=True,
        )

        if pending_error:
            st.markdown(
                f'<div class="login-error-banner" role="alert">'
                f'  <span class="login-error-icon">⚠️</span>'
                f'  <span class="login-error-text">{escape(pending_error)}</span>'
                f'</div>',
                unsafe_allow_html=True,
            )

        with st.form("login_form", clear_on_submit=False):
            username = st.text_input("Kullanıcı adı", placeholder="kullanici_adi")
            password = st.text_input("Şifre", type="password", placeholder="••••••••")
            submitted = st.form_submit_button(
                "Giriş Yap", use_container_width=True, type="primary",
            )
        st.markdown(
            '<div class="login-form-foot">'
            '  <span class="badge">Güvenli kurumsal oturum</span>'
            '  <span>© 2026 Norm Fasteners</span>'
            '</div>',
            unsafe_allow_html=True,
        )

    if not submitted:
        timer.finish()
        return

    error_msg: str | None = None

    if not username or not password:
        error_msg = "Kullanıcı adı ve şifre boş olamaz."
    else:
        try:
            with get_session() as session:
                user = authenticate(username.strip(), password, session)
                if user is None:
                    error_msg = "Kullanıcı adı veya şifre hatalı."
                else:
                    login_user(user)
        except OperationalError:
            error_msg = "Veritabanına bağlanılamıyor. Lütfen yöneticiye bildirin."
        except SQLAlchemyError:
            error_msg = "Veritabanı hatası oluştu. Lütfen tekrar deneyin."
        except Exception:
            error_msg = "Beklenmeyen bir hata oluştu."

    if error_msg:
        st.session_state["login_error"] = error_msg
        timer.finish()
        st.rerun()
    else:
        # Başarılı login — kullanıcıyı her zaman ana sayfaya götür.
        # st.switch_page Streamlit'in kendi nav state'ini doğru tutuyor;
        # eski JS history.replaceState hack'ine gerek yok.
        timer.finish()
        st.switch_page("pages/00_ana_sayfa.py")


# ---------------------------------------------------------------------------
# (Eski render_dashboard / render_sidebar callable'ları silindi —
#  ana sayfa artık pages/00_ana_sayfa.py içinde; st.switch_page ile
#  güvenli yönlendirme için bu zorunluydu. JS history hack'ı da
#  utils/auth.py'den temizlendi.)
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
restore_session_from_query()

if is_authenticated():
    pages = [
        st.Page("pages/00_ana_sayfa.py", title="Ana Sayfa", default=True),
        st.Page("pages/01_sayim_girisi.py", title="Sayım Girişi"),
        st.Page("pages/03_haftalik_takip.py", title="Haftalık Durum"),
        st.Page("pages/05_yetkililer.py", title="Yetkililer"),
    ]
    # Analiz ve admin paneli sadece adminlere açıktır.
    if st.session_state.get("role") == "admin":
        pages.insert(3, st.Page("pages/04_analiz.py", title="Analiz"))
        pages.append(st.Page("pages/99_admin.py", title="Admin Paneli"))

    # st.navigation routing yapsın — otomatik çizdiği sidebar nav'ı CSS ile
    # gizleyip ([data-testid="stSidebarNav"]) yerine kendi page_link
    # listesini elle çiziyoruz: brand üstte, sayfa linkleri ortada,
    # kullanıcı kart + logout altta.
    selected_page = st.navigation(pages)

    render_sidebar_brand(_LOGO_PATH)
    with st.sidebar:
        st.markdown('<div class="sidebar-nav-section">', unsafe_allow_html=True)
        for page in pages:
            st.page_link(page, label=page.title)
        st.markdown('</div>', unsafe_allow_html=True)

    selected_page.run()
else:
    render_login_form()
