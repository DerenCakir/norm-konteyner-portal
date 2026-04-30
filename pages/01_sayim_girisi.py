"""
Sayım Girişi — kullanıcı bu hafta için yetkili olduğu bölümün sayımını girer.

Akış:
  1. Yetki kontrolü (require_auth)
  2. Yetkili bölümleri listele (get_user_departments)
  3. Bölüm seçimi → bu hafta için form
  4. Submission status kontrol:
       open / late  → form aktif, submit edilebilir
       locked       → form görüntülenir ama submit kapalı
  5. Submit:
       - Aynı (department, week_iso) için tek kayıt — UPSERT
       - Renk bazlı detaylar yeniden yazılır
       - Status: open → 'submitted', late → 'late_submitted'
       - Audit log: count_submit (sadece submit, taslak yok)
"""

from __future__ import annotations

from datetime import date, time as dt_time
from decimal import Decimal

import streamlit as st
from sqlalchemy import select

from db.connection import get_session
from db.models import (
    AuditLog,
    Color,
    CountDetail,
    CountSubmission,
    Department,
    LateWindowOverride,
    ProductionSite,
)
from utils.auth import (
    get_user_departments,
    require_auth,
    restore_session_from_cookie,
    user_can_submit_for,
)
from utils.ui import inject_css, page_header, render_sidebar_user, status_pill
from utils.week import (
    current_week_iso,
    format_week_human,
    get_submission_status,
    now_tr,
)


inject_css()
restore_session_from_cookie()


# ---------------------------------------------------------------------------
# Yetki kontrolü
# ---------------------------------------------------------------------------
with get_session() as _s:
    me = require_auth(_s)
me_id = me.id
render_sidebar_user(me.full_name, me.role)

current_week = current_week_iso()

with get_session() as s:
    active_late_weeks = list(s.execute(
        select(LateWindowOverride.week_iso)
        .where(LateWindowOverride.closes_at > now_tr())
        .order_by(LateWindowOverride.week_iso.desc())
    ).scalars())

week_options = [current_week]
for late_week in active_late_weeks:
    if late_week not in week_options:
        week_options.append(late_week)
page_header(
    title="Sayım Girişi",
    subtitle="Yetkili bölüm için haftalık sayım",
    )


# ---------------------------------------------------------------------------
week_iso = st.selectbox(
    "Hafta",
    week_options,
    index=0,
    format_func=lambda w: f"{w} — {format_week_human(w)}",
)


# Yetkili bölümleri çek (üretim yeri adıyla birlikte)
# ---------------------------------------------------------------------------
with get_session() as s:
    my_depts = get_user_departments(me_id, s)
    dept_with_site: list[tuple[Department, str]] = []
    for d in my_depts:
        site = s.get(ProductionSite, d.production_site_id)
        dept_with_site.append((d, site.name if site else "-"))

if not dept_with_site:
    st.warning(
        "Henüz yetkili olduğun bir bölüm yok. "
        "Lütfen yöneticinden bölüm yetkisi atamasını iste."
    )
    st.stop()


# ---------------------------------------------------------------------------
# Bölüm seçimi
# ---------------------------------------------------------------------------
dept_options = {f"{site_name} — {d.name}": d.id for d, site_name in dept_with_site}
selected_label = st.selectbox("Bölüm seç", list(dept_options.keys()))
selected_dept_id = dept_options[selected_label]

# Seçilen bölümün tüm bilgileri
with get_session() as s:
    selected_dept = s.get(Department, selected_dept_id)
    selected_site = s.get(ProductionSite, selected_dept.production_site_id)
    target_tonnage = float(selected_dept.weekly_tonnage_target) if selected_dept.weekly_tonnage_target else None

col_a, col_b, col_c = st.columns(3)
col_a.metric("Üretim Yeri", selected_site.name)
col_b.metric("Bölüm", selected_dept.name)
col_c.metric(
    "Haftalık Tonaj Hedefi",
    f"{target_tonnage:.2f} t" if target_tonnage is not None else "-"
)


# ---------------------------------------------------------------------------
# Status kontrolü
# ---------------------------------------------------------------------------
with get_session() as s:
    status = get_submission_status(week_iso, s)

if status == "open":
    st.success("Sayım girişi açık (Cuma 09:00–12:00)")
elif status == "late":
    st.warning("Geç giriş penceresi açık")
else:
    st.error(
        "Sayım girişi şu an kapalı. "
        "Bir sonraki pencere: **Cuma 09.00 – 12.00** (Türkiye saati). "
        "Geç giriş için yöneticinizle iletişime geçin."
    )

can_submit = status in ("open", "late")


# ---------------------------------------------------------------------------
# Aktif renkleri ve mevcut kaydı çek
# ---------------------------------------------------------------------------
with get_session() as s:
    active_colors = list(s.execute(
        select(Color).where(Color.is_active.is_(True)).order_by(Color.sort_order, Color.id)
    ).scalars())

    existing = s.execute(
        select(CountSubmission).where(
            CountSubmission.department_id == selected_dept_id,
            CountSubmission.week_iso == week_iso,
        )
    ).scalar_one_or_none()

    existing_details: dict[int, CountDetail] = {}
    if existing is not None:
        for d in existing.details:
            existing_details[d.color_id] = d

