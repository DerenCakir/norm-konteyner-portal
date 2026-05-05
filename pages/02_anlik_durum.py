"""
Anlık Durum - bölüm x renk matrisi.

Seçilen hafta için tüm aktif bölümleri ve aktif renkleri yan yana gösterir.
Hücre formatı: Boş/Dolu/Kanban.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from db.connection import get_session
from utils.auth import require_auth
from utils.cached_queries import (
    get_active_colors,
    get_active_sites_departments,
    get_available_weeks,
    get_week_count_details,
    get_week_submissions_with_users,
)
from utils.performance import page_timer
from utils.ui import (
    data_panel,
    empty_state,
    filter_bar,
    inject_css,
    kpi_card,
    page_header,
    render_kpis,
    render_sidebar_user,
    table_note,
)
from utils.week import current_week_iso, format_week_human


inject_css()
timer = page_timer("anlik_durum")

with get_session() as _s:
    me = require_auth(_s)
render_sidebar_user(me.full_name, me.role)

page_header(
    title="Anlık Durum",
    subtitle="Bölüm x renk matrisi - boş / dolu / kanban değerleri",
)


default_week = current_week_iso()
weeks = get_available_weeks(default_week)

filter_bar("Hafta filtresi", "Matriste görüntülenecek sayım haftasını seçin.")
selected_week = st.selectbox(
    "Hafta",
    weeks,
    index=0,
    format_func=lambda w: f"{w} - {format_week_human(w)}",
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
    st.markdown(
        empty_state(
            "Aktif renk bulunamadı",
            "Matrisi oluşturmak için en az bir aktif renk tanımlı olmalı.",
            badge="Veri gerekli",
            tone="warning",
        ),
        unsafe_allow_html=True,
    )
    st.stop()

rows: list[dict[str, object]] = []
for dept in sites_depts:
    sub = sub_by_dept.get(dept["department_id"])
    row: dict[str, object] = {
        "Üretim Yeri": dept["site_name"],
        "Bölüm": dept["department_name"],
        "Durum": (
            "-" if sub is None else
            ("Gönderildi" if sub["status"] == "submitted" else
             ("Geç" if sub["status"] == "late_submitted" else "Taslak"))
        ),
    }

    for color in active_colors:
        column_name = f"{color['name']}\n(B/D/K)"
        if sub is None:
            row[column_name] = "-"
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

render_kpis([
    kpi_card("Toplam Bölüm", f"{total_depts}", sub="Aktif bölüm sayısı"),
    kpi_card("Sayım Giren", f"{submitted}", sub="Seçili haftada kayıt var", tone="green"),
    kpi_card("Eksik", f"{missing}", sub="Henüz sayım girilmedi", tone="amber" if missing else "green"),
])

data_panel(
    "Bölüm x Renk Matrisi",
    "Hücreler boş / dolu / kanban sıralamasıyla okunur; tonaj değeri bölüm sayım kaydından gelir.",
)
st.dataframe(df, use_container_width=True, hide_index=True)
table_note("Hücreler: Boş / Dolu / Kanban sırasıyla.")

timer.finish()
