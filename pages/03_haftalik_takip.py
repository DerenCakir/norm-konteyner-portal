"""
Haftalık Takip — seçilen hafta için giren/girmeyen bölümler.
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
timer = page_timer("haftalik_takip")

with get_session() as _s:
    me = require_auth(_s)
render_sidebar_user(me.full_name, me.role)

page_header(
    title="Haftalık Takip",
    subtitle="Bu hafta sayım giren ve girmeyen bölümler",
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
dept_users = get_department_users(include_inactive=False)

sub_by_dept = {sub["department_id"]: sub for sub in submissions}

total_depts = len(sites_depts)
submitted = sum(1 for dept in sites_depts if dept["department_id"] in sub_by_dept)
missing = total_depts - submitted
pct = (submitted / total_depts * 100) if total_depts else 0

c1, c2, c3, c4 = st.columns(4)
c1.metric("Toplam Bölüm", total_depts)
c2.metric("Giren", submitted)
c3.metric("Eksik", missing)
c4.metric("Tamamlanma", f"%{pct:.0f}")

st.divider()


tab_in, tab_out = st.tabs([f"Giren ({submitted})", f"Eksik ({missing})"])

with tab_in:
    if submitted == 0:
        st.info("Bu hafta için henüz sayım girilmemiş.")
    else:
        in_rows: list[dict[str, object]] = []
        for dept in sites_depts:
            sub = sub_by_dept.get(dept["department_id"])
            if sub is None:
                continue

            status_label = {
                "submitted": "Zamanında",
                "late_submitted": "Geç giriş",
                "draft": "Taslak",
            }.get(sub["status"], sub["status"])

            in_rows.append({
                "Üretim Yeri": dept["site_name"],
                "Bölüm": dept["department_name"],
                "Durum": status_label,
                "Giren Kullanıcı": sub["user_full_name"],
                "Sayım Tarihi": sub["count_date"],
                "Gönderim": (
                    sub["submitted_at"][:16].replace("T", " ")
                    if sub["submitted_at"] else "-"
                ),
                "Tonaj (t)": sub["actual_tonnage"],
            })

        st.dataframe(pd.DataFrame(in_rows), use_container_width=True, hide_index=True)

with tab_out:
    if missing == 0:
        st.success("Tüm bölümler sayımını girdi!")
    else:
        out_rows: list[dict[str, object]] = []
        for dept in sites_depts:
            if dept["department_id"] in sub_by_dept:
                continue

            users = dept_users.get(dept["department_id"], [])
            out_rows.append({
                "Üretim Yeri": dept["site_name"],
                "Bölüm": dept["department_name"],
                "Sorumlu Kullanıcı(lar)": (
                    ", ".join(user["full_name"] for user in users) or "Atanmamış"
                ),
                "Tonaj Hedefi": dept["weekly_tonnage_target"] or "-",
            })

        st.dataframe(pd.DataFrame(out_rows), use_container_width=True, hide_index=True)

timer.finish()
