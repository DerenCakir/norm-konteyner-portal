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
    page_header,
    process_diagram,
    quick_action_card,
    render_sidebar_brand,
    render_sidebar_user,
    section_header,
    status_panel,
)
from utils.week import (
    current_week_iso,
    format_week_human,
    get_submission_status,
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

    timer.finish()
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

    # Sade üst başlık — sadece selamlama, KPI yok, hero meta yok
    status_label = {"open": "Açık", "late": "Geç giriş", "locked": "Kapalı"}[status]
    status_kind = {"open": "success", "late": "warning", "locked": "info"}[status]

    page_header(
        title=f"Hoş geldin, {full_name.split()[0] if full_name else ''}".strip(),
        subtitle=f"{week_human} · sayım penceresi {status_label.lower()}",
    )

    # Tek büyük durum paneli — bu sayfanın asıl amacı bunu söylemek
    if status == "open":
        status_title = "Sayım girişi şu an açık"
        status_text = f"{week_human} haftası için yetkili olduğunuz bölümlerde sayım girişi yapabilirsiniz."
        status_meta = "Aktif pencere"
    elif status == "late":
        status_title = "Geç giriş penceresi açık"
        status_text = f"Yönetici {week_human} haftası için manuel geç giriş açtı."
        status_meta = "Admin onaylı"
    else:
        status_title = "Sayım girişi şu an kapalı"
        status_text = "Bir sonraki giriş penceresi Cuma 09.00 – 12.00 arasında açılır."
        status_meta = "Takip modu"

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

    # Süreç diyagramı — herkesin nerede olduğunu net görsün
    st.markdown('<div class="section-gap"></div>', unsafe_allow_html=True)
    section_header("Sayım Süreci", "Bu hafta hangi adımdayız")
    st.markdown(process_diagram(status), unsafe_allow_html=True)

    # Hızlı erişim — kısayollar
    st.markdown('<div class="section-gap"></div>', unsafe_allow_html=True)
    section_header("Hızlı Erişim")
    qa1, qa2, qa3, qa4 = st.columns(4)
    qa1.markdown(
        quick_action_card("", "Sayım Girişi", "Haftalık sayımı girin", "sayim_girisi"),
        unsafe_allow_html=True,
    )
    qa2.markdown(
        quick_action_card("", "Anlık Durum", "Bölüm × renk matrisi", "anlik_durum"),
        unsafe_allow_html=True,
    )
    qa3.markdown(
        quick_action_card("", "Analiz", "Trend ve sapma analizi", "analiz"),
        unsafe_allow_html=True,
    )
    qa4.markdown(
        quick_action_card("", "Haftalık Takip", "Giren ve eksik bölümler", "haftalik_takip"),
        unsafe_allow_html=True,
    )
    timer.finish()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
restore_session_from_query()

if is_authenticated():
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

    # Streamlit'in otomatik sidebar nav'ını kapat — kendi sidebar'ımızı
    # tamamen elle çiziyoruz: brand üstte, sayfa linkleri ortada, kullanıcı
    # kart + logout altta.
    selected_page = st.navigation(pages, position="hidden")

    render_sidebar_brand(_LOGO_PATH)
    with st.sidebar:
        st.markdown('<div class="sidebar-nav-section">', unsafe_allow_html=True)
        for page in pages:
            st.page_link(page, label=page.title)
        st.markdown('</div>', unsafe_allow_html=True)

    selected_page.run()
else:
    render_login_form()
