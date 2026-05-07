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
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
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
    flush_pending_toasts,
    inject_css,
    page_header,
    queue_toast,
    render_sidebar_user,
    status_panel,
)
from utils.week import (
    current_week_iso,
    format_schedule_human,
    format_week_human,
    get_submission_status,
    load_schedule,
    now_tr,
)


inject_css()
restore_session_from_query()
flush_pending_toasts()
timer = page_timer("sayim_girisi")


# ---------------------------------------------------------------------------
# Yetki kontrolü
# ---------------------------------------------------------------------------
with get_session() as _s:
    me = require_auth(_s)
me_id = me.id
me_role = me.role
is_admin = me_role == "admin"
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

# Aktif takvimi al (kullanıcılara "geç giriş" terimi gösterilmez —
# pencere kavramı tek tip "açık/kapalı" sunulur. Admin için late state'i
# ayrıca görünür kalır.)
with get_session() as _s_sched:
    active_schedule = load_schedule(_s_sched)
schedule_human = format_schedule_human(active_schedule)

if is_admin:
    status_meta = {
        "open": ("success", "Açık", "Sayım girişi açık",
                 f"{schedule_human} arasındasınız, kaydedebilirsiniz."),
        "late": ("warning", "Geç giriş", "Geç giriş penceresi açık",
                 "Yönetici manuel ek süre açtı, kaydedebilirsiniz."),
        "locked": ("danger", "Kapalı", "Sayım girişi kapalı",
                   f"Bir sonraki pencere {schedule_human}'da açılır."),
    }
