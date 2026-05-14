"""
Analiz sayfası — kapsamlı görünüm.

Bölümler:
  1. KPI kartları (seçili hafta)
  2. Genel tablo (her zaman açık)
  3. Üretim yeri kırılımı (expander)
  4. Renk kırılımı (expander)
  5. Eksik bölümler + ilgili kullanıcılar (expander)
  6. Trend grafikleri (boş/dolu/kanban + tonaj actual vs target)
  7. Üretim yeri trend sapma (expander)

Tonaj sapma kuralı: actual > target → KIRMIZI (fazla üretim sinyali).
Az üretim sorun değil, sadece görsel olarak farkını göster.
"""

from __future__ import annotations

import altair as alt
import pandas as pd
import streamlit as st
from sqlalchemy import select

from db.connection import get_session
from db.models import Department, ProductionSite, User, UserDepartment
from utils.cached_queries import (
    get_active_department_count,
    get_analysis_rows,
    get_available_weeks,
)
from utils.auth import require_admin, restore_session_from_query
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
from utils.week import current_week_iso, format_week_human, week_iso_from_date


def _fmt_tr(n: float | int) -> str:
    """Format an integer/float with Turkish thousands separator (.) — no
    decimal places for whole numbers. ``1234567`` → ``"1.234.567"``."""
    try:
        return f"{int(round(float(n))):,}".replace(",", ".")
    except (TypeError, ValueError):
        return str(n)


def _fmt_tr_decimal(n: float, digits: int = 1) -> str:
    """TR formatlı ondalıklı sayı — binlik ayraç '.', ondalık ',' ile.

    Örnek: ``1234.5`` → ``"1.234,5"``.
    """
    try:
        v = float(n)
    except (TypeError, ValueError):
        return str(n)
    # f-string'de ondalık ayraç '.', binlik ',' geliyor → swap ile çeviriyoruz.
    formatted = f"{v:,.{digits}f}"
    return formatted.replace(",", "X").replace(".", ",").replace("X", ".")


inject_css()
restore_session_from_query()
timer = page_timer("analiz")

with get_session() as _s:
    me = require_admin(_s)
render_sidebar_user(me.full_name, me.role)

page_header(
    title="Analiz",
    subtitle="Konteyner ve tonaj trendleri, üretim yeri ve renk kırılımları",
    )


# ---------------------------------------------------------------------------
# Hafta + zaman aralığı seçici
# ---------------------------------------------------------------------------
default_week = current_week_iso()
all_weeks = get_available_weeks(default_week)

filter_bar("Analiz filtreleri", "Hafta ve trend aralığını seçerek özetleri güncelleyin.")
ctop1, ctop2 = st.columns([2, 1])
selected_week = ctop1.selectbox(
    "Hafta",
    all_weeks,
    index=0,
    format_func=lambda w: f"{w} — {format_week_human(w)}",
)
range_n = ctop2.selectbox("Trend aralığı (hafta)", [4, 8, 12, 26], index=0)

# Trend için: seçili haftadan geriye N hafta
def weeks_back_from(anchor: str, n: int) -> list[str]:
    """Anchor (dahil) ve geriye n-1 hafta — kronolojik sırayla."""
    from datetime import timedelta
    from utils.week import week_iso_to_dates
    monday, _ = week_iso_to_dates(anchor)
    weeks = []
    for i in range(n):
        d = monday - pd.Timedelta(weeks=i)
        weeks.append(week_iso_from_date(d))
    weeks.reverse()
    return weeks

trend_weeks = weeks_back_from(selected_week, range_n)


# ---------------------------------------------------------------------------
# Veriyi cache'li oku
# ---------------------------------------------------------------------------
rows = get_analysis_rows(tuple(trend_weeks))

if not rows:
    st.markdown(
        empty_state(
            "Analiz için veri yok",
            "Seçili aralıkta henüz sayım kaydı bulunmuyor. Sayım kayıtları oluştuğunda analiz ekranı dolacaktır.",
            badge="Veri bekleniyor",
            tone="info",
        ),
        unsafe_allow_html=True,
    )
    timer.finish()
    st.stop()

