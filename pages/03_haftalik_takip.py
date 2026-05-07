"""
Haftalık Durum — bu hafta kim girdi, kim eksik + bölüm × renk matrisi.

Tek sayfada üç şerit:
  1) Tamamlanma göstergesi (X/42 girdi)
  2) Eksik bölümler tablosu — eylem odaklı
  3) Bölüm × renk matrisi — son hafta konteyner dağılımı
  + Giren bölümler expander'da gizli (gerekirse açılır)
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from db.connection import get_session
from utils.auth import require_auth, restore_session_from_query
from utils.cached_queries import (
    get_active_colors,
    get_active_sites_departments,
    get_available_weeks,
    get_department_users,
    get_week_count_details,
    get_week_submissions_with_users,
)
from utils.performance import page_timer
from utils.ui import (
    data_panel,
    empty_state,
    inject_css,
    page_header,
    progress_summary,
    render_sidebar_user,
    table_note,
)
from utils.week import current_week_iso, format_week_human


inject_css()
restore_session_from_query()
timer = page_timer("haftalik_durum")

with get_session() as _s:
    me = require_auth(_s)
render_sidebar_user(me.full_name, me.role)

page_header(
    title="Haftalık Durum",
    subtitle="Bu hafta giren/eksik bölümler ve konteyner dağılım matrisi",
)


# ---------------------------------------------------------------------------
# Hafta seçici
# ---------------------------------------------------------------------------
default_week = current_week_iso()
weeks = get_available_weeks(default_week)

selected_week = st.selectbox(
    "Hafta",
    weeks,
    index=0,
    format_func=lambda w: f"{w} — {format_week_human(w)}",
)


# ---------------------------------------------------------------------------
# Veri toplama
# ---------------------------------------------------------------------------
sites_depts = get_active_sites_departments()
active_colors = get_active_colors()
submissions = get_week_submissions_with_users(selected_week)
details = get_week_count_details(selected_week)
dept_users = get_department_users(include_inactive=False)

sub_by_dept = {sub["department_id"]: sub for sub in submissions}
detail_map = {
    (detail["submission_id"], detail["color_id"]): detail
    for detail in details
}

total_depts = len(sites_depts)
submitted = sum(1 for dept in sites_depts if dept["department_id"] in sub_by_dept)
missing = total_depts - submitted
pct = (submitted / total_depts * 100) if total_depts else 0


# ---------------------------------------------------------------------------
# 1) Tamamlanma göstergesi
# ---------------------------------------------------------------------------
progress_summary(
    f"{submitted} / {total_depts} bölüm sayım girdi",
    pct,
    helper=(
        "🎉 Tüm bölümler tamamlandı."
        if missing == 0
        else f"{missing} bölüm hâlâ bekliyor."
    ),
)
st.markdown('<div class="section-gap"></div>', unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# 2) Eksik bölümler — eylem odaklı
# ---------------------------------------------------------------------------
data_panel(
    f"⚠ Bekleyen Bölümler ({missing})",
    "Bu bölümlerin sorumluları sayım girişini henüz yapmadı.",
)

if missing == 0:
    st.markdown(
        empty_state(
            "Tüm bölümler tamamlandı",
            "Seçili haftada eksik bölüm bulunmuyor.",
            badge="Tamamlandı",
            tone="success",
        ),
        unsafe_allow_html=True,
    )
else:
    out_rows: list[dict[str, object]] = []
    for dept in sites_depts:
        if dept["department_id"] in sub_by_dept:
            continue
        # Defansif filtre — cache stale ise pasif kullanıcılar Sorumlu
        # sütununda gözükmesin. get_department_users zaten is_active=True
        # filtreliyor ama Railway multi-replica senaryosunda cache farklı
        # bir replica'da eski kalabiliyor.
        users = [
            u for u in dept_users.get(dept["department_id"], [])
            if u.get("is_active", True)
        ]
        sorumlu = ", ".join(u["full_name"] for u in users) if users else "⚠ Atanmamış"
        out_rows.append({
            "Üretim Yeri": dept["site_name"],
            "Bölüm": dept["department_name"],
            "Sorumlu": sorumlu,
        })
    st.dataframe(
        pd.DataFrame(out_rows),
        use_container_width=True,
        hide_index=True,
    )


st.markdown('<div class="section-gap"></div>', unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# 3) Bölüm × renk matrisi
# ---------------------------------------------------------------------------
data_panel(
    "Bölüm × Renk Matrisi",
    "Hücreler boş / dolu / kanban sırasıyla okunur. Tonaj sütunu bölümün haftalık sayım kaydından gelir.",
)

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
else:
    matrix_rows: list[dict[str, object]] = []
    for dept in sites_depts:
        sub = sub_by_dept.get(dept["department_id"])
        # Durum sütununu kaldırdık — kullanıcılar zaten satırların
        # dolu/boş olmasından girdi/girmedi olduğunu anlıyor.
        row: dict[str, object] = {
            "Üretim Yeri": dept["site_name"],
            "Bölüm": dept["department_name"],
        }

        for color in active_colors:
            column_name = f"{color['name']} (B/D/K/H)"
            if sub is None:
                row[column_name] = "-"
                continue

            detail = detail_map.get((sub["submission_id"], color["color_id"]))
            if detail is None:
                row[column_name] = "0/0/0/0"
            else:
                row[column_name] = (
                    f"{detail['empty_count']}/{detail['full_count']}"
                    f"/{detail['kanban_count']}/{detail.get('scrap_count', 0)}"
                )

        row["Tonaj"] = sub["actual_tonnage"] if sub else None
        matrix_rows.append(row)

    # Sütun genişliklerini açıkça small/medium yapalım — tonaj sağda
    # gizlenip kaydırma çubuğu arkasında kalmasın, hepsi tek bakışta okusun.
    color_col_config = {
        f"{color['name']} (B/D/K/H)": st.column_config.TextColumn(
            f"{color['name']} (B/D/K/H)", width="small"
        )
        for color in active_colors
    }
    st.dataframe(
        pd.DataFrame(matrix_rows),
        use_container_width=True,
        hide_index=True,
        column_config={
            "Üretim Yeri": st.column_config.TextColumn("Üretim Yeri", width="small"),
            "Bölüm": st.column_config.TextColumn("Bölüm", width="small"),
            **color_col_config,
            "Tonaj": st.column_config.NumberColumn("Tonaj", format="%d", width="small"),
        },
    )
    table_note(
        "Her renk hücresi: Boş / Dolu / Kanban / Hurdaya Ayrılacak sırasıyla."
    )


st.markdown('<div class="section-gap"></div>', unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# 4) Giren bölümler — expander içinde
# ---------------------------------------------------------------------------
with st.expander(f"✓ Sayım Giren Bölümler ({submitted})", expanded=False):
    if submitted == 0:
        st.markdown(
            empty_state(
                "Henüz sayım girilmedi",
                "Seçili hafta için kayıt oluştuğunda giren bölümler burada listelenecek.",
                badge="Veri bekleniyor",
                tone="info",
            ),
            unsafe_allow_html=True,
        )
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
                "Gönderim": (
                    sub["submitted_at"][:16].replace("T", " ")
                    if sub["submitted_at"] else "-"
                ),
                "Tonaj (t)": sub["actual_tonnage"],
            })
        st.dataframe(
            pd.DataFrame(in_rows),
            use_container_width=True,
            hide_index=True,
            column_config={
                "Tonaj (t)": st.column_config.NumberColumn("Tonaj (t)", format="%d"),
            },
        )


timer.finish()