else:
    # Kullanıcılar için 'late' durumu "açık" olarak sunulur. Geç giriş
    # kavramının duyurulması suistimale açık olduğu için, kullanıcı
    # sadece "şu an açık" ya da "kapalı" görür.
    user_open_meta = (
        "success", "Açık", "Sayım girişi açık",
        "Sayımı girip kaydedebilirsiniz.",
    )
    user_locked_meta = (
        "danger", "Kapalı", "Sayım girişi kapalı",
        "Şu an sayım girişi açık değil. Acil bir durum varsa yöneticinizle "
        "iletişime geçiniz.",
    )
    status_meta = {
        "open": user_open_meta,
        "late": user_open_meta,
        "locked": user_locked_meta,
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

# Tonaj prefill: kayıt yoksa boş (None) — kutuya tıklanınca rakam yazmaya
# başlandığında baştaki "0" yerine boş başlasın. Mevcut kayıt varsa o
# değer prefill olur.
default_tonnage = (
    float(existing.actual_tonnage)
    if existing is not None and existing.actual_tonnage is not None
    else None
)


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

    # Widget keys must change whenever (department, week) changes; otherwise
    # Streamlit reuses the previous session_state value and ignores the
    # `value=` prefill, leading to stale displays and silent overwrites
    # when the user navigates between departments. Scope every input by
    # (selected_dept_id, week_iso).
form_scope = f"{selected_dept_id}_{week_iso}"

with st.form(f"submission_form_{form_scope}", clear_on_submit=False):
    # Tarih ve saat müdahaleye kapalı — kayıt anında otomatik atanır.
    # Sadece tonaj girişi alıyoruz; üstte küçük bir bilgi satırı.
    st.caption(
        "Tarih ve saat sayımı kaydederken otomatik olarak işlenir; manuel "
        "değiştirilemez."
    )
    # Tonaj alanını öne çıkar — formun en kritik tek-değer girişi.
    st.markdown('<div class="tonnage-field">', unsafe_allow_html=True)
    tonnage = st.number_input(
        "Yarı mamül tonajı (toplam) — ton",
        value=default_tonnage, min_value=0.0, step=0.1, format="%g",
        disabled=not can_submit,
        key=f"sayim_tonnage_{form_scope}",
        placeholder="örn. 1234",
    )
    st.markdown('</div>', unsafe_allow_html=True)

    # Renk × Boş / Dolu / Kanban / Hurda tablosu
    st.markdown('<div style="height:0.5rem"></div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="color-table-caption">'
        'Her renk için <strong>boş</strong>, <strong>dolu</strong>, '
        '<strong>doluların kaçı</strong> kanban ve '
        '<strong>hurdaya ayrılacak</strong> — sırayla yazın.'
        '<div class="example-grid">'

        # --- Birinci örnek: Boş / Dolu / Kanban ---
        '  <div class="example-block">'
        '    <div class="example-row">'
        '      <span class="ex-label">Örnek</span>'
        '      <span class="ex-cell"><b>100</b><small>boş</small></span>'
        '      <span class="ex-cell"><b>500</b><small>dolu (toplam)</small></span>'
        '      <span class="ex-cell"><b>100</b><small>kanban</small></span>'
        '    </div>'
        '    <div class="example-note example-note--include">'
        '      ✓ Kanban (100), doluya (500) <strong>dahildir</strong>; doludan büyük olamaz.'
        '    </div>'
        '  </div>'

        # --- İkinci örnek: Hurda ---
        '  <div class="example-block">'
        '    <div class="example-row">'
        '      <span class="ex-label">Örnek</span>'
        '      <span class="ex-cell"><b>5</b><small>hurdaya ayrılacak</small></span>'
        '    </div>'
        '    <div class="example-note example-note--exclude">'
        '      ✕ Hurdaya ayrılacak — artık kullanılmayacak konteynerler (ayağı kırık vs). '
        'Boş ve dolu sayılarına <strong>dahil değildir</strong>, ayrı sayılır.'
        '    </div>'
        '  </div>'

        '</div>'
        '</div>',
        unsafe_allow_html=True,
    )
    color_inputs: dict[int, dict[str, int]] = {}
    color_warnings: list[str] = []

    h1, h2, h3, h4, h5 = st.columns([2, 1, 1, 1.2, 1.4])
    h1.markdown('<div class="color-table-head">Renk</div>', unsafe_allow_html=True)
    h2.markdown('<div class="color-table-head">Boş</div>', unsafe_allow_html=True)
    h3.markdown('<div class="color-table-head">Dolu (toplam)</div>', unsafe_allow_html=True)
    h4.markdown('<div class="color-table-head">Kanban</div>', unsafe_allow_html=True)
    h5.markdown('<div class="color-table-head">Hurdaya Ayrılacak</div>', unsafe_allow_html=True)

    for color in active_colors:
        prev = existing_details.get(color.id)
        # value=None → kutu boş açılır; kullanıcı tıklayıp rakam yazmaya
        # başladığında baştaki sıfırla uğraşmaz. Mevcut kayıt varsa o
        # sayı prefill olur.
        prev_empty = prev.empty_count if prev is not None else None
        prev_full = prev.full_count if prev is not None else None
        prev_kanban = prev.kanban_count if prev is not None else None
        prev_scrap = prev.scrap_count if prev is not None else None

        c1, c2, c3, c4, c5 = st.columns([2, 1, 1, 1.2, 1.4])
        c1.markdown(
            f'<div style="padding-top:0.7rem; font-weight:500;">{color.name}</div>',
            unsafe_allow_html=True,
        )
        empty_v = c2.number_input(
            f"{color.name} — Boş",
            key=f"sayim_empty_{form_scope}_{color.id}",
            value=prev_empty, min_value=0, step=1,
            label_visibility="collapsed", disabled=not can_submit,
            placeholder="0",
        )
        full_v = c3.number_input(
            f"{color.name} — Dolu",
            key=f"sayim_full_{form_scope}_{color.id}",
            value=prev_full, min_value=0, step=1,
            label_visibility="collapsed", disabled=not can_submit,
            placeholder="0",
        )
        kanban_v = c4.number_input(
            f"{color.name} — Kanban",
            key=f"sayim_kanban_{form_scope}_{color.id}",
            value=prev_kanban, min_value=0, step=1,
            label_visibility="collapsed", disabled=not can_submit,
            placeholder="0",
        )
        scrap_v = c5.number_input(
            f"{color.name} — Hurdaya Ayrılacak",
            key=f"sayim_scrap_{form_scope}_{color.id}",
            value=prev_scrap, min_value=0, step=1,
            label_visibility="collapsed", disabled=not can_submit,
            placeholder="0",
        )
        # Boş bırakılan kutuyu 0 olarak değerlendir.
        color_inputs[color.id] = {
            "empty": int(empty_v) if empty_v is not None else 0,
            "full": int(full_v) if full_v is not None else 0,
            "kanban": int(kanban_v) if kanban_v is not None else 0,
            "scrap": int(scrap_v) if scrap_v is not None else 0,
        }

    submit_label = "Güncelle" if existing is not None else "Kaydet"
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
        # Tarih/saat müdahaleye kapalı; her kayıt/güncellemede şu anki
        # TR zamanı yazılır.
        submit_now = now_tr()
        cdate = submit_now.date()
        ctime = submit_now.time().replace(microsecond=0)

        # Boş bırakılan tonajı 0 olarak ele al.
        tonnage_value = float(tonnage) if tonnage is not None else 0.0

        # No-change detection: if the form values match the existing
        # submission exactly, skip the DB write to keep the audit log
        # clean and tell the user nothing happened. Tarih/saat değişimi
        # sayılmaz (otomatik atanıyor).
        new_tonnage_dec = Decimal(str(tonnage_value)).quantize(Decimal("0.01"))
        unchanged = False
        if existing is not None:
            existing_tonnage_dec = (
                Decimal(str(existing.actual_tonnage)).quantize(Decimal("0.01"))
                if existing.actual_tonnage is not None
                else Decimal("0.00")
            )
            same_meta = existing_tonnage_dec == new_tonnage_dec
            same_details = all(
                (
                    existing_details.get(cid) is not None
                    and existing_details[cid].empty_count == vals["empty"]
                    and existing_details[cid].full_count == vals["full"]
                    and existing_details[cid].kanban_count == vals["kanban"]
                    and existing_details[cid].scrap_count == vals["scrap"]
                )
                for cid, vals in color_inputs.items()
            ) and len(existing_details) == len(color_inputs)
            unchanged = same_meta and same_details

        if unchanged:
            queue_toast("Değişiklik yapılmadı — değerler zaten kayıtlı.", icon="ℹ️")
            timer.finish()
            st.rerun()

        # Yetki teyidi (defansif) — bu kullanıcı hâlâ aktif mi ve bu
        # bölüme yazabiliyor mu? Sayfa yüklendikten sonra admin yetki
        # kaldırabilir veya hesabı pasifleştirebilir; submit anında
        # tekrar kontrol edip eski oturumun "açık kalması" boşluğunu
        # kapatıyoruz.
        with get_session() as s:
            fresh_user = s.get(User, me_id)
            if fresh_user is None or not fresh_user.is_active:
                st.error("Hesabınız artık aktif değil. Lütfen tekrar giriş yapın.")
                timer.finish()
                st.stop()
            if not user_can_submit_for(me_id, selected_dept_id, s):
                st.error("Bu bölüme sayım girme yetkiniz yok.")
                timer.finish()
                st.stop()

            new_status = "submitted" if status == "open" else "late_submitted"
            submit_ts = now_tr()

            # Old value snapshot (audit için) — kayıt zaten varsa eski
            # halini logla. Yarış koşulu olmaması için aynı transaction'da
            # SELECT FOR UPDATE ile satırı kilitliyoruz.
            sub = s.execute(
                select(CountSubmission)
                .where(
                    CountSubmission.department_id == selected_dept_id,
                    CountSubmission.week_iso == week_iso,
                )
                .with_for_update()
            ).scalar_one_or_none()

            old_value = None
            audit_action = "count_submit"
            if sub is not None:
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
                            "scrap": detail.scrap_count,
                        }
                        for detail in sub.details
                    },
                }

            # PostgreSQL native UPSERT — atomik, yarış koşulu yok.
            # Aynı (dept, week) için iki kullanıcı milisaniye farkıyla
            # çakışsa bile son yazan ON CONFLICT branch'ine düşer ve
            # UNIQUE constraint ihlali atılmaz.
            sub_stmt = (
                pg_insert(CountSubmission.__table__)
                .values(
                    department_id=selected_dept_id,
                    user_id=me_id,
                    week_iso=week_iso,
                    count_date=cdate,
                    count_time=ctime,
                    actual_tonnage=new_tonnage_dec,
                    status=new_status,
                    submitted_at=submit_ts,
                )
                .on_conflict_do_update(
                    index_elements=["department_id", "week_iso"],
                    set_={
                        "user_id": me_id,
                        "count_date": cdate,
                        "count_time": ctime,
                        "actual_tonnage": new_tonnage_dec,
                        "status": new_status,
                        "submitted_at": submit_ts,
                    },
                )
                .returning(CountSubmission.__table__.c.id)
            )
            sub_id = s.execute(sub_stmt).scalar_one()

            # Detayları aynı atomiklik garantisiyle yaz: eskileri sil,
            # yenilerini at — hepsi bu transaction içinde, dış dünya
            # commit'ten önce hiçbir şey görmez.
            s.execute(
                delete(CountDetail).where(CountDetail.submission_id == sub_id)
            )
            s.execute(
                CountDetail.__table__.insert(),
                [
                    {
                        "submission_id": sub_id,
                        "color_id": cid,
                        "empty_count": vals["empty"],
                        "full_count": vals["full"],
                        "kanban_count": vals["kanban"],
                        "scrap_count": vals["scrap"],
                    }
                    for cid, vals in color_inputs.items()
                ],
            )

            # Audit
            s.add(AuditLog(
                user_id=me_id,
                action=audit_action,
                entity_type="count_submission",
                entity_id=sub_id,
                old_value=old_value,
                new_value={
                    "week_iso": week_iso,
                    "department_id": selected_dept_id,
                    "status": new_status,
                    "actual_tonnage": tonnage_value,
                    "details": {
                        str(cid): vals for cid, vals in color_inputs.items()
                    },
                },
            ))

        clear_cached_queries()
        success_text = "Sayım güncellendi." if audit_action == "count_update" else "Sayım kaydedildi."
        queue_toast(success_text, icon="✅")
        timer.finish()
        st.rerun()

timer.finish()