df = pd.DataFrame(rows)
df["actual_tonnage"] = pd.to_numeric(df["actual_tonnage"], errors="coerce")
df["weekly_tonnage_target"] = pd.to_numeric(df["weekly_tonnage_target"], errors="coerce")

# Sadece seçili hafta için filtre (KPI ve özet tabloları için)
df_week = df[df["week_iso"] == selected_week].copy()


# ---------------------------------------------------------------------------
# Section 1 — KPI kartları (seçili hafta)
# ---------------------------------------------------------------------------
total_empty = int(df_week["empty_count"].sum())
total_full = int(df_week["full_count"].sum())
total_kanban = int(df_week["kanban_count"].sum())
total_scrap = int(df_week["scrap_count"].sum()) if "scrap_count" in df_week.columns else 0

# Tonaj — submission başına bir kez (renkler aynı tonajı tekrar etmesin)
sub_unique = df_week.drop_duplicates(subset=["submission_id"])
total_actual = float(sub_unique["actual_tonnage"].sum())
total_target = float(sub_unique["weekly_tonnage_target"].dropna().sum())
excess = max(0.0, total_actual - total_target)

submitted_dept_count = sub_unique["department_id"].nunique()

total_dept_count = get_active_department_count()
missing_count = total_dept_count - submitted_dept_count

st.markdown(f"#### Seçili Hafta: {format_week_human(selected_week)}")
total_containers = total_empty + total_full + total_scrap  # kanban dolu'nun alt kümesi, ayrı sayma
completion_pct = (submitted_dept_count / total_dept_count * 100) if total_dept_count else 0
kanban_rate = (total_kanban / total_full * 100) if total_full else 0

# Ortalama dolu konteyner ağırlığı (kg) — toplam tonaj × 1000 / toplam dolu
# Bölüm-bazlı hesabı ileride tabloda gösteriyoruz; burada genel ortalama.
avg_kg_per_full = (total_actual * 1000 / total_full) if total_full else 0

primary_cards = [
    kpi_card("Toplam Konteyner", _fmt_tr(total_containers), sub="Boş + Dolu + Hurdaya Ayrılacak"),
    kpi_card("Dolu Konteyner", _fmt_tr(total_full), sub="Ürün / yarı mamul taşıyan"),
    kpi_card("Boş Konteyner", _fmt_tr(total_empty), sub="Kullanılabilir kasa"),
    kpi_card("Kanban", _fmt_tr(total_kanban), sub="Dolu konteynerin alt kümesi"),
    kpi_card("Hurdaya Ayrılacak", _fmt_tr(total_scrap)),
]
render_kpis(primary_cards)

secondary_cards = [
    kpi_card(
        "Sayım Kapsamı",
        f"{submitted_dept_count} / {total_dept_count}",
        sub=f"%{completion_pct:.0f} tamamlandı",
        delta=f"{missing_count} eksik" if missing_count else "Eksik yok",
        delta_kind="neutral" if missing_count else "neg",
    ),
    kpi_card("Kanban Oranı", f"%{_fmt_tr_decimal(kanban_rate)}", sub="Kanban / dolu"),
    kpi_card(
        "Ort. Dolu Konteyner Ağırlığı",
        f"{_fmt_tr(avg_kg_per_full)} kg",
        sub="Toplam tonaj / dolu konteyner",
    ),
]
st.markdown("<div style='height:0.75rem'></div>", unsafe_allow_html=True)
render_kpis(secondary_cards)
st.markdown("<br>", unsafe_allow_html=True)

