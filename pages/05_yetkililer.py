"""
Yetkililer — bölüm sorumluları ve haftalık sayım durumu.

Her aktif bölüm için yetkili kullanıcıları, kullanıcı durumlarını ve seçilen
haftada sayım girilip girilmediğini tek tabloda gösterir.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st
from sqlalchemy import select

from db.connection import get_session
from db.models import CountSubmission, Department, ProductionSite, User, UserDepartment
from utils.auth import require_auth, restore_session_from_cookie
from utils.ui import inject_css, page_header, render_sidebar_user
from utils.week import current_week_iso, format_week_human, now_tr


inject_css()
restore_session_from_cookie()

with get_session() as _s:
    me = require_auth(_s)
render_sidebar_user(me.full_name, me.role)

page_header(
    title="Yetkililer",
    subtitle="Bölüm sorumluları ve haftalık sayım giriş durumu",
)


# ---------------------------------------------------------------------------
# Hafta seçici
# ---------------------------------------------------------------------------
default_week = current_week_iso()

with get_session() as s:
    weeks = list(s.execute(
        select(CountSubmission.week_iso)
        .distinct()
        .order_by(CountSubmission.week_iso.desc())
    ).scalars())

if default_week not in weeks:
    weeks = [default_week] + weeks

selected_week = st.selectbox(
    "Hafta",
    weeks,
    index=0,
    format_func=lambda w: f"{w} — {format_week_human(w)}",
)


# ---------------------------------------------------------------------------
# Veriyi çek
# ---------------------------------------------------------------------------
with get_session() as s:
    sites_depts = list(s.execute(
        select(ProductionSite, Department)
        .join(Department, Department.production_site_id == ProductionSite.id)
        .where(Department.is_active.is_(True))
        .order_by(ProductionSite.name, Department.name)
    ).all())

    submissions = list(s.execute(
        select(CountSubmission, User)
        .join(User, CountSubmission.user_id == User.id)
        .where(CountSubmission.week_iso == selected_week)
    ).all())

    sub_by_dept: dict[int, tuple[CountSubmission, User]] = {
        sub.department_id: (sub, user) for sub, user in submissions
    }

    dept_users: dict[int, list[User]] = {}
    for dept_id, user in s.execute(
        select(UserDepartment.department_id, User)
        .join(User, User.id == UserDepartment.user_id)
        .order_by(User.full_name)
    ).all():
        dept_users.setdefault(dept_id, []).append(user)


total_depts = len(sites_depts)
submitted_count = sum(1 for _site, dept in sites_depts if dept.id in sub_by_dept)
missing_count = total_depts - submitted_count
assigned_count = sum(1 for _site, dept in sites_depts if dept_users.get(dept.id))
unassigned_count = total_depts - assigned_count

c1, c2, c3, c4 = st.columns(4)
c1.metric("Toplam Bölüm", total_depts)
c2.metric("Sayım Giren", submitted_count)
c3.metric("Eksik", missing_count)
c4.metric("Sorumlusuz Bölüm", unassigned_count)

st.divider()


def _status_label(status: str) -> str:
    return {
        "submitted": "Girdi",
        "late_submitted": "Geç Girdi",
        "draft": "Taslak",
    }.get(status, status)


def _format_users(users: list[User]) -> str:
    active_names = [u.full_name for u in users if u.is_active]
    inactive_names = [f"{u.full_name} (pasif)" for u in users if not u.is_active]
    names = active_names + inactive_names
    return ", ".join(names) if names else "Atanmamış"


rows: list[dict[str, object]] = []
for site, dept in sites_depts:
    entry = sub_by_dept.get(dept.id)
    users = dept_users.get(dept.id, [])

    if entry is None:
        count_status = "Eksik"
        entered_by = "-"
        submitted_at = "-"
        actual_tonnage = None
        late_flag = "Hayır"
    else:
        submission, submitter = entry
        count_status = _status_label(submission.status)
        entered_by = submitter.full_name
        submitted_at = (
            now_tr(submission.submitted_at).strftime("%Y-%m-%d %H:%M")
            if submission.submitted_at else "-"
        )
        actual_tonnage = float(submission.actual_tonnage) if submission.actual_tonnage else None
        late_flag = "Evet" if submission.status == "late_submitted" else "Hayır"

    rows.append({
        "Üretim Yeri": site.name,
        "Bölüm": dept.name,
        "Yetkili Kullanıcı(lar)": _format_users(users),
        "Aktif Yetkili Sayısı": sum(1 for u in users if u.is_active),
        "Sayım Durumu": count_status,
        "Giren Kullanıcı": entered_by,
        "Gönderim Zamanı": submitted_at,
        "Geç Giriş": late_flag,
        "Tonaj (t)": actual_tonnage,
    })

df = pd.DataFrame(rows)

status_filter = st.segmented_control(
    "Durum filtresi",
    ["Tümü", "Eksik", "Girdi", "Geç Girdi", "Sorumlusuz"],
    default="Tümü",
)

filtered = df
if status_filter == "Eksik":
    filtered = df[df["Sayım Durumu"] == "Eksik"]
elif status_filter == "Girdi":
    filtered = df[df["Sayım Durumu"] == "Girdi"]
elif status_filter == "Geç Girdi":
    filtered = df[df["Sayım Durumu"] == "Geç Girdi"]
elif status_filter == "Sorumlusuz":
    filtered = df[df["Aktif Yetkili Sayısı"] == 0]

st.dataframe(
    filtered,
    use_container_width=True,
    hide_index=True,
    column_config={
        "Tonaj (t)": st.column_config.NumberColumn("Tonaj (t)", format="%.2f"),
    },
)

st.caption(
    "Bu tablo, her bölüm için kimin yetkili olduğunu ve seçilen haftada sayımın girilip girilmediğini gösterir."
)
