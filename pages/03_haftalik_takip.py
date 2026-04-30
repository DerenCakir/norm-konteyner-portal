"""
Haftalık Takip — bu hafta giren/girmeyen bölümler.

İki sekme:
  - Sayım girenler (status, kim girdi, ne zaman, tonaj)
  - Eksik bölümler (sayım girmemiş)
"""

from __future__ import annotations

import pandas as pd
import streamlit as st
from sqlalchemy import select

from db.connection import get_session
from db.models import (
    CountSubmission,
    Department,
    ProductionSite,
    User,
    UserDepartment,
)
from utils.auth import require_auth, restore_session_from_cookie
from utils.ui import inject_css, page_header, render_sidebar_user
from utils.week import current_week_iso, format_week_human


inject_css()
restore_session_from_cookie()

with get_session() as _s:
    me = require_auth(_s)
render_sidebar_user(me.full_name, me.role)

page_header(
    title="Haftalık Takip",
    subtitle="Bu hafta sayım giren ve girmeyen bölümler",
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

    submissions_with_user = list(s.execute(
        select(CountSubmission, User)
        .join(User, CountSubmission.user_id == User.id)
        .where(CountSubmission.week_iso == selected_week)
    ).all())

    sub_by_dept: dict[int, tuple[CountSubmission, User]] = {
        sub.department_id: (sub, user) for sub, user in submissions_with_user
    }

    dept_users: dict[int, list[str]] = {}
    for dept_id, full_name in s.execute(
        select(UserDepartment.department_id, User.full_name)
        .join(User, User.id == UserDepartment.user_id)
        .where(User.is_active.is_(True))
        .order_by(User.full_name)
    ).all():
        dept_users.setdefault(dept_id, []).append(full_name)


# ---------------------------------------------------------------------------
# Özet kartları
# ---------------------------------------------------------------------------
total_depts = len(sites_depts)
submitted = sum(1 for _s, d in sites_depts if d.id in sub_by_dept)
missing = total_depts - submitted

c1, c2, c3, c4 = st.columns(4)
c1.metric("Toplam Bölüm", total_depts)
c2.metric("Giren", submitted)
c3.metric("Eksik", missing)
pct = (submitted / total_depts * 100) if total_depts else 0
c4.metric("Tamamlanma", f"%{pct:.0f}")

st.divider()


# ---------------------------------------------------------------------------
# Sekmeler
# ---------------------------------------------------------------------------
tab_in, tab_out = st.tabs([f"Giren ({submitted})", f"Eksik ({missing})"])

with tab_in:
    if submitted == 0:
        st.info("Bu hafta için henüz sayım girilmemiş.")
    else:
        in_rows: list[dict] = []
        for site, dept in sites_depts:
            entry = sub_by_dept.get(dept.id)
            if entry is None:
                continue
            sub, user = entry
            status_label = {
                "submitted": "Zamanında",
                "late_submitted": "Geç giriş",
                "draft": "Taslak",
            }.get(sub.status, sub.status)
            in_rows.append({
                "Üretim Yeri": site.name,
                "Bölüm": dept.name,
                "Durum": status_label,
                "Giren Kullanıcı": user.full_name,
                "Sayım Tarihi": str(sub.count_date),
                "Gönderim": (
                    sub.submitted_at.strftime("%Y-%m-%d %H:%M") if sub.submitted_at else "-"
                ),
                "Tonaj (t)": float(sub.actual_tonnage) if sub.actual_tonnage else None,
            })
        st.dataframe(pd.DataFrame(in_rows), use_container_width=True, hide_index=True)

with tab_out:
    if missing == 0:
        st.success("Tüm bölümler sayımını girdi!")
    else:
        out_rows: list[dict] = []
        for site, dept in sites_depts:
            if dept.id in sub_by_dept:
                continue
            out_rows.append({
                "Üretim Yeri": site.name,
                "Bölüm": dept.name,
                "Sorumlu Kullanıcı(lar)": (
                    ", ".join(dept_users.get(dept.id, [])) or "Atanmamış"
                ),
                "Tonaj Hedefi": (
                    float(dept.weekly_tonnage_target)
                    if dept.weekly_tonnage_target else "-"
                ),
            })
        st.dataframe(pd.DataFrame(out_rows), use_container_width=True, hide_index=True)
