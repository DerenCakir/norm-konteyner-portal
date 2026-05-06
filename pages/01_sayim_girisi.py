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

from decimal import Decimal

import streamlit as st
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from db.connection import get_session
from db.models import (
    AuditLog,
    Color,
    CountDetail,
    CountSubmission,
    Department,
    LateUserWindowOverride,
    LateWindowOverride,
    ProductionSite,
    User,
    UserDepartment,
)
from utils.auth import (
    get_user_departments,
    require_auth,
    restore_session_from_query,
    user_can_submit_for,
)
from utils.cached_queries import clear_cached_queries
from utils.performance import page_timer
from utils.ui import (
    empty_state,
    inject_css,
    page_header,
    render_sidebar_user,
    status_panel,
)
from utils.week import (
    current_week_iso,
    format_week_human,
    get_submission_status,
    now_tr,
)


inject_css()
restore_session_from_query()
timer = page_timer("sayim_girisi")


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
    try:
        active_user_late_weeks = list(s.execute(
            select(LateUserWindowOverride.week_iso)
            .where(
                LateUserWindowOverride.user_id == me_id,
                LateUserWindowOverride.closes_at > now_tr(),
            )
            .order_by(LateUserWindowOverride.week_iso.desc())
        ).scalars())
    except SQLAlchemyError:
        active_user_late_weeks = []

week_options = [current_week]
for late_week in active_late_weeks:
    if late_week not in week_options:
        week_options.append(late_week)
for late_week in active_user_late_weeks:
    if late_week not in week_options:
        week_options.append(late_week)