site_signal = (
    df_week.groupby("site")
    .agg(
        Dolu=("full_count", "sum"),
        Boş=("empty_count", "sum"),
        Kanban=("kanban_count", "sum"),
        **({"Hurdaya_Ayrılacak": ("scrap_count", "sum")} if "scrap_count" in df_week.columns else {}),
        Giren_Bölüm=("department_id", "nunique"),
    )
    .reset_index()
)
if not site_signal.empty:
    # Toplam (B+D+H) — hurda da dahil
    if "Hurdaya_Ayrılacak" in site_signal.columns:
        site_signal["Toplam (B+D+H)"] = (
            site_signal["Boş"] + site_signal["Dolu"] + site_signal["Hurdaya_Ayrılacak"]
        )
    else:
        site_signal["Toplam (B+D+H)"] = site_signal["Boş"] + site_signal["Dolu"]
    site_signal["Kanban Oranı (%)"] = (
        site_signal["Kanban"] / site_signal["Dolu"].replace(0, pd.NA) * 100
    ).fillna(0)
    data_panel("Öne Çıkan Üretim Yerleri", "Dolu konteyner ve toplam yoğunluğa göre ilk üretim yerleri.")
    cols = ["Üretim Yeri", "Toplam (B+D+H)", "Dolu", "Boş", "Kanban"]
    if "Hurdaya_Ayrılacak" in site_signal.columns:
        cols.append("Hurdaya Ayrılacak")
    cols.extend(["Kanban Oranı (%)", "Giren Bölüm"])
    site_num_cols = ["Toplam (B+D+H)", "Dolu", "Boş", "Kanban", "Giren Bölüm"]
    if "Hurdaya_Ayrılacak" in site_signal.columns:
        site_num_cols.append("Hurdaya Ayrılacak")
    st.dataframe(
        site_signal.sort_values(["Dolu", "Toplam (B+D+H)"], ascending=False)
        .head(8)
        .rename(columns={
            "site": "Üretim Yeri",
            "Giren_Bölüm": "Giren Bölüm",
            "Hurdaya_Ayrılacak": "Hurdaya Ayrılacak",
        })[cols]
        .style.format({
            **{c: _fmt_tr for c in site_num_cols},
            "Kanban Oranı (%)": _fmt_tr_decimal,
        }),
        use_container_width=True,
        hide_index=True,
    )


# ---------------------------------------------------------------------------
# Section 2 — Genel Trend (filtre: üretim yeri + bölüm breakdown)
# ---------------------------------------------------------------------------
st.divider()
st.subheader(f"Genel Trend (son {range_n} hafta)")

trend_c1, trend_c2 = st.columns([2, 1])
with trend_c1:
    sites_options = ["Tümü"] + sorted(df["site"].unique().tolist())
    selected_trend_site = st.selectbox("Üretim Yeri", sites_options, key="trend_site")
with trend_c2:
    breakdown = st.toggle(
        "Bölüm bazında ayır",
        value=False,
        disabled=(selected_trend_site == "Tümü"),
        help="Bir üretim yeri seçince bölümleri ayrı çizgilerde göster",
    )

# Filtre uygula
if selected_trend_site == "Tümü":
    trend_df = df
else:
    trend_df = df[df["site"] == selected_trend_site]

if breakdown and selected_trend_site != "Tümü":
    # Bölüm bazında ayır — kullanıcı tek metrik seçsin (yoksa çok karışır)
    metric = st.radio(
        "Metrik",
        ["Dolu", "Boş", "Kanban", "Gerçekleşen Tonaj"],
        horizontal=True,
        key="trend_metric",
    )
    metric_col = {
        "Boş": "empty_count",
        "Dolu": "full_count",
        "Kanban": "kanban_count",
    }.get(metric)

    if metric == "Gerçekleşen Tonaj":
        sub_uniq_filtered = trend_df.drop_duplicates(subset=["submission_id"])
        per_dept = (
            sub_uniq_filtered.groupby(["week_iso", "department"])["actual_tonnage"]
            .sum().reset_index()
        )
        per_dept = per_dept.rename(columns={"actual_tonnage": "Değer"})
    else:
        per_dept = (
            trend_df.groupby(["week_iso", "department"])[metric_col]
            .sum().reset_index().rename(columns={metric_col: "Değer"})
        )

    if per_dept.empty or per_dept["week_iso"].nunique() < 2:
        st.markdown(
            empty_state(
                "Trend için yeterli veri yok",
                "Bölüm bazlı trend analizi için seçili üretim yerinde en az 2 hafta veri gerekir.",
                badge="En az 2 hafta",
                tone="info",
            ),
            unsafe_allow_html=True,
        )
    else:
        chart = alt.Chart(per_dept).mark_line(point=True).encode(
            x=alt.X("week_iso:N", title="Hafta"),
            y=alt.Y("Değer:Q", title=metric),
            color=alt.Color("department:N", title="Bölüm"),
            tooltip=["week_iso", "department", "Değer"],
        ).properties(height=400)
        st.altair_chart(chart, use_container_width=True)
