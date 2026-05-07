"""
Ana Sayfa — login sonrası ilk durak.

Eskiden app.py içinde ``render_dashboard`` callable'ı olarak duruyordu.
Streamlit'in ``st.switch_page`` API'si bir dosya yolu beklediği için
ana sayfayı kendi page dosyasına ayırdık; böylece login/logout
sonrasında ``st.switch_page("pages/00_ana_sayfa.py")`` ile güvenle
yönlendirebiliyoruz (URL/history hack'lerine gerek kalmadan).
"""

from __future__ import annotations

import streamlit as st
from sqlalchemy.exc import SQLAlchemyError

from db.connection import get_session
from utils.auth import require_auth, restore_session_from_query
from utils.performance import page_timer
from utils.ui import (
    flush_pending_toasts,
    inject_css,
    page_header,
    process_diagram,
    quick_action_card,
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


inject_css()
restore_session_from_query()
flush_pending_toasts()
timer = page_timer("ana_sayfa")

with get_session() as _s:
    me = require_auth(_s)
render_sidebar_user(me.full_name, me.role)

full_name = me.full_name
role = me.role

week_iso = current_week_iso()
week_human = format_week_human(week_iso)

try:
    with get_session() as session:
        status = get_submission_status(week_iso, session, user_id=me.id)
        active_schedule = load_schedule(session)
except SQLAlchemyError:
    st.error("Sayım durumu okunamadı (veritabanı hatası).")
    timer.finish()
    st.stop()

is_admin_view = role == "admin"
schedule_human = format_schedule_human(active_schedule)

# Kullanıcılara "geç giriş" terimi gösterilmez — admin'in açtığı late
# pencere de onlara "açık" olarak görünür.
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

# Süreç diyagramı: 2 durumlu (Açık / Kapalı). Sağ üstte küçük bir
# "şu an" pill'i.
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

# Hızlı erişim
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
