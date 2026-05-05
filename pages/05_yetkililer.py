"""
Yetkililer — bölüm sorumluları ve haftalık sayım durumu.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from db.connection import get_session
from utils.auth import require_auth, restore_session_from_cookie
from utils.cached_queries import (
    get_active_sites_departments,
    get_available_weeks,
    get_department_users,
    get_week_submissions_with_users,
)
from utils.performance import page_timer
from utils.ui import inject_css, page_header, render_sidebar_user
from utils.week import current_week_iso, format_week_human


inject_css()
restore_session_from_cookie()
timer = page_timer("yetkililer")

with get_session() as _s:
    me = require_auth(_s)
render_sidebar_user(me.full_name, me.role)

page_header(
    title="Yetkililer",
    subtitle="Bölüm sorumluları ve haftalık sayım giriş durumu",
)


default_week = current_week_iso()
weeks = get_available_weeks(default_week)

selected_week = st.selectbox(
    "Hafta",
    weeks,
    index=0,
    format_func=lambda w: f"{w} — {format_week_human(w)}",
)


sites_depts = get_active_sites_departments()
submissions = get_week_submissions_with_users(selected_week)
dept_users = get_department_users(include_inactive=True)

sub_by_dept = {sub["department_id"]: sub for sub in submissions}

total_depts = len(sites_depts)
submitted_count = sum(1 for dept in sites_depts if dept["department_id"] in sub_by_dept)
missing_count = total_depts - submitted_count
assigned_count = sum(1 for dept in sites_depts if dept_users.get(dept["department_id"]))
unassigned_count = total_depts - assigned_count

c1, c2, c3, c4 = st.columns(4)
c1.metric("Toplam Bölüm", total_depts)
c2.metric("Sayım Giren", submitted_count)
c3.metric("Eksik", missing_count)
c4.metric("Yetkilisi Olmayan", unassigned_count)

st.divider()


def _status_label(status: str) -> str:
    return {
        "submitted": "Girdi",
        "late_submitted": "Geç Girdi",
        "draft": "Taslak",
    }.get(status, status)


def _format_users(users: list[dict]) -> str:
    active_names = [user["full_name"] for user in users if user["is_active"]]
    inactive_names = [
        f"{user['full_name']} (pasif)"
        for user in users
        if not user["is_active"]
    ]
    names = active_names + inactive_names
    return ", ".join(names) if names else "Atanmamış"


def _assignment_status(users: list[dict]) -> str:
    active_count = sum(1 for user in users if user["is_active"])
    if active_count == 0:
        return "Yetkilisi Yok"
    if active_count == 1:
        return "Tek Yetkili"
    return "Mükerrer Yetki"


rows: list[dict[str, object]] = []
for dept in sites_depts:
    sub = sub_by_dept.get(dept["department_id"])
    users = dept_users.get(dept["department_id"], [])

    if sub is None:
        count_status = "Eksik"
        entered_by = "-"
        submitted_at = "-"
        actual_tonnage = None
        late_flag = "Hayır"
    else:
        count_status = _status_label(sub["status"])
        entered_by = sub["user_full_name"]
        submitted_at = (
            sub["submitted_at"][:16].replace("T", " ")
            if sub["submitted_at"] else "-"
        )
        actual_tonnage = sub["actual_tonnage"]
        late_flag = "Evet" if sub["status"] == "late_submitted" else "Hayır"

    rows.append({
        "Üretim Yeri": dept["site_name"],
        "Bölüm": dept["department_name"],
        "Yetkili Kullanıcı(lar)": _format_users(users),
        "Aktif Yetkili Sayısı": sum(1 for user in users if user["is_active"]),
        "Yetki Durumu": _assignment_status(users),
        "Sayım Durumu": count_status,
        "Giren Kullanıcı": entered_by,
        "Gönderim Zamanı": submitted_at,
        "Geç Giriş": late_flag,
        "Tonaj (t)": actual_tonnage,
    })

df = pd.DataFrame(rows)

status_filter = st.segmented_control(
    "Durum filtresi",
    ["Tümü", "Eksik Girilen", "Tamamlanan", "Geç Girilen", "Yetkilisi Olmayan"],
    default="Tümü",
)

filtered = df
if status_filter == "Eksik Girilen":
    filtered = df[df["Sayım Durumu"] == "Eksik"]
elif status_filter == "Tamamlanan":
    filtered = df[df["Sayım Durumu"] == "Girdi"]
elif status_filter == "Geç Girilen":
    filtered = df[df["Sayım Durumu"] == "Geç Girdi"]
elif status_filter == "Yetkilisi Olmayan":
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
timer.finish()
