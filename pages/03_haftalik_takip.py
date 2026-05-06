"""
Haftalık Takip — bu hafta hangi bölüm sayım girdi, kim hâlâ bekliyor.

Sadeleştirilmiş eylem-odaklı sayfa: en üstte tek büyük tamamlanma
göstergesi, hemen ardından "kim hatırlatmalı" diye eksik bölümler
listesi, en altta secondary olarak giren bölümler.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from db.connection import get_session
from utils.auth import require_auth, restore_session_from_query
from utils.cached_queries import (
    get_active_sites_departments,
    get_available_weeks,
    get_department_users,
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
)
from utils.week import current_week_iso, format_week_human


inject_css()
restore_session_from_query()
timer = page_timer("haftalik_takip")

with get_session() as _s:
    me = require_auth(_s)
render_sidebar_user(me.full_name, me.role)

page_header(
    title="Haftalık Takip",
    subtitle="Bu hafta sayım giren ve hâlâ bekleyen bölümler",
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
submissions = get_week_submissions_with_users(selected_week)
dept_users = get_department_users(include_inactive=False)

sub_by_dept = {sub["department_id"]: sub for sub in submissions}

total_depts = len(sites_depts)
submitted = sum(1 for dept in sites_depts if dept["department_id"] in sub_by_dept)
missing = total_depts - submitted
pct = (submitted / total_depts * 100) if total_depts else 0


# ---------------------------------------------------------------------------
# Tek büyük tamamlanma göstergesi (4 KPI yerine bunu kullanıyoruz)
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
# 1) Eksik bölümler — eylem odaklı, üstte
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
        users = dept_users.get(dept["department_id"], [])
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
# 2) Giren bölümler — secondary, expander içinde
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
                "Tonaj (t)": st.column_config.NumberColumn("Tonaj (t)", format="%.2f"),
            },
        )


timer.finish()