else:
    # Aggregate görünüm — Boş/Dolu/Kanban 3 çizgi
    weekly = (
        trend_df.groupby("week_iso")
        .agg(
            Boş=("empty_count", "sum"),
            Dolu=("full_count", "sum"),
            Kanban=("kanban_count", "sum"),
        ).reset_index()
    )
    sub_uniq_filtered = trend_df.drop_duplicates(subset=["submission_id"])
    weekly_tonnage = (
        sub_uniq_filtered.groupby("week_iso")
        .agg(
            Gerçekleşen=("actual_tonnage", "sum"),
            Hedef=("weekly_tonnage_target", "sum"),
        ).reset_index()
    )

    if len(weekly) < 2:
        st.markdown(
            empty_state(
                "Trend için yeterli veri yok",
                f"Trend analizi için en az 2 hafta veri gerekir. Şu an {len(weekly)} hafta var.",
                badge="En az 2 hafta",
                tone="info",
            ),
            unsafe_allow_html=True,
        )
    else:
        cl, cr = st.columns(2)
        with cl:
            st.markdown("**Konteyner sayıları (haftalık toplam)**")
            st.line_chart(weekly.set_index("week_iso")[["Boş", "Dolu", "Kanban"]])
        with cr:
            st.markdown("**Tonaj: Gerçekleşen vs Hedef**")
            st.line_chart(weekly_tonnage.set_index("week_iso")[["Gerçekleşen", "Hedef"]])

        weekly_tonnage["Fazla (t)"] = (
            weekly_tonnage["Gerçekleşen"] - weekly_tonnage["Hedef"]
        ).clip(lower=0)
        st.markdown("**Hedefi aşan tonaj (haftalık)**")
        st.bar_chart(weekly_tonnage.set_index("week_iso")[["Fazla (t)"]])


# ---------------------------------------------------------------------------
# Section 3 — Genel Tablo
# ---------------------------------------------------------------------------
st.divider()
st.subheader("Bölüm Özeti (seçili hafta)")
data_panel("Bölüm Özeti", "Seçili haftada bölüm bazında konteyner, kanban ve tonaj sapması.")

_dept_agg_kwargs = dict(
    boş=("empty_count", "sum"),
    dolu=("full_count", "sum"),
    kanban=("kanban_count", "sum"),
)
if "scrap_count" in df_week.columns:
    _dept_agg_kwargs["hurda"] = ("scrap_count", "sum")

dept_summary = (
    df_week.groupby(["site", "department", "department_id", "weekly_tonnage_target"], dropna=False)
    .agg(**_dept_agg_kwargs)
    .reset_index()
)
# Tonajı submission'dan al
dept_tonnage = sub_unique[["department_id", "actual_tonnage"]].set_index("department_id")
dept_summary["actual"] = dept_summary["department_id"].map(
    dept_tonnage["actual_tonnage"]
).astype(float)
dept_summary["target"] = dept_summary["weekly_tonnage_target"]
dept_summary["sapma"] = dept_summary["actual"] - dept_summary["target"]


# Bölüm Özeti — kırmızı satır boyaması KALDIRILDI (talep). Sapma sütunu
# zaten +/- işaretiyle aşımı gösteriyor; satır boyama görsel kirlilik.

# Toplam (B+D+H) kolonu — kullanıcı her sayfada görmek istiyor
dept_summary["toplam_bdh"] = (
    dept_summary["boş"] + dept_summary["dolu"]
    + dept_summary.get("hurda", 0)
)