# Form prefill değerleri
default_count_date = existing.count_date if existing else now_tr().date()
default_count_time = existing.count_time if existing else now_tr().time().replace(microsecond=0)
default_tonnage = float(existing.actual_tonnage) if existing and existing.actual_tonnage else 0.0


# ---------------------------------------------------------------------------
# Form
# ---------------------------------------------------------------------------
st.divider()
st.subheader("Konteyner Sayımı")

if existing is not None:
    st.info(
        f"Bu hafta için zaten bir kayıt var (durum: **{existing.status}**, "
        f"son güncelleme: {existing.updated_at:%Y-%m-%d %H:%M}). "
        "Yeni gönderim eskisinin üzerine yazar."
    )

with st.form("submission_form", clear_on_submit=False):
    cdate = st.date_input("Sayım tarihi", value=default_count_date, disabled=not can_submit)
    ctime = st.time_input("Sayım saati", value=default_count_time, disabled=not can_submit)
    tonnage = st.number_input(
        "Bu hafta gerçekleşen tonaj (ton)",
        value=default_tonnage, min_value=0.0, step=0.1, format="%.2f",
        disabled=not can_submit,
    )

    st.write("**Renk bazlı sayım**")
    color_inputs: dict[int, dict[str, int]] = {}

    # Tablo başlığı
    h1, h2, h3, h4 = st.columns([2, 1, 1, 1])
    h1.markdown("**Renk**")
    h2.markdown("**Boş**")
    h3.markdown("**Dolu**")
    h4.markdown("**Kanban**")

    for color in active_colors:
        prev = existing_details.get(color.id)
        prev_empty = prev.empty_count if prev else 0
        prev_full = prev.full_count if prev else 0
        prev_kanban = prev.kanban_count if prev else 0

        c1, c2, c3, c4 = st.columns([2, 1, 1, 1])
        c1.write(color.name)
        empty_v = c2.number_input(
            f"empty_{color.id}", value=prev_empty, min_value=0, step=1,
            label_visibility="collapsed", disabled=not can_submit,
        )
        full_v = c3.number_input(
            f"full_{color.id}", value=prev_full, min_value=0, step=1,
            label_visibility="collapsed", disabled=not can_submit,
        )
        kanban_v = c4.number_input(
            f"kanban_{color.id}", value=prev_kanban, min_value=0, step=1,
            label_visibility="collapsed", disabled=not can_submit,
        )
        color_inputs[color.id] = {
            "empty": int(empty_v), "full": int(full_v), "kanban": int(kanban_v)
        }

    submit_clicked = st.form_submit_button(
        "Gönder", use_container_width=True, disabled=not can_submit, type="primary",
    )


# ---------------------------------------------------------------------------
# Submit handling
# ---------------------------------------------------------------------------
if submit_clicked and can_submit:
    # Frontend validation: kanban <= full
    errors: list[str] = []
    for cid, vals in color_inputs.items():
        if vals["kanban"] > vals["full"]:
            color_name = next(c.name for c in active_colors if c.id == cid)
            errors.append(f"**{color_name}**: kanban ({vals['kanban']}) dolu ({vals['full']})'dan büyük olamaz.")

    if errors:
        for e in errors:
            st.error(e)
    else:
        # Yetki teyidi (defansif)
        with get_session() as s:
            if not user_can_submit_for(me_id, selected_dept_id, s):
                st.error("Bu bölüme sayım girme yetkiniz yok.")
                st.stop()

            # UPSERT
            sub = s.execute(
                select(CountSubmission).where(
                    CountSubmission.department_id == selected_dept_id,
                    CountSubmission.week_iso == week_iso,
                )
            ).scalar_one_or_none()

            new_status = "submitted" if status == "open" else "late_submitted"

            if sub is None:
                sub = CountSubmission(
                    department_id=selected_dept_id,
                    user_id=me_id,
                    week_iso=week_iso,
                    count_date=cdate,
                    count_time=ctime,
                    actual_tonnage=Decimal(str(tonnage)),
                    status=new_status,
                    submitted_at=now_tr(),
                )
                s.add(sub)
                s.flush()  # sub.id
            else:
                sub.user_id = me_id
                sub.count_date = cdate
                sub.count_time = ctime
                sub.actual_tonnage = Decimal(str(tonnage))
                sub.status = new_status
                sub.submitted_at = now_tr()
                # Eski detayları sil
                for d in list(sub.details):
                    s.delete(d)
                s.flush()

            # Yeni detayları ekle
            for cid, vals in color_inputs.items():
                s.add(CountDetail(
                    submission_id=sub.id,
                    color_id=cid,
                    empty_count=vals["empty"],
                    full_count=vals["full"],
                    kanban_count=vals["kanban"],
                ))

            # Audit
            s.add(AuditLog(
                user_id=me_id,
                action="count_submit",
                entity_type="count_submission",
                entity_id=sub.id,
                new_value={
                    "week_iso": week_iso,
                    "department_id": selected_dept_id,
                    "status": new_status,
                    "actual_tonnage": float(tonnage),
                    "details": {
                        str(cid): vals for cid, vals in color_inputs.items()
                    },
                },
            ))

        st.success(f"Sayım gönderildi. Durum: **{new_status}**")
        st.rerun()
