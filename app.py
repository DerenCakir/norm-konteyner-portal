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
    require_auth,
    restore_session_from_query,
)
from utils.performance import page_timer
from utils.ui import (
    _logo_data_uri,
    flush_pending_toasts,
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
    format_schedule_human,
    format_week_human,
    get_submission_status,
    load_schedule,
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
    # Sidebar'ı login ekranında gizle (orijinal 845d40b kuralı).
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

    pending_error = st.session_state.pop("login_error", None)
    if pending_error:
        st.toast(f"⚠️ {pending_error}", icon="🚫")

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
            username = st.text_input(
                "Kullanıcı adı",
                placeholder="kullanici_adi",
                key="login_username_input",
            )
            password = st.text_input(
                "Şifre",
                type="password",
                placeholder="••••••••",
                key="login_password_input",
            )
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
    # st.rerun() — st.switch_page("app.py") entrypoint için desteklenmiyor
    # ve login'i tamamen kırıyordu. Trade-off: logout sonrası tekrar
    # girişte URL'in işaret ettiği sayfa açılabilir; ama login en azından
    # çalışıyor. "Always home" özelliği için ayrı bir yaklaşım gerekiyor.
    st.rerun()


# ---------------------------------------------------------------------------
# Dashboard (callable Page — file-tabanlı sayfa kullanmıyoruz çünkü
# st.switch_page'in yan etkileri var, manuel page_link listesi ile
# kontrol etmek istiyoruz)
# ---------------------------------------------------------------------------
def render_dashboard() -> None:
    timer = page_timer("ana_sayfa")
    flush_pending_toasts()

    full_name = st.session_state.get("full_name", "")
    role = st.session_state.get("role", "user")
    me_id = st.session_state.get("user_id")
    render_sidebar_user(full_name, role)

    week_iso = current_week_iso()
    week_human = format_week_human(week_iso)

    try:
        with get_session() as session:
            status = get_submission_status(week_iso, session, user_id=me_id)
            active_schedule = load_schedule(session)
    except SQLAlchemyError:
        st.error("Sayım durumu okunamadı (veritabanı hatası).")
        timer.finish()
        return

    is_admin_view = role == "admin"
    schedule_human = format_schedule_human(active_schedule)
    effective_status = status if is_admin_view else ("open" if status == "late" else status)

    status_label = {"open": "Açık", "late": "Geç giriş", "locked": "Kapalı"}[effective_status]
    status_kind = {"open": "success", "late": "warning", "locked": "info"}[effective_status]

    page_header(
        title=f"Hoş geldin, {full_name.split()[0] if full_name else ''}".strip(),
        subtitle=f"{week_human} · sayım penceresi {status_label.lower()}",
    )

    if effective_status == "open":
        status_title = "Sayım girişi şu an açık"
        status_text = f"{week_human} haftası için yetkili olduğunuz bölümlerde sayım girişi yapabilirsiniz."
        status_meta = "Aktif pencere"
    elif effective_status == "late":
        status_title = "Geç giriş penceresi açık"
        status_text = f"{week_human} haftası için manuel geç giriş açtınız."
        status_meta = "Admin onaylı"
    else:
        status_title = "Sayım girişi şu an kapalı"
        status_text = f"Bir sonraki giriş penceresi {schedule_human} arasında açılır."
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

    st.markdown('<div class="section-gap"></div>', unsafe_allow_html=True)

    if effective_status == "open":
        current_step_label = "Sayım Açık"
        current_step_tone = "success"
    elif effective_status == "late":
        current_step_label = "Geç Giriş Açık"
        current_step_tone = "warning"
    else:
        current_step_label = "Sayım Kapalı"
        current_step_tone = "info"

    st.markdown(
        f'<div class="process-header">'
        f'  <div class="process-header-titles">'
        f'    <div class="section-header-title">Sayım Süreci</div>'
        f'    <div class="section-header-sub">Bu hafta hangi adımdayız</div>'
        f'  </div>'
        f'  <div class="process-current-step process-current-step--{current_step_tone}">'
        f'    📍 {current_step_label}'
        f'  </div>'
        f'</div>',
        unsafe_allow_html=True,
    )
    st.markdown(process_diagram(effective_status, schedule_human), unsafe_allow_html=True)

    st.markdown('<div class="section-gap"></div>', unsafe_allow_html=True)
    section_header("Hızlı Erişim")
    if is_admin_view:
        qa1, qa2, qa3 = st.columns(3)
    else:
        qa1, qa2 = st.columns(2)
    qa1.markdown(
        quick_action_card("", "Sayım Girişi", "Haftalık sayımı girin", "sayim_girisi"),
        unsafe_allow_html=True,
    )
    qa2.markdown(
        quick_action_card("", "Haftalık Durum", "Giren/eksik bölümler + matris", "haftalik_takip"),
        unsafe_allow_html=True,
    )
    if is_admin_view:
        qa3.markdown(
            quick_action_card("", "Analiz", "Trend ve sapma analizi", "analiz"),
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
        st.Page("pages/03_haftalik_takip.py", title="Haftalık Durum"),
        st.Page("pages/05_yetkililer.py", title="Yetkililer"),
    ]
    if st.session_state.get("role") == "admin":
        pages.insert(3, st.Page("pages/04_analiz.py", title="Analiz"))
        pages.append(st.Page("pages/99_admin.py", title="Admin Paneli"))

    # st.navigation routing yapsın — otomatik çizdiği sidebar nav'ı CSS ile
    # gizleyip yerine kendi page_link listesini elle çiziyoruz: brand
    # üstte, sayfa linkleri ortada, kullanıcı kart + logout altta. Bu
    # yapı orijinal çalışan tasarım; her render'da sidebar dolu olduğu
    # için Streamlit "boş sidebar" diye gizlemiyor.
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