# Bölüm bazında ortalama dolu konteyner ağırlığı (kg)
# = tonaj (ton) × 1000 / dolu sayısı. Dolu yoksa NaN bırak (gösterimde "—").
dept_summary["ort_kg"] = (
    (dept_summary["actual"] * 1000 / dept_summary["dolu"].replace(0, pd.NA))
).fillna(0)
# 0 dolu olan bölümlere "—" göstermek için NaN'a çevir
dept_summary.loc[dept_summary["dolu"] == 0, "ort_kg"] = pd.NA

_summary_cols = ["site", "department", "boş", "dolu", "kanban"]
if "hurda" in dept_summary.columns:
    _summary_cols.append("hurda")
_summary_cols.extend(["toplam_bdh", "actual", "ort_kg", "target", "sapma"])

_num_int_cols = ["Boş", "Dolu", "Kanban"]
if "hurda" in dept_summary.columns:
    _num_int_cols.append("Hurdaya Ayrılacak")
_num_int_cols.append("Toplam (B+D+H)")
_num_int_cols.extend(["Gerçekleşen (t)", "Ort. Ağırlık (kg)", "Hedef (t)"])

def _fmt_sapma_tr(n):
    try:
        v = int(round(float(n)))
    except (TypeError, ValueError):
        return "—"
    sign = "+" if v > 0 else ("" if v == 0 else "-")
    return f"{sign}{_fmt_tr(abs(v))}"

st.dataframe(
    dept_summary[_summary_cols]
    .rename(columns={
        "site": "Üretim Yeri", "department": "Bölüm",
        "boş": "Boş", "dolu": "Dolu", "kanban": "Kanban",
        "hurda": "Hurdaya Ayrılacak",
        "toplam_bdh": "Toplam (B+D+H)",
        "actual": "Gerçekleşen (t)",
        "ort_kg": "Ort. Ağırlık (kg)",
        "target": "Hedef (t)", "sapma": "Sapma (t)",
    })
    .style.format(
        {**{c: _fmt_tr for c in _num_int_cols}, "Sapma (t)": _fmt_sapma_tr},
        na_rep="—",
    ),
    use_container_width=True,
    hide_index=True,
)


# ---------------------------------------------------------------------------
# Section 3 — Üretim yeri kırılımı
# ---------------------------------------------------------------------------
with st.expander("Üretim Yeri Kırılımı", expanded=False):
    _site_agg = dict(
        boş=("empty_count", "sum"),
        dolu=("full_count", "sum"),
        kanban=("kanban_count", "sum"),
    )
    if "scrap_count" in df_week.columns:
        _site_agg["hurda"] = ("scrap_count", "sum")
    site_summary = df_week.groupby("site").agg(**_site_agg).reset_index()
    site_tonnage = (
        sub_unique.groupby("site")
        .agg(
            actual=("actual_tonnage", "sum"),
            target=("weekly_tonnage_target", "sum"),
        )
        .reset_index()
    )
    site_summary = site_summary.merge(site_tonnage, on="site", how="left")
    site_summary["sapma"] = site_summary["actual"] - site_summary["target"]
    site_summary["bölüm_sayısı"] = (
        df_week.groupby("site")["department_id"].nunique().values
    )
    site_summary["toplam_bdh"] = (
        site_summary["boş"] + site_summary["dolu"]
        + site_summary.get("hurda", 0)
    )
    # Üretim yeri bazında ortalama dolu konteyner ağırlığı (kg)
    site_summary["ort_kg"] = (
        site_summary["actual"] * 1000 / site_summary["dolu"].replace(0, pd.NA)
    )
    site_summary.loc[site_summary["dolu"] == 0, "ort_kg"] = pd.NA
    rename_map = {
        "site": "Üretim Yeri",
        "boş": "Boş", "dolu": "Dolu", "kanban": "Kanban",
        "hurda": "Hurdaya Ayrılacak",
        "toplam_bdh": "Toplam (B+D+H)",
        "actual": "Gerçekleşen (t)",
        "ort_kg": "Ort. Ağırlık (kg)",
        "target": "Hedef (t)", "sapma": "Sapma (t)",
        "bölüm_sayısı": "Giren Bölüm",
    }
    site_num_cols = ["Boş", "Dolu", "Kanban"]
    if "hurda" in site_summary.columns:
        site_num_cols.append("Hurdaya Ayrılacak")
    site_num_cols.extend([
        "Toplam (B+D+H)", "Gerçekleşen (t)",
        "Ort. Ağırlık (kg)", "Hedef (t)", "Giren Bölüm",
    ])
    st.dataframe(
        site_summary.rename(columns=rename_map)
        .style.format(
            {**{c: _fmt_tr for c in site_num_cols}, "Sapma (t)": _fmt_sapma_tr},
            na_rep="—",
        ),
        use_container_width=True, hide_index=True,
    )


