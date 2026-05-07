"""
Yetkililer — bölüm sorumluları ve haftalık sayım durumu.

Görünüm role göre değişir:
  - Regular kullanıcı: kendi bölümleri üstte vurgulu, diğer bölümler basit
    bir liste (bölüm, sorumlu kişiler, sayım durumu).
  - Admin: tüm detaylı tablo (gönderim zamanı, tonaj, geç giriş bayrağı,
    yetki durumu, durum filtresi) — eski admin-odaklı görünümün aynısı.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from db.connection import get_session
from utils.auth import (
    get_user_departments,
    require_auth,
    restore_session_from_query,
)
from utils.cached_queries import (
    get_active_sites_departments,
    get_available_weeks,
    get_department_users,
    get_week_submissions_with_users,
)
from utils.performance import page_timer
from utils.ui import (
    data_panel,
    inject_css,
    page_header,
    render_sidebar_user,
    table_note,
)
from utils.week import current_week_iso, format_week_human


inject_css()
restore_session_from_query()
timer = page_timer("yetkililer")

with get_session() as _s:
    me = require_auth(_s)
    my_depts = get_user_departments(me.id, _s)
    my_dept_ids = {d.id for d in my_depts}

is_admin = me.role == "admin"
render_sidebar_user(me.full_name, me.role)

page_header(
    title="Yetkililer",
    subtitle=(
        "Tüm bölümlerin sorumluları ve haftalık sayım durumu"
        if is_admin
        else "Bölüm sorumluları ve sayım durumu"
    ),
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
# Veri
# ---------------------------------------------------------------------------
sites_depts = get_active_sites_departments()
submissions = get_week_submissions_with_users(selected_week)
# Pasif kullanıcılar yetkili tablosunda görünmesin — admin de olsa
# silinen kullanıcıları operasyonel listelerde göstermek istemiyoruz.
dept_users = get_department_users(include_inactive=False)

sub_by_dept = {sub["department_id"]: sub for sub in submissions}


def _status_label(status: str) -> str:
    return {
        "submitted": "Girdi",
        "late_submitted": "Geç Girdi",
        "draft": "Taslak",
    }.get(status, status)


def _format_users(users: list[dict]) -> str:
    # dept_users zaten sadece aktif kullanıcıları döndürüyor; defansif
    # ek filtre cache stale ise pasif kullanıcı sızmasın.
    active_names = [u["full_name"] for u in users if u.get("is_active", True)]
    return ", ".join(active_names) if active_names else "Atanmamış"


def _simple_row(dept: dict) -> dict[str, object]:
    sub = sub_by_dept.get(dept["department_id"])
    users = dept_users.get(dept["department_id"], [])
    return {
        "Üretim Yeri": dept["site_name"],
        "Bölüm": dept["department_name"],
        "Yetkili Kullanıcılar": _format_users(users),
        "Sayım Durumu": _status_label(sub["status"]) if sub else "Eksik",
    }


# ---------------------------------------------------------------------------
# Regular kullanıcı görünümü — sade, kendi bölümleri vurgulu
# ---------------------------------------------------------------------------
if not is_admin:
    if my_depts:
        data_panel(
            "Sizin Bölümleriniz",
            "Sayım girişi yetkiniz olan bölümler ve birlikte yetkili olduğunuz kişiler.",
        )
        own_rows = [
            _simple_row(d)
            for d in sites_depts
            if d["department_id"] in my_dept_ids
        ]
        st.dataframe(
            pd.DataFrame(own_rows),
            use_container_width=True,
            hide_index=True,
        )

        st.markdown('<div class="section-gap"></div>', unsafe_allow_html=True)

    other_rows = [
        _simple_row(d)
        for d in sites_depts
        if d["department_id"] not in my_dept_ids
    ]

    if other_rows:
        data_panel(
            "Diğer Bölümler",
            "Tüm bölümlerin sorumluları ve bu haftaki sayım durumu — "
            "başka bir bölümden bilgi almak gerekirse buradaki sorumluya "
            "ulaşabilirsiniz.",
        )
        st.dataframe(
            pd.DataFrame(other_rows),
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info(
            "Tüm aktif bölümlere yetkiniz var; gösterilecek başka bölüm yok."
        )

    timer.finish()
    st.stop()


# ---------------------------------------------------------------------------
# Admin görünümü — eski detaylı tablo + filtre
# ---------------------------------------------------------------------------
total_depts = len(sites_depts)
submitted_count = sum(1 for d in sites_depts if d["department_id"] in sub_by_dept)
missing_count = total_depts - submitted_count
unassigned_count = sum(1 for d in sites_depts if not dept_users.get(d["department_id"]))


def _assignment_status(users: list[dict]) -> str:
    active = sum(1 for u in users if u["is_active"])
    if active == 0:
        return "Yetkilisi Yok"
    if active == 1:
        return "Tek Yetkili"
    return "Mükerrer Yetki"


admin_rows: list[dict[str, object]] = []
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

    admin_rows.append({
        "Üretim Yeri": dept["site_name"],
        "Bölüm": dept["department_name"],
        "Yetkili Kullanıcı(lar)": _format_users(users),
        "Aktif Yetkili Sayısı": sum(1 for u in users if u["is_active"]),
        "Yetki Durumu": _assignment_status(users),
        "Sayım Durumu": count_status,
        "Giren Kullanıcı": entered_by,
        "Gönderim Zamanı": submitted_at,
        "Geç Giriş": late_flag,
        "Tonaj (t)": actual_tonnage,
    })

df = pd.DataFrame(admin_rows)

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

data_panel(
    "Yetki ve Sayım Durumu",
    f"{total_depts} bölüm · {submitted_count} girdi · {missing_count} eksik · {unassigned_count} atanmamış",
)
st.dataframe(
    filtered,
    use_container_width=True,
    hide_index=True,
    column_config={
        "Tonaj (t)": st.column_config.NumberColumn("Tonaj (t)", format="%.2f"),
    },
)
table_note(
    "Bu tablo, her bölüm için kimin yetkili olduğunu ve seçilen haftada sayımın girilip girilmediğini gösterir."
)
timer.finish()
