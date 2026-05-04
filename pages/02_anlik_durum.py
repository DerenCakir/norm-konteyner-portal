"""
Anlık Durum — bölüm × renk matrisi.

Seçilen hafta için tüm aktif bölümleri ve aktif renkleri yan yana gösterir.
Hücre formatı: Boş/Dolu/Kanban.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from db.connection import get_session
from utils.auth import require_auth, restore_session_from_cookie
from utils.cached_queries import (
    get_active_colors,
    get_active_sites_departments,
    get_available_weeks,
    get_week_count_details,
    get_week_submissions_with_users,
)
from utils.ui import inject_css, page_header, render_sidebar_user
from utils.week import current_week_iso, format_week_human


inject_css()
restore_session_from_cookie()

with get_session() as _s:
    me = require_auth(_s)
render_sidebar_user(me.full_name, me.role)

page_header(
    title="Anlık Durum",
    subtitle="Bölüm × renk matrisi — boş / dolu / kanban değerleri",
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
active_colors = get_active_colors()
submissions = get_week_submissions_with_users(selected_week)
details = get_week_count_details(selected_week)

sub_by_dept = {sub["department_id"]: sub for sub in submissions}
detail_map = {
    (detail["submission_id"], detail["color_id"]): detail
    for detail in details
}

if not active_colors:
    st.warning("Aktif renk yok.")
    st.stop()

rows: list[dict[str, object]] = []
for dept in sites_depts:
    sub = sub_by_dept.get(dept["department_id"])
    row: dict[str, object] = {
        "Üretim Yeri": dept["site_name"],
        "Bölüm": dept["department_name"],
        "Durum": (
            "—" if sub is None else
            ("Gönderildi" if sub["status"] == "submitted" else
             ("Geç" if sub["status"] == "late_submitted" else "Taslak"))
        ),
    }

    for color in active_colors:
        column_name = f"{color['name']}\n(B/D/K)"
        if sub is None:
            row[column_name] = "—"
            continue

        detail = detail_map.get((sub["submission_id"], color["color_id"]))
        if detail is None:
            row[column_name] = "0/0/0"
        else:
            row[column_name] = (
                f"{detail['empty_count']}/{detail['full_count']}/{detail['kanban_count']}"
            )

    row["Tonaj (t)"] = sub["actual_tonnage"] if sub else None
    rows.append(row)

df = pd.DataFrame(rows)

total_depts = len(sites_depts)
submitted = sum(1 for dept in sites_depts if dept["department_id"] in sub_by_dept)
missing = total_depts - submitted

c1, c2, c3 = st.columns(3)
c1.metric("Toplam Bölüm", total_depts)
c2.metric("Sayım Giren", submitted)
c3.metric("Eksik", missing)

st.divider()
st.dataframe(df, use_container_width=True, hide_index=True)

st.caption("Hücreler: **Boş/Dolu/Kanban** sırasıyla.")