# ---------------------------------------------------------------------------
# Section 4 — Renk kırılımı
# ---------------------------------------------------------------------------
with st.expander("Renk Kırılımı", expanded=False):
    _color_agg = dict(
        boş=("empty_count", "sum"),
        dolu=("full_count", "sum"),
        kanban=("kanban_count", "sum"),
    )
    if "scrap_count" in df_week.columns:
        _color_agg["hurda"] = ("scrap_count", "sum")
    # Renk sırasını kayıt sırasında verilen sort_order'a göre yap (alfabetik değil).
    if "color_sort_order" in df_week.columns:
        color_summary = (
            df_week.groupby(["color", "color_sort_order"])
            .agg(**_color_agg)
            .reset_index()
            .sort_values("color_sort_order")
            .drop(columns=["color_sort_order"])
        )
    else:
        color_summary = df_week.groupby("color").agg(**_color_agg).reset_index()
    color_summary["toplam"] = (
        color_summary["boş"] + color_summary["dolu"]
        + color_summary.get("hurda", 0)
    )
    rename_map = {
        "color": "Renk", "boş": "Boş", "dolu": "Dolu",
        "kanban": "Kanban", "hurda": "Hurdaya Ayrılacak",
        "toplam": "Toplam (B+D+H)",
    }
    num_cols = ["Boş", "Dolu", "Kanban"]
    if "hurda" in color_summary.columns:
        num_cols.append("Hurdaya Ayrılacak")
    num_cols.append("Toplam (B+D+H)")
    st.dataframe(
        color_summary.rename(columns=rename_map)
        .style.format({c: _fmt_tr for c in num_cols}),
        use_container_width=True, hide_index=True,
    )

    # Renk dağılım grafiği — gruplu bar (Boş + Dolu yan yana) + Kanban Dolu içinde overlay
    long_rows = []
    for _, r in color_summary.iterrows():
        long_rows.append({"Renk": r["color"], "Tip": "Boş", "Sayı": int(r["boş"]), "Kanban": 0})
        long_rows.append({"Renk": r["color"], "Tip": "Dolu", "Sayı": int(r["dolu"]), "Kanban": int(r["kanban"])})
    long_df = pd.DataFrame(long_rows)

    required_chart_columns = {"Renk", "Tip", "Sayı", "Kanban"}
    if long_df.empty or not required_chart_columns.issubset(long_df.columns):
        st.markdown(
            empty_state(
                "Renk kırılımı için veri yok",
                "Seçili hafta için renk bazlı grafik oluşturacak yeterli veri bulunmuyor.",
                badge="Grafik bekliyor",
                tone="info",
            ),
            unsafe_allow_html=True,
        )
    else:
        base = alt.Chart(long_df).encode(
            x=alt.X("Renk:N", title="Renk"),
            xOffset=alt.XOffset("Tip:N"),
        )
        bars = base.mark_bar().encode(
            y=alt.Y("Sayı:Q", title="Konteyner sayısı"),
            color=alt.Color(
                "Tip:N",
                scale=alt.Scale(domain=["Boş", "Dolu"], range=["#9aa5b1", "#3aa56b"]),
                legend=alt.Legend(title="Tip"),
            ),
            tooltip=["Renk", "Tip", "Sayı", "Kanban"],
        )
        kanban_overlay = (
            alt.Chart(long_df[long_df["Tip"] == "Dolu"])
            .mark_bar(color="#1a5934")
            .encode(
                x=alt.X("Renk:N"),
                xOffset=alt.XOffset("Tip:N"),
                y=alt.Y("Kanban:Q"),
                tooltip=["Renk", alt.Tooltip("Kanban:Q", title="Kanban")],
            )
        )
        chart = (bars + kanban_overlay).properties(height=350)
        st.altair_chart(chart, use_container_width=True)
        table_note("Dolu içindeki koyu yeşil bölge = Kanban (Dolu'nun alt kümesi).")


