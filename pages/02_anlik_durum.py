"""
Anlık Durum — bölüm × renk matrisi (tek hafta).

Tüm aktif bölümleri ve renkleri yan yana koyar; her hücrede
boş/dolu/kanban değerlerini gösterir. Kayıt yoksa hücre boş.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st
from sqlalchemy import select

from db.connection import get_session
from db.models import (
    Color,
    CountDetail,
    CountSubmission,
    Department,
    ProductionSite,
)
from utils.auth import require_auth, restore_session_from_cookie
from utils.ui import inject_css, page_header, render_sidebar_user
from utils.week import current_week_iso, format_week_human, week_iso_from_date


inject_css()
restore_session_from_cookie()

with get_session() as _s:
    me = require_auth(_s)
render_sidebar_user(me.full_name, me.role)

page_header(
    title="Anlık Durum",
    subtitle="Bölüm × renk matrisi — boş / dolu / kanban değerleri",
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

    active_colors = list(s.execute(
        select(Color).where(Color.is_active.is_(True)).order_by(Color.sort_order, Color.id)
    ).scalars())

    submissions = list(s.execute(
        select(CountSubmission).where(CountSubmission.week_iso == selected_week)
    ).scalars())

    # submissions[department_id] = CountSubmission
    sub_by_dept: dict[int, CountSubmission] = {sub.department_id: sub for sub in submissions}

    # details: keyed by (submission_id, color_id)
    detail_map: dict[tuple[int, int], CountDetail] = {}
    if submissions:
        sub_ids = [sub.id for sub in submissions]
        for d in s.execute(
            select(CountDetail).where(CountDetail.submission_id.in_(sub_ids))
        ).scalars():
            detail_map[(d.submission_id, d.color_id)] = d


# ---------------------------------------------------------------------------
# Tabloyu kur
# ---------------------------------------------------------------------------
if not active_colors:
    st.warning("Aktif renk yok.")
    st.stop()

rows: list[dict] = []
for site, dept in sites_depts:
    sub = sub_by_dept.get(dept.id)
    row: dict[str, object] = {
        "Üretim Yeri": site.name,
        "Bölüm": dept.name,
        "Durum": (
            "—" if sub is None else
            ("Gönderildi" if sub.status == "submitted" else
             ("Geç" if sub.status == "late_submitted" else "Taslak"))
        ),
    }
    for color in active_colors:
        if sub is None:
            row[f"{color.name}\n(B/D/K)"] = "—"
        else:
            d = detail_map.get((sub.id, color.id))
            if d is None:
                row[f"{color.name}\n(B/D/K)"] = "0/0/0"
            else:
                row[f"{color.name}\n(B/D/K)"] = f"{d.empty_count}/{d.full_count}/{d.kanban_count}"
    if sub is not None and sub.actual_tonnage is not None:
        row["Tonaj (t)"] = float(sub.actual_tonnage)
    else:
        row["Tonaj (t)"] = None
    rows.append(row)

df = pd.DataFrame(rows)

# Özet kartları
total_depts = len(sites_depts)
submitted = sum(1 for _s, _d in sites_depts if _d.id in sub_by_dept)
missing = total_depts - submitted

c1, c2, c3 = st.columns(3)
c1.metric("Toplam Bölüm", total_depts)
c2.metric("Sayım Giren", submitted)
c3.metric("Eksik", missing)

st.divider()
st.dataframe(df, use_container_width=True, hide_index=True)

st.caption("Hücreler: **Boş/Dolu/Kanban** sırasıyla.")