page_header(
    title="Sayım Girişi",
    subtitle="Yetkili bölüm için haftalık sayım",
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
    st.markdown(
        empty_state(
            "Yetkili bölüm bulunamadı",
            "Sayım girişi yapabilmek için yöneticinizin size en az bir bölüm yetkisi ataması gerekir.",
            action_text="Bölüm yetkisi için sistem yöneticinizle iletişime geçin.",
            badge="Yetki gerekli",
            tone="warning",
        ),
        unsafe_allow_html=True,
    )
    timer.finish()
    st.stop()


# ---------------------------------------------------------------------------
# Hafta ve bölüm seçimi
# ---------------------------------------------------------------------------
dept_options = {f"{site_name} — {d.name}": d.id for d, site_name in dept_with_site}

select_week_col, select_dept_col = st.columns([1, 2])
week_iso = select_week_col.selectbox(
    "Hafta",
    week_options,
    index=0,
    format_func=lambda w: f"{w} — {format_week_human(w)}",
)
selected_label = select_dept_col.selectbox("Bölüm", list(dept_options.keys()))
selected_dept_id = dept_options[selected_label]

# Seçilen bölümün tüm bilgileri
with get_session() as s:
    selected_dept = s.get(Department, selected_dept_id)
    selected_site = s.get(ProductionSite, selected_dept.production_site_id)
    target_tonnage = float(selected_dept.weekly_tonnage_target) if selected_dept.weekly_tonnage_target else None

# ---------------------------------------------------------------------------
# Status kontrolü
# ---------------------------------------------------------------------------
with get_session() as s:
    status = get_submission_status(
        week_iso,
        s,
        user_id=me_id,
        department_id=selected_dept_id,
    )

status_meta = {
    "open": ("success", "Açık", "Sayım girişi açık", "Cuma 09.00 – 12.00 arasındasınız, kaydedebilirsiniz."),
    "late": ("warning", "Geç giriş", "Geç giriş penceresi açık", "Yönetici manuel ek süre açtı, kaydedebilirsiniz."),
    "locked": ("danger", "Kapalı", "Sayım girişi kapalı", "Bir sonraki pencere Cuma 09.00'da açılır. Acil değişiklik için yöneticiyle iletişime geçin."),
}
status_tone, status_badge_text, status_title, status_body = status_meta.get(status, status_meta["locked"])
st.markdown(
    status_panel(
        title=status_title,
        description=status_body,
        tone=status_tone,
        badge=status_badge_text,
    ),
    unsafe_allow_html=True,
)

can_submit = status in ("open", "late")

# Bölüm bilgisi tek satır — KPI kart yok, sadece tonaj hedefi + (varsa) çoklu yetkili notu
authorized_users_preview: list[str] = []
with get_session() as _s:
    authorized_users_preview = [
        u.full_name for u in _s.execute(
            select(User)
            .join(UserDepartment, UserDepartment.user_id == User.id)
            .where(
                UserDepartment.department_id == selected_dept_id,
                User.is_active.is_(True),
            )
            .order_by(User.full_name)
        ).scalars()
    ]

tonnage_part = (
    f'<span>Haftalık tonaj hedefi: <strong>{target_tonnage:.2f} t</strong></span>'
    if target_tonnage is not None
    else '<span>Haftalık tonaj hedefi: <strong>belirsiz</strong></span>'
)
multi_user_part = ""
if len(authorized_users_preview) > 1:
    names = ", ".join(authorized_users_preview)
    multi_user_part = (
        f'<span class="meta-warn">{len(authorized_users_preview)} yetkili kişi var: '
        f'{names}. Son kaydeden mevcudun üzerine yazar.</span>'
    )
st.markdown(
    f'<div class="dept-meta-row">{tonnage_part}{multi_user_part}</div>',
    unsafe_allow_html=True,
)


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
    existing_user = s.get(User, existing.user_id) if existing is not None else None
    authorized_users = list(s.execute(
        select(User)
        .join(UserDepartment, UserDepartment.user_id == User.id)
        .where(
            UserDepartment.department_id == selected_dept_id,
            User.is_active.is_(True),
        )
        .order_by(User.full_name)
    ).scalars())

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
# Bu bölüm + hafta için zaten kayıt varsa kullanıcıya tek satır info ver
if existing is not None:
    updater_name = existing_user.full_name if existing_user else "-"
    msg = (
        f"Bu hafta için daha önce kayıt var. Son giren: **{updater_name}** "
        f"({existing.updated_at:%d.%m %H:%M}). "
        + ("Kaydederseniz üzerine yazılır." if can_submit else "Düzeltme için yönetici gerekir.")
    )
    (st.warning if can_submit else st.info)(msg)

with st.form("submission_form", clear_on_submit=False):
    # Tarih + Saat + Tonaj
    info_date, info_time, info_tonnage = st.columns([1, 1, 1.2])
    cdate = info_date.date_input("Sayım tarihi", value=default_count_date, disabled=not can_submit)
    ctime = info_time.time_input("Sayım saati", value=default_count_time, disabled=not can_submit)
    tonnage = info_tonnage.number_input(
        "Gerçekleşen tonaj (ton)",
        value=default_tonnage, min_value=0.0, step=0.1, format="%.2f",
        disabled=not can_submit,
    )

    # Renk × Boş / Dolu / Kanban tablosu
    st.markdown('<div style="height:0.5rem"></div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="color-table-caption">'
        'Her renk için <strong>boş</strong> kaç tane var, <strong>dolu</strong> '
        'kaç tane var, <strong>doluların kaçı</strong> kanban — sırayla yazın.'
        '<div class="example-grid">'
        '  <div class="example-row">'
        '    <span class="ex-label">Örnek</span>'
        '    <span class="ex-cell"><b>100</b><small>boş</small></span>'
        '    <span class="ex-cell"><b>500</b><small>dolu (toplam)</small></span>'
        '    <span class="ex-cell"><b>100</b><small>bunlardan kanban</small></span>'
        '  </div>'
        '  <div class="example-note">Kanban (100), doluya (500) <strong>dahildir</strong>; '
        'doludan büyük olamaz.</div>'
        '</div>'
        '</div>',
        unsafe_allow_html=True,
    )
    color_inputs: dict[int, dict[str, int]] = {}
    color_warnings: list[str] = []

    h1, h2, h3, h4 = st.columns([2, 1, 1, 1.4])
    h1.markdown('<div class="color-table-head">Renk</div>', unsafe_allow_html=True)
    h2.markdown('<div class="color-table-head">Boş</div>', unsafe_allow_html=True)
    h3.markdown('<div class="color-table-head">Dolu (toplam)</div>', unsafe_allow_html=True)
    h4.markdown('<div class="color-table-head">Bunlardan Kanban</div>', unsafe_allow_html=True)

    for color in active_colors:
        prev = existing_details.get(color.id)
        prev_empty = prev.empty_count if prev else 0
        prev_full = prev.full_count if prev else 0
        prev_kanban = prev.kanban_count if prev else 0

        c1, c2, c3, c4 = st.columns([2, 1, 1, 1.4])
        c1.markdown(
            f'<div style="padding-top:0.7rem; font-weight:500;">{color.name}</div>',
            unsafe_allow_html=True,
        )
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

    submit_label = "Sayımı Güncelle" if existing is not None else "Gönder"
    submit_clicked = st.form_submit_button(
        submit_label, use_container_width=True, disabled=not can_submit, type="primary",
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
                timer.finish()
                st.stop()

            # UPSERT
            sub = s.execute(
                select(CountSubmission).where(
                    CountSubmission.department_id == selected_dept_id,
                    CountSubmission.week_iso == week_iso,
                )
            ).scalar_one_or_none()

            new_status = "submitted" if status == "open" else "late_submitted"
            old_value = None
            audit_action = "count_submit"

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
                audit_action = "count_update"
                old_value = {
                    "week_iso": sub.week_iso,
                    "department_id": sub.department_id,
                    "status": sub.status,
                    "actual_tonnage": float(sub.actual_tonnage) if sub.actual_tonnage else None,
                    "details": {
                        str(detail.color_id): {
                            "empty": detail.empty_count,
                            "full": detail.full_count,
                            "kanban": detail.kanban_count,
                        }
                        for detail in sub.details
                    },
                }
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
                action=audit_action,
                entity_type="count_submission",
                entity_id=sub.id,
                old_value=old_value,
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

        clear_cached_queries()
        success_text = "Sayım güncellendi." if audit_action == "count_update" else "Sayım gönderildi."
        st.success(f"{success_text} Durum: **{new_status}**")
        timer.finish()
        st.rerun()

timer.finish()