# ---------------------------------------------------------------------------
# Section 5 — Eksik bölümler + kullanıcılar
# ---------------------------------------------------------------------------
with st.expander(f"Eksik Bölümler ({missing_count})", expanded=False):
    submitted_dept_ids = set(sub_unique["department_id"].tolist())

    with get_session() as s:
        missing_depts = list(s.execute(
            select(Department, ProductionSite)
            .join(ProductionSite, Department.production_site_id == ProductionSite.id)
            .where(Department.is_active.is_(True))
            .where(~Department.id.in_(submitted_dept_ids) if submitted_dept_ids else Department.id == Department.id)
            .order_by(ProductionSite.name, Department.name)
        ).all())

        # Bölüm başına yetkili kullanıcılar
        dept_users: dict[int, list[str]] = {}
        for dept_id, full_name in s.execute(
            select(UserDepartment.department_id, User.full_name)
            .join(User, User.id == UserDepartment.user_id)
            .where(User.is_active.is_(True))
        ).all():
            dept_users.setdefault(dept_id, []).append(full_name)

    if not missing_depts:
        st.success("Bu hafta için tüm bölümler sayım girdi!")
    else:
        miss_rows = []
        for d, site in missing_depts:
            users = dept_users.get(d.id, [])
            miss_rows.append({
                "Üretim Yeri": site.name,
                "Bölüm": d.name,
                "Yetkili Kullanıcı(lar)": ", ".join(users) if users else "— (atanmamış)",
                "Tonaj Hedefi": float(d.weekly_tonnage_target) if d.weekly_tonnage_target else None,
            })
        st.dataframe(
            pd.DataFrame(miss_rows).style.format({"Tonaj Hedefi": "{:.2f}"}, na_rep="—"),
            use_container_width=True, hide_index=True,
        )




# ---------------------------------------------------------------------------
# Section 7 — Üretim yeri trend sapma
# ---------------------------------------------------------------------------
with st.expander("Üretim Yeri Trend Sapma", expanded=False):
    sites = sorted(df["site"].unique())
    selected_site = st.selectbox("Üretim yeri seç", sites)
    site_df = df[df["site"] == selected_site]
    site_sub_unique = site_df.drop_duplicates(subset=["submission_id"])

    _sw_agg = dict(
        Boş=("empty_count", "sum"),
        Dolu=("full_count", "sum"),
        Kanban=("kanban_count", "sum"),
    )
    if "scrap_count" in site_df.columns:
        _sw_agg["Hurdaya_Ayrılacak"] = ("scrap_count", "sum")
    site_weekly = site_df.groupby("week_iso").agg(**_sw_agg).reset_index()
    if "Hurdaya_Ayrılacak" in site_weekly.columns:
        site_weekly = site_weekly.rename(columns={"Hurdaya_Ayrılacak": "Hurdaya Ayrılacak"})
    site_tonnage_weekly = (
        site_sub_unique.groupby("week_iso")
        .agg(
            Gerçekleşen=("actual_tonnage", "sum"),
            Hedef=("weekly_tonnage_target", "sum"),
        )
        .reset_index()
    )
    site_tonnage_weekly["Fazla"] = (
        site_tonnage_weekly["Gerçekleşen"] - site_tonnage_weekly["Hedef"]
    )

    site_weekly["Toplam"] = site_weekly["Boş"] + site_weekly["Dolu"]
    site_weekly["Kanban Oranı (%)"] = (
        site_weekly["Kanban"] / site_weekly["Dolu"].replace(0, pd.NA) * 100
    ).fillna(0)

    cl, cr = st.columns(2)
    with cl:
        st.markdown(f"**{selected_site} — konteynerler**")
        st.line_chart(site_weekly.set_index("week_iso")[["Boş", "Dolu", "Kanban"]])
    with cr:
        st.markdown(f"**{selected_site} — tonaj**")
        st.line_chart(site_tonnage_weekly.set_index("week_iso")[["Gerçekleşen", "Hedef"]])

    st.markdown("**Kanban oranı ve toplam konteyner trendi**")
    c_ratio, c_total = st.columns(2)
    c_ratio.line_chart(site_weekly.set_index("week_iso")[["Kanban Oranı (%)"]])
    c_total.line_chart(site_weekly.set_index("week_iso")[["Toplam"]])

    site_change = site_weekly.merge(
        site_tonnage_weekly[["week_iso", "Gerçekleşen", "Hedef", "Fazla"]],
        on="week_iso",
        how="left",
    ).sort_values("week_iso")
    diff_cols = ["Boş", "Dolu", "Kanban", "Toplam", "Gerçekleşen", "Hedef", "Fazla"]
    if "Hurdaya Ayrılacak" in site_change.columns:
        diff_cols.append("Hurdaya Ayrılacak")
    for col in diff_cols:
        site_change[f"{col} Δ"] = site_change[col].diff()

    st.markdown("**Haftalık değişim tablosu**")
    table_cols = [
        "week_iso", "Boş", "Boş Δ", "Dolu", "Dolu Δ",
        "Kanban", "Kanban Δ", "Kanban Oranı (%)",
    ]
    if "Hurdaya Ayrılacak" in site_change.columns:
        table_cols.extend(["Hurdaya Ayrılacak", "Hurdaya Ayrılacak Δ"])
    table_cols.extend(["Toplam", "Toplam Δ", "Gerçekleşen", "Hedef", "Fazla"])
    st.dataframe(
        site_change[table_cols].rename(columns={
            "week_iso": "Hafta",
            "Boş Δ": "Boş Değişim",
            "Dolu Δ": "Dolu Değişim",
            "Kanban Δ": "Kanban Değişim",
            "Toplam Δ": "Toplam Değişim",
            "Gerçekleşen": "Gerçekleşen Tonaj",
        }).style.format({
            "Kanban Oranı (%)": _fmt_tr_decimal,
            "Gerçekleşen Tonaj": _fmt_tr,
            "Hedef": _fmt_tr,
            "Fazla": _fmt_tr,
        }, na_rep="-"),
        use_container_width=True,
        hide_index=True,
    )

    # Anormal artış uyarısı: son haftanın "Fazla" değeri,
    # önceki haftaların ortalamasının %20+ üstünde mi?
    if len(site_tonnage_weekly) >= 4:
        last = site_tonnage_weekly.iloc[-1]["Fazla"]
        prev_mean = site_tonnage_weekly.iloc[:-1]["Fazla"].mean()
        if pd.notna(last) and pd.notna(prev_mean) and prev_mean > 0:
            jump_pct = (last - prev_mean) / prev_mean * 100
            if last > 0 and jump_pct > 20:
                st.error(
                    f"Son haftada **{selected_site}**'de fazla tonaj "
                    f"%{jump_pct:.0f} arttı "
                    f"(geçmiş ortalama: {prev_mean:.1f} t, son: {last:.1f} t)."
                )
            elif last <= 0:
                st.success(f"Son hafta hedef altında — sorun yok.")
            else:
                st.info(f"Son haftadaki fazla: {last:.1f} t (geçmiş ortalama: {prev_mean:.1f} t).")

timer.finish()
