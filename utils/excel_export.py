"""Excel export helpers for the admin panel.

Per-week workbook (``build_week_excel``) layout:

    1. Renk Kırılımı           — selected week, per (dept × color) detail
    2. Üretim Yeri Kırılımı    — selected week, per-department aggregate
    3. Üretim Yeri Özeti       — selected week, per-site aggregate with %
                                 and ton/dolu KPI
    4. Renk Özeti              — selected week, per-color aggregate
    5. ÖZET                    — ALL weeks, charts only
    6. Üretim Yeri Karşılaştırma — ALL weeks, site-summary tables placed
                                 side by side for visual comparison

Long-format export (``build_all_weeks_excel``) is a separate workbook
that lists every (week × site × dept × color) row in one sheet for
PivotTable consumption — unchanged by this refactor.
"""

from __future__ import annotations

from datetime import datetime, date, timedelta
from io import BytesIO
from typing import Any

from openpyxl import Workbook
from openpyxl.chart import BarChart, LineChart, Reference
from openpyxl.chart.shapes import GraphicalProperties
from openpyxl.drawing.line import LineProperties
from openpyxl.styles import Alignment, Font, PatternFill, Border, Side
from openpyxl.utils import get_column_letter

from utils.week import now_tr


_STATUS_LABEL = {
    "submitted": "Zamanında",
    "late_submitted": "Geç giriş",
    "draft": "Taslak",
}

_HEADER_FILL = PatternFill("solid", fgColor="1F3A8A")
_HEADER_FONT = Font(bold=True, color="FFFFFF", size=11)
_SUBHEADER_FILL = PatternFill("solid", fgColor="3B5BB1")
_ZEBRA_FILL = PatternFill("solid", fgColor="F1F5F9")
_LATE_FILL = PatternFill("solid", fgColor="FEF3C7")
_TOTAL_FILL = PatternFill("solid", fgColor="E0EAF8")
_TOTAL_FONT = Font(bold=True, color="1F3A8A", size=11)
_THIN = Side(style="thin", color="D8E4F2")
_BORDER = Border(left=_THIN, right=_THIN, top=_THIN, bottom=_THIN)
_CENTER = Alignment(horizontal="center", vertical="center")
_LEFT = Alignment(horizontal="left", vertical="center")
_RIGHT = Alignment(horizontal="right", vertical="center")

# Brand-ish hex codes for color-coded chart series. Anything outside this
# set falls back to a neutral gray so the chart still renders.
_COLOR_HEX = {
    "Mavi": "2563EB",
    "Turuncu": "F97316",
    "Yeşil": "22C55E",
    "Gri": "6B7280",
    "MS Vida": "854D0E",
    "Sarı": "EAB308",
}


# ---------------------------------------------------------------------------
# Small helpers (kept stable across refactor)
# ---------------------------------------------------------------------------

def _fmt_ts(value: Any) -> str:
    if value in (None, ""):
        return ""
    s = str(value)
    if "T" in s:
        try:
            dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
            return dt.strftime("%Y-%m-%d %H:%M")
        except ValueError:
            return s[:16].replace("T", " ")
    return s


def _autofit(ws, headers: list[str]) -> None:
    for col_idx, header in enumerate(headers, start=1):
        max_len = len(str(header))
        for cell in ws[get_column_letter(col_idx)]:
            if cell.value is None:
                continue
            length = len(str(cell.value))
            if length > max_len:
                max_len = length
        ws.column_dimensions[get_column_letter(col_idx)].width = min(max_len + 3, 42)


_TR_MONTHS_SHORT = [
    "Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran",
    "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık",
]


def _week_iso_to_human(week_iso: str) -> tuple[str, str, int]:
    """Return ``(hafta_aralığı, ay, yıl)`` strings for the given ISO week.

    Falls back to the raw code if parsing fails.
    """
    try:
        year_str, week_str = week_iso.split("-W")
        year = int(year_str)
        week = int(week_str)
        monday = date.fromisocalendar(year, week, 1)
        sunday = monday + timedelta(days=6)
        if monday.year == sunday.year and monday.month == sunday.month:
            label = f"{monday.day:02d}-{sunday.day:02d} {_TR_MONTHS_SHORT[monday.month - 1]} {monday.year}"
        elif monday.year == sunday.year:
            label = (
                f"{monday.day:02d} {_TR_MONTHS_SHORT[monday.month - 1]} - "
                f"{sunday.day:02d} {_TR_MONTHS_SHORT[sunday.month - 1]} {monday.year}"
            )
        else:
            label = (
                f"{monday.day:02d} {_TR_MONTHS_SHORT[monday.month - 1]} {monday.year} - "
                f"{sunday.day:02d} {_TR_MONTHS_SHORT[sunday.month - 1]} {sunday.year}"
            )
        return label, _TR_MONTHS_SHORT[monday.month - 1], monday.year
    except Exception:
        return week_iso, "", 0


def _style_header_row(ws, header_count: int) -> None:
    """Apply standard header styling to the first row of `ws`."""
    for col_idx in range(1, header_count + 1):
        cell = ws.cell(row=1, column=col_idx)
        cell.fill = _HEADER_FILL
        cell.font = _HEADER_FONT
        cell.alignment = _CENTER
        cell.border = _BORDER
    ws.row_dimensions[1].height = 26
    ws.freeze_panes = "A2"


def _set_bar_series_color(series, hex_code: str) -> None:
    """Color a bar/column series solidly. openpyxl needs this dance."""
    series.graphicalProperties = GraphicalProperties(solidFill=hex_code)


def _set_line_series_color(series, hex_code: str) -> None:
    """Color a line series. Solid fill applies to markers; line color
    needs its own LineProperties."""
    gp = GraphicalProperties()
    gp.line = LineProperties(solidFill=hex_code)
    series.graphicalProperties = gp


# ---------------------------------------------------------------------------
# Per-week sheet builders
# ---------------------------------------------------------------------------

def _build_renk_kirilim_sheet(wb: Workbook, rows: list[dict[str, Any]]) -> None:
    """Sheet 1: detail per (department × color) for the selected week."""
    ws = wb.active
    ws.title = "Renk Kırılımı"

    headers = [
        "Üretim Yeri", "Bölüm", "Renk",
        "Boş", "Dolu", "Dolu İçindeki Kanban", "Hurdaya Ayrılacak",
        "Toplam (B+D+H)", "Durum",
        "Giren Kullanıcı", "Sayım Tarihi", "Sayım Saati", "Gönderim Zamanı",
    ]
    ws.append(headers)
    _style_header_row(ws, len(headers))

    totals = {"empty": 0, "full": 0, "kanban": 0, "scrap": 0, "bdh": 0}

    for idx, row in enumerate(rows, start=2):
        is_late = row.get("Durum") == "late_submitted"
        zebra = (idx % 2 == 0) and not is_late
        fill = _LATE_FILL if is_late else (_ZEBRA_FILL if zebra else None)

        bos_v = int(row.get("Boş") or 0)
        dolu_v = int(row.get("Dolu") or 0)
        kanban_v = int(row.get("Kanban") or 0)
        hurda_v = int(row.get("Hurda") or 0)
        bdh_v = bos_v + dolu_v + hurda_v

        values = [
            row.get("Üretim Yeri", ""), row.get("Bölüm", ""), row.get("Renk", ""),
            row.get("Boş"), row.get("Dolu"), row.get("Kanban"), row.get("Hurda"),
            bdh_v,
            _STATUS_LABEL.get(row.get("Durum"), row.get("Durum", "")),
            row.get("Giren Kullanıcı", ""),
            row.get("Sayım Tarihi", ""), row.get("Sayım Saati", ""),
            _fmt_ts(row.get("Gönderim Zamanı")),
        ]
        ws.append(values)
        totals["empty"] += bos_v
        totals["full"] += dolu_v
        totals["kanban"] += kanban_v
        totals["scrap"] += hurda_v
        totals["bdh"] += bdh_v

        for col_idx in range(1, len(values) + 1):
            cell = ws.cell(row=idx, column=col_idx)
            cell.border = _BORDER
            if fill:
                cell.fill = fill
            if col_idx in (4, 5, 6, 7, 8):
                cell.alignment = _RIGHT
                cell.number_format = "#,##0"
            elif col_idx == 9:
                cell.alignment = _CENTER
                if is_late:
                    cell.font = Font(bold=True, color="92400E")
            else:
                cell.alignment = _LEFT

    if rows:
        total_row_idx = ws.max_row + 1
        ws.append([
            "TOPLAM", "", "",
            totals["empty"], totals["full"], totals["kanban"], totals["scrap"],
            totals["bdh"],
            "", "", "", "", "",
        ])
        for col_idx in range(1, len(headers) + 1):
            cell = ws.cell(row=total_row_idx, column=col_idx)
            cell.fill = _TOTAL_FILL
            cell.font = _TOTAL_FONT
            cell.border = _BORDER
            if col_idx in (4, 5, 6, 7, 8):
                cell.alignment = _RIGHT
                cell.number_format = "#,##0"
            elif col_idx == 1:
                cell.alignment = _RIGHT
            else:
                cell.alignment = _LEFT

    _autofit(ws, headers)


def _build_uretim_yeri_kirilim_sheet(
    wb: Workbook, rows: list[dict[str, Any]]
) -> dict[tuple[str, str], dict[str, Any]]:
    """Sheet 2: per-(site, department) aggregate.

    Returns the aggregate dict so the per-site sheet can reuse it
    without re-scanning the rows.
    """
    ws = wb.create_sheet("Üretim Yeri Kırılımı")

    headers = [
        "Üretim Yeri", "Bölüm",
        "Boş", "Dolu", "Dolu İçindeki Kanban", "Hurdaya ayrılacak",
        "Toplam Konteyner", "Toplam Tonaj",
        "Durum", "Giren Kullanıcı", "Sayım Gönderim Zamanı",
    ]
    ws.append(headers)
    _style_header_row(ws, len(headers))

    aggregates: dict[tuple[str, str], dict[str, Any]] = {}
    for row in rows:
        key = (row.get("Üretim Yeri", ""), row.get("Bölüm", ""))
        agg = aggregates.setdefault(key, {
            "empty": 0, "full": 0, "kanban": 0, "scrap": 0,
            "tonnage": row.get("Gerçekleşen Tonaj"),
            "status": row.get("Durum"),
            "user": row.get("Giren Kullanıcı", ""),
            "submitted_at": row.get("Gönderim Zamanı"),
        })
        agg["empty"] += int(row.get("Boş") or 0)
        agg["full"] += int(row.get("Dolu") or 0)
        agg["kanban"] += int(row.get("Kanban") or 0)
        agg["scrap"] += int(row.get("Hurda") or 0)

    totals = {"empty": 0, "full": 0, "kanban": 0, "scrap": 0, "bdh": 0, "tonnage": 0.0}

    for idx, ((site, dept), agg) in enumerate(sorted(aggregates.items()), start=2):
        is_late = agg["status"] == "late_submitted"
        fill = _LATE_FILL if is_late else (_ZEBRA_FILL if idx % 2 == 0 else None)
        bdh = int(agg["empty"] or 0) + int(agg["full"] or 0) + int(agg["scrap"] or 0)
        ton = agg["tonnage"]
        values = [
            site, dept,
            agg["empty"], agg["full"], agg["kanban"], agg["scrap"],
            bdh, ton,
            _STATUS_LABEL.get(agg["status"], agg["status"] or ""),
            agg["user"],
            _fmt_ts(agg["submitted_at"]),
        ]
        ws.append(values)
        totals["empty"] += int(agg["empty"] or 0)
        totals["full"] += int(agg["full"] or 0)
        totals["kanban"] += int(agg["kanban"] or 0)
        totals["scrap"] += int(agg["scrap"] or 0)
        totals["bdh"] += bdh
        if ton is not None:
            try:
                totals["tonnage"] += float(ton)
            except (TypeError, ValueError):
                pass

        for col_idx in range(1, len(values) + 1):
            cell = ws.cell(row=idx, column=col_idx)
            cell.border = _BORDER
            if fill:
                cell.fill = fill
            if col_idx in (3, 4, 5, 6, 7):
                cell.alignment = _RIGHT
                cell.number_format = "#,##0"
            elif col_idx == 8:
                cell.alignment = _RIGHT
                cell.number_format = "#,##0"
            elif col_idx == 9:
                cell.alignment = _CENTER
                if is_late:
                    cell.font = Font(bold=True, color="92400E")
            else:
                cell.alignment = _LEFT

    if aggregates:
        total_row_idx = ws.max_row + 1
        ws.append([
            "TOPLAM", "",
            totals["empty"], totals["full"], totals["kanban"], totals["scrap"],
            totals["bdh"], totals["tonnage"],
            "", "", "",
        ])
        for col_idx in range(1, len(headers) + 1):
            cell = ws.cell(row=total_row_idx, column=col_idx)
            cell.fill = _TOTAL_FILL
            cell.font = _TOTAL_FONT
            cell.border = _BORDER
            if col_idx in (3, 4, 5, 6, 7, 8):
                cell.alignment = _RIGHT
                cell.number_format = "#,##0"
            elif col_idx == 1:
                cell.alignment = _RIGHT
            else:
                cell.alignment = _LEFT

    _autofit(ws, headers)
    return aggregates


def _build_uretim_yeri_ozeti_sheet(
    wb: Workbook, dept_aggs: dict[tuple[str, str], dict[str, Any]]
) -> None:
    """Sheet 3: per-site aggregate with percentage and ton/dolu KPI."""
    ws = wb.create_sheet("Üretim Yeri Özeti")
    headers = [
        "Üretim Yeri",
        "Boş", "Dolu", "Dolu içindeki Kanban", "Hurdaya ayrılacak",
        "Toplam Konteyner", "Toplam (%)",
        "Toplam Tonaj", "Dolu Konteyner Başına Yük (ton/konteyner)",
    ]
    ws.append(headers)
    _style_header_row(ws, len(headers))

    site_aggs: dict[str, dict[str, Any]] = {}
    for (site, _dept), agg in dept_aggs.items():
        s = site_aggs.setdefault(site, {
            "empty": 0, "full": 0, "kanban": 0, "scrap": 0, "tonnage": 0.0,
        })
        s["empty"] += int(agg["empty"] or 0)
        s["full"] += int(agg["full"] or 0)
        s["kanban"] += int(agg["kanban"] or 0)
        s["scrap"] += int(agg["scrap"] or 0)
        if agg["tonnage"] is not None:
            try:
                s["tonnage"] += float(agg["tonnage"])
            except (TypeError, ValueError):
                pass

    grand_total_bdh = sum(
        s["empty"] + s["full"] + s["scrap"] for s in site_aggs.values()
    )

    totals = {"empty": 0, "full": 0, "kanban": 0, "scrap": 0, "bdh": 0, "tonnage": 0.0}
    for idx, (site, s) in enumerate(sorted(site_aggs.items()), start=2):
        zebra = _ZEBRA_FILL if idx % 2 == 0 else None
        bdh = s["empty"] + s["full"] + s["scrap"]
        pct = (bdh / grand_total_bdh) if grand_total_bdh else 0  # stored as fraction
        ton_per = (s["tonnage"] / s["full"]) if s["full"] else 0

        values = [
            site,
            s["empty"], s["full"], s["kanban"], s["scrap"],
            bdh, pct,
            s["tonnage"], ton_per,
        ]
        ws.append(values)
        totals["empty"] += s["empty"]
        totals["full"] += s["full"]
        totals["kanban"] += s["kanban"]
        totals["scrap"] += s["scrap"]
        totals["bdh"] += bdh
        totals["tonnage"] += s["tonnage"]

        for col_idx in range(1, len(values) + 1):
            cell = ws.cell(row=idx, column=col_idx)
            cell.border = _BORDER
            if zebra:
                cell.fill = zebra
            if col_idx in (2, 3, 4, 5, 6):
                cell.alignment = _RIGHT
                cell.number_format = "#,##0"
            elif col_idx == 7:  # Toplam %
                cell.alignment = _RIGHT
                cell.number_format = "0.0%"
            elif col_idx == 8:  # Toplam Tonaj
                cell.alignment = _RIGHT
                cell.number_format = "#,##0"
            elif col_idx == 9:  # ton/konteyner
                cell.alignment = _RIGHT
                cell.number_format = "0.00"
            else:
                cell.alignment = _LEFT

    if site_aggs:
        total_row_idx = ws.max_row + 1
        ton_per_total = (totals["tonnage"] / totals["full"]) if totals["full"] else 0
        ws.append([
            "TOPLAM",
            totals["empty"], totals["full"], totals["kanban"], totals["scrap"],
            totals["bdh"], 1.0,
            totals["tonnage"], ton_per_total,
        ])
        for col_idx in range(1, len(headers) + 1):
            cell = ws.cell(row=total_row_idx, column=col_idx)
            cell.fill = _TOTAL_FILL
            cell.font = _TOTAL_FONT
            cell.border = _BORDER
            if col_idx in (2, 3, 4, 5, 6, 8):
                cell.alignment = _RIGHT
                cell.number_format = "#,##0"
            elif col_idx == 7:
                cell.alignment = _RIGHT
                cell.number_format = "0.0%"
            elif col_idx == 9:
                cell.alignment = _RIGHT
                cell.number_format = "0.00"
            elif col_idx == 1:
                cell.alignment = _RIGHT
            else:
                cell.alignment = _LEFT

    _autofit(ws, headers)


def _build_renk_ozeti_sheet(wb: Workbook, rows: list[dict[str, Any]]) -> None:
    """Sheet 4: per-color aggregate for the selected week."""
    ws = wb.create_sheet("Renk Özeti")
    headers = [
        "Renk", "Boş", "Dolu", "Dolu içindeki Kanban",
        "Hurdaya ayrılacak", "Toplam Konteyner",
    ]
    ws.append(headers)
    _style_header_row(ws, len(headers))

    color_aggs: dict[str, dict[str, int]] = {}
    color_order: list[str] = []
    for row in rows:
        color = row.get("Renk", "") or ""
        if color not in color_aggs:
            color_aggs[color] = {"empty": 0, "full": 0, "kanban": 0, "scrap": 0}
            color_order.append(color)
        c = color_aggs[color]
        c["empty"] += int(row.get("Boş") or 0)
        c["full"] += int(row.get("Dolu") or 0)
        c["kanban"] += int(row.get("Kanban") or 0)
        c["scrap"] += int(row.get("Hurda") or 0)

    totals = {"empty": 0, "full": 0, "kanban": 0, "scrap": 0, "bdh": 0}
    for idx, color in enumerate(color_order, start=2):
        c = color_aggs[color]
        bdh = c["empty"] + c["full"] + c["scrap"]
        values = [color, c["empty"], c["full"], c["kanban"], c["scrap"], bdh]
        ws.append(values)
        totals["empty"] += c["empty"]
        totals["full"] += c["full"]
        totals["kanban"] += c["kanban"]
        totals["scrap"] += c["scrap"]
        totals["bdh"] += bdh

        zebra = _ZEBRA_FILL if idx % 2 == 0 else None
        for col_idx in range(1, len(values) + 1):
            cell = ws.cell(row=idx, column=col_idx)
            cell.border = _BORDER
            if zebra:
                cell.fill = zebra
            if col_idx >= 2:
                cell.alignment = _RIGHT
                cell.number_format = "#,##0"
            else:
                cell.alignment = _LEFT

    if color_order:
        total_row_idx = ws.max_row + 1
        ws.append([
            "TOPLAM",
            totals["empty"], totals["full"], totals["kanban"],
            totals["scrap"], totals["bdh"],
        ])
        for col_idx in range(1, len(headers) + 1):
            cell = ws.cell(row=total_row_idx, column=col_idx)
            cell.fill = _TOTAL_FILL
            cell.font = _TOTAL_FONT
            cell.border = _BORDER
            if col_idx >= 2:
                cell.alignment = _RIGHT
                cell.number_format = "#,##0"
            else:
                cell.alignment = _RIGHT

    _autofit(ws, headers)


# ---------------------------------------------------------------------------
# Multi-week aggregation (used by ÖZET + Karşılaştırma sheets)
# ---------------------------------------------------------------------------

def _aggregate_all_weeks(
    all_rows: list[dict[str, Any]],
) -> tuple[
    dict[str, dict[str, float]],           # weekly_totals
    dict[str, dict[str, dict[str, float]]], # weekly_site
    dict[str, dict[str, int]],             # weekly_color (color → toplam konteyner)
    list[str],                              # ordered color list (discovery order)
]:
    """Aggregate the long-format rows into structures useful for charts.

    Tonnage is captured once per (week, site, department) because each color
    row of the same submission carries the same submission-level tonnage —
    summing it per color would multiply by color count.
    """
    weekly_totals: dict[str, dict[str, float]] = {}
    weekly_site: dict[str, dict[str, dict[str, float]]] = {}
    weekly_color: dict[str, dict[str, int]] = {}
    color_order: list[str] = []
    seen_colors: set[str] = set()

    tonnage_seen: set[tuple[str, str, str]] = set()

    for r in all_rows:
        week = r.get("Hafta") or ""
        site = r.get("Üretim Yeri") or ""
        dept = r.get("Bölüm") or ""
        color = r.get("Renk") or ""

        empty_v = int(r.get("Boş") or 0)
        full_v = int(r.get("Dolu") or 0)
        kanban_v = int(r.get("Kanban") or 0)
        scrap_v = int(r.get("Hurda") or 0)
        bdh_v = empty_v + full_v + scrap_v

        wt = weekly_totals.setdefault(week, {
            "empty": 0, "full": 0, "kanban": 0, "scrap": 0,
            "bdh": 0, "tonnage": 0.0,
        })
        wt["empty"] += empty_v
        wt["full"] += full_v
        wt["kanban"] += kanban_v
        wt["scrap"] += scrap_v
        wt["bdh"] += bdh_v

        ws_agg = weekly_site.setdefault(week, {}).setdefault(site, {
            "empty": 0, "full": 0, "kanban": 0, "scrap": 0,
            "bdh": 0, "tonnage": 0.0,
        })
        ws_agg["empty"] += empty_v
        ws_agg["full"] += full_v
        ws_agg["kanban"] += kanban_v
        ws_agg["scrap"] += scrap_v
        ws_agg["bdh"] += bdh_v

        if color and color not in seen_colors:
            seen_colors.add(color)
            color_order.append(color)
        wc = weekly_color.setdefault(week, {})
        wc[color] = wc.get(color, 0) + bdh_v

        key = (week, site, dept)
        if key not in tonnage_seen:
            tonnage_seen.add(key)
            t = r.get("Gerçekleşen Tonaj")
            if t is not None:
                try:
                    t_f = float(t)
                    wt["tonnage"] += t_f
                    ws_agg["tonnage"] += t_f
                except (TypeError, ValueError):
                    pass

    return weekly_totals, weekly_site, weekly_color, color_order


# ---------------------------------------------------------------------------
# ÖZET — charts across all weeks
# ---------------------------------------------------------------------------

def _build_ozet_charts_sheet(
    wb: Workbook, all_rows: list[dict[str, Any]]
) -> None:
    """Sheet 5 (ÖZET): four charts driven by tables placed to the right.

    Layout:
      - Charts in columns A:K (visible area).
      - Data tables driving the charts in columns N onwards.
    """
    ws = wb.create_sheet("ÖZET")
    ws["A1"] = "ÖZET — Tüm Haftaların Görüntüsü"
    ws["A1"].font = Font(bold=True, size=16, color="1F3A8A")
    ws.merge_cells("A1:K1")
    ws["A2"] = "Aşağıdaki grafikler tüm haftaların verisi üzerinden hesaplanır."
    ws["A2"].font = Font(italic=True, color="64748B")
    ws.merge_cells("A2:K2")

    if not all_rows:
        ws["A4"] = "Henüz veri yok — sayım girildikçe burada grafikler oluşacak."
        return

    weekly_totals, weekly_site, weekly_color, color_order = _aggregate_all_weeks(all_rows)
    weeks = sorted(weekly_totals.keys())
    all_sites = sorted({s for sd in weekly_site.values() for s in sd.keys()})

    # ================================================================
    # Table 1 (cols N..R): Hafta | Boş | Dolu | Kanban | Hurda
    # Drives Chart 1.
    # ================================================================
    t1_col = 14  # column N
    t1_headers = ["Hafta", "Boş", "Dolu", "Dolu İçindeki Kanban", "Hurdaya Ayrılacak"]
    for j, h in enumerate(t1_headers):
        cell = ws.cell(row=3, column=t1_col + j, value=h)
        cell.fill = _HEADER_FILL
        cell.font = _HEADER_FONT
        cell.alignment = _CENTER
    for i, w in enumerate(weeks):
        wt = weekly_totals[w]
        ws.cell(row=4 + i, column=t1_col, value=w).alignment = _CENTER
        ws.cell(row=4 + i, column=t1_col + 1, value=wt["empty"])
        ws.cell(row=4 + i, column=t1_col + 2, value=wt["full"])
        ws.cell(row=4 + i, column=t1_col + 3, value=wt["kanban"])
        ws.cell(row=4 + i, column=t1_col + 4, value=wt["scrap"])
    t1_last = 4 + len(weeks) - 1

    chart1 = BarChart()
    chart1.type = "col"
    chart1.style = 11
    chart1.grouping = "stacked"
    chart1.overlap = 100
    chart1.title = "Haftalık Toplam Konteyner Dağılımı (Boş / Dolu / Kanban / Hurda)"
    chart1.y_axis.title = "Konteyner Adedi"
    chart1.x_axis.title = "Hafta"
    data_ref = Reference(
        ws, min_col=t1_col + 1, min_row=3, max_col=t1_col + 4, max_row=t1_last,
    )
    chart1.add_data(data_ref, titles_from_data=True)
    cats_ref = Reference(ws, min_col=t1_col, min_row=4, max_row=t1_last)
    chart1.set_categories(cats_ref)
    chart1.height = 10
    chart1.width = 22
    ws.add_chart(chart1, "A4")

    # ================================================================
    # Table 2 (cols T..V): Hafta | Toplam Tonaj | Toplam Dolu | ton/Dolu
    # Drives Chart 2 (overall ton-per-full).
    # ================================================================
    t2_col = 20  # column T
    t2_headers = ["Hafta", "Toplam Tonaj", "Toplam Dolu", "Ton / Dolu Konteyner"]
    for j, h in enumerate(t2_headers):
        cell = ws.cell(row=3, column=t2_col + j, value=h)
        cell.fill = _HEADER_FILL
        cell.font = _HEADER_FONT
        cell.alignment = _CENTER
    for i, w in enumerate(weeks):
        wt = weekly_totals[w]
        ton_per = (wt["tonnage"] / wt["full"]) if wt["full"] else None
        ws.cell(row=4 + i, column=t2_col, value=w).alignment = _CENTER
        ws.cell(row=4 + i, column=t2_col + 1, value=wt["tonnage"])
        ws.cell(row=4 + i, column=t2_col + 2, value=wt["full"])
        ws.cell(row=4 + i, column=t2_col + 3, value=ton_per)
    t2_last = 4 + len(weeks) - 1

    chart2 = LineChart()
    chart2.style = 12
    chart2.title = "Dolu Konteyner Başına Yük — Genel (Haftalık)"
    chart2.y_axis.title = "Ton / Dolu Konteyner"
    chart2.x_axis.title = "Hafta"
    data_ref = Reference(
        ws, min_col=t2_col + 3, min_row=3, max_col=t2_col + 3, max_row=t2_last,
    )
    chart2.add_data(data_ref, titles_from_data=True)
    cats_ref = Reference(ws, min_col=t2_col, min_row=4, max_row=t2_last)
    chart2.set_categories(cats_ref)
    chart2.height = 10
    chart2.width = 22
    ws.add_chart(chart2, "A24")

    # ================================================================
    # Table 3: Hafta + columns per site, values = ton/dolu
    # Drives Chart 3 (per-site lines).
    # ================================================================
    t3_col = 25  # column Y (well away from t2)
    ws.cell(row=3, column=t3_col, value="Hafta").fill = _HEADER_FILL
    ws.cell(row=3, column=t3_col).font = _HEADER_FONT
    ws.cell(row=3, column=t3_col).alignment = _CENTER
    for j, site in enumerate(all_sites):
        cell = ws.cell(row=3, column=t3_col + 1 + j, value=site)
        cell.fill = _HEADER_FILL
        cell.font = _HEADER_FONT
        cell.alignment = _CENTER
    for i, w in enumerate(weeks):
        ws.cell(row=4 + i, column=t3_col, value=w).alignment = _CENTER
        sites_map = weekly_site.get(w, {})
        for j, site in enumerate(all_sites):
            sd = sites_map.get(site)
            if sd and sd["full"]:
                val = sd["tonnage"] / sd["full"]
            else:
                val = None
            ws.cell(row=4 + i, column=t3_col + 1 + j, value=val)
    t3_last = 4 + len(weeks) - 1

    chart3 = LineChart()
    chart3.style = 12
    chart3.title = "Dolu Konteyner Başına Yük — Üretim Yeri Kırılımı (Haftalık)"
    chart3.y_axis.title = "Ton / Dolu Konteyner"
    chart3.x_axis.title = "Hafta"
    if all_sites:
        data_ref = Reference(
            ws,
            min_col=t3_col + 1, min_row=3,
            max_col=t3_col + len(all_sites), max_row=t3_last,
        )
        chart3.add_data(data_ref, titles_from_data=True)
        cats_ref = Reference(ws, min_col=t3_col, min_row=4, max_row=t3_last)
        chart3.set_categories(cats_ref)
    chart3.height = 11
    chart3.width = 22
    ws.add_chart(chart3, "A44")

    # ================================================================
    # Table 4: Hafta + per-color totals
    # Drives Chart 4 (color breakdown stacked column).
    # ================================================================
    t4_col = t3_col + 1 + max(len(all_sites), 1) + 2
    ws.cell(row=3, column=t4_col, value="Hafta").fill = _HEADER_FILL
    ws.cell(row=3, column=t4_col).font = _HEADER_FONT
    ws.cell(row=3, column=t4_col).alignment = _CENTER
    for j, color in enumerate(color_order):
        cell = ws.cell(row=3, column=t4_col + 1 + j, value=color)
        cell.fill = _HEADER_FILL
        cell.font = _HEADER_FONT
        cell.alignment = _CENTER
    for i, w in enumerate(weeks):
        ws.cell(row=4 + i, column=t4_col, value=w).alignment = _CENTER
        wc = weekly_color.get(w, {})
        for j, color in enumerate(color_order):
            ws.cell(row=4 + i, column=t4_col + 1 + j, value=wc.get(color, 0))
    t4_last = 4 + len(weeks) - 1

    chart4 = BarChart()
    chart4.type = "col"
    chart4.style = 11
    chart4.grouping = "stacked"
    chart4.overlap = 100
    chart4.title = "Haftalık Renk Bazlı Konteyner Adetleri"
    chart4.y_axis.title = "Konteyner Adedi (Toplam B+D+H)"
    chart4.x_axis.title = "Hafta"
    if color_order:
        data_ref = Reference(
            ws,
            min_col=t4_col + 1, min_row=3,
            max_col=t4_col + len(color_order), max_row=t4_last,
        )
        chart4.add_data(data_ref, titles_from_data=True)
        cats_ref = Reference(ws, min_col=t4_col, min_row=4, max_row=t4_last)
        chart4.set_categories(cats_ref)
        # Map series to actual colors where possible.
        for series, color_name in zip(chart4.series, color_order):
            hex_code = _COLOR_HEX.get(color_name, "94A3B8")
            try:
                _set_bar_series_color(series, hex_code)
            except Exception:
                pass  # fall back to Excel default
    chart4.height = 11
    chart4.width = 22
    ws.add_chart(chart4, "A65")


# ---------------------------------------------------------------------------
# Üretim Yeri Karşılaştırma — weekly site-summary tables side by side
# ---------------------------------------------------------------------------

def _build_uretim_yeri_karsilastirma_sheet(
    wb: Workbook, all_rows: list[dict[str, Any]]
) -> None:
    """Sheet 6: per-week ``Üretim Yeri Özeti`` tables placed horizontally.

    Each week occupies 9 consecutive columns, separated by a 1-column gap.
    """
    ws = wb.create_sheet("Üretim Yeri Karşılaştırma")
    ws["A1"] = "Üretim Yeri Özeti — Haftalık Karşılaştırma"
    ws["A1"].font = Font(bold=True, size=14, color="1F3A8A")

    if not all_rows:
        ws["A3"] = "Henüz veri yok."
        return

    _, weekly_site, _, _ = _aggregate_all_weeks(all_rows)
    weeks = sorted(weekly_site.keys())

    sub_headers = [
        "Üretim Yeri", "Boş", "Dolu", "Dolu içindeki Kanban", "Hurdaya ayrılacak",
        "Toplam Konteyner", "Toplam (%)", "Toplam Tonaj",
        "Dolu Konteyner Başına Yük",
    ]
    cols_per_table = len(sub_headers)
    gap = 1

    start_col = 1
    for w in weeks:
        # Week title row (row 3) — merged across the table width.
        title_cell = ws.cell(row=3, column=start_col, value=w)
        title_cell.font = Font(bold=True, size=12, color="1F3A8A")
        title_cell.alignment = _CENTER
        title_cell.fill = _TOTAL_FILL
        ws.merge_cells(
            start_row=3, start_column=start_col,
            end_row=3, end_column=start_col + cols_per_table - 1,
        )

        # Column header row (row 4)
        for j, h in enumerate(sub_headers):
            cell = ws.cell(row=4, column=start_col + j, value=h)
            cell.fill = _HEADER_FILL
            cell.font = _HEADER_FONT
            cell.alignment = _CENTER
            cell.border = _BORDER

        sites_in_week = weekly_site[w]
        grand_total_bdh = sum(
            s["empty"] + s["full"] + s["scrap"] for s in sites_in_week.values()
        )
        totals = {"empty": 0, "full": 0, "kanban": 0, "scrap": 0,
                  "bdh": 0, "tonnage": 0.0}

        for r_offset, (site, agg) in enumerate(
            sorted(sites_in_week.items()), start=5
        ):
            bdh = agg["empty"] + agg["full"] + agg["scrap"]
            pct = (bdh / grand_total_bdh) if grand_total_bdh else 0
            ton_per = (agg["tonnage"] / agg["full"]) if agg["full"] else 0

            values = [
                site,
                agg["empty"], agg["full"], agg["kanban"], agg["scrap"],
                bdh, pct, agg["tonnage"], ton_per,
            ]
            for j, val in enumerate(values):
                cell = ws.cell(row=r_offset, column=start_col + j, value=val)
                cell.border = _BORDER
                if j == 0:
                    cell.alignment = _LEFT
                elif j == 6:
                    cell.alignment = _RIGHT
                    cell.number_format = "0.0%"
                elif j == 8:
                    cell.alignment = _RIGHT
                    cell.number_format = "0.00"
                else:
                    cell.alignment = _RIGHT
                    cell.number_format = "#,##0"

            totals["empty"] += agg["empty"]
            totals["full"] += agg["full"]
            totals["kanban"] += agg["kanban"]
            totals["scrap"] += agg["scrap"]
            totals["bdh"] += bdh
            totals["tonnage"] += agg["tonnage"]

        # TOPLAM row
        total_row = 5 + len(sites_in_week)
        ton_per_total = (totals["tonnage"] / totals["full"]) if totals["full"] else 0
        total_values = [
            "TOPLAM",
            totals["empty"], totals["full"], totals["kanban"], totals["scrap"],
            totals["bdh"], 1.0, totals["tonnage"], ton_per_total,
        ]
        for j, val in enumerate(total_values):
            cell = ws.cell(row=total_row, column=start_col + j, value=val)
            cell.fill = _TOTAL_FILL
            cell.font = _TOTAL_FONT
            cell.border = _BORDER
            if j == 0:
                cell.alignment = _RIGHT
            elif j == 6:
                cell.alignment = _RIGHT
                cell.number_format = "0.0%"
            elif j == 8:
                cell.alignment = _RIGHT
                cell.number_format = "0.00"
            else:
                cell.alignment = _RIGHT
                cell.number_format = "#,##0"

        # Column widths — site col wider, others compact.
        ws.column_dimensions[get_column_letter(start_col)].width = 22
        for j in range(1, cols_per_table):
            ws.column_dimensions[get_column_letter(start_col + j)].width = 14

        start_col += cols_per_table + gap

    ws.freeze_panes = "A5"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_week_excel(
    rows: list[dict[str, Any]],
    week_iso: str,
    week_human: str,
    all_weeks_rows: list[dict[str, Any]] | None = None,
) -> bytes:
    """Return an .xlsx byte string for the selected week.

    ``rows``           — output of ``get_week_export_rows(week_iso)``.
    ``all_weeks_rows`` — output of ``get_all_weeks_export_rows()``; used for
                        the ÖZET (charts) and Üretim Yeri Karşılaştırma
                        sheets. Pass ``None`` if you only need the per-week
                        sheets; the ÖZET sheet will show an empty notice.
    ``week_iso`` and ``week_human`` are accepted for backwards-compatible
    call sites but no longer surfaced in a "Bilgi" cover sheet.
    """
    wb = Workbook()
    _build_renk_kirilim_sheet(wb, rows)
    dept_aggs = _build_uretim_yeri_kirilim_sheet(wb, rows)
    _build_uretim_yeri_ozeti_sheet(wb, dept_aggs)
    _build_renk_ozeti_sheet(wb, rows)
    _build_ozet_charts_sheet(wb, all_weeks_rows or [])
    _build_uretim_yeri_karsilastirma_sheet(wb, all_weeks_rows or [])

    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def build_all_weeks_excel(rows: list[dict[str, Any]]) -> bytes:
    """Long-format export — one row per (week × site × department × color).

    Mirrors ``build_week_excel`` styling so it reads consistently with
    the per-week file, but adds Hafta / Hafta Aralığı / Ay / Yıl columns
    upfront so the user can pivot or filter quickly in Excel.
    """
    wb = Workbook()
    sheet = wb.active
    sheet.title = "Tüm Haftalar"

    headers = [
        "Hafta",
        "Hafta Aralığı",
        "Ay",
        "Yıl",
        "Üretim Yeri",
        "Bölüm",
        "Renk",
        "Boş",
        "Dolu",
        "Kanban",
        "Hurdaya Ayrılacak",
        "Toplam (B+D+H)",
        "Gerçekleşen Tonaj (t)",
        "Durum",
        "Giren Kullanıcı",
        "Sayım Tarihi",
        "Sayım Saati",
        "Gönderim Zamanı",
    ]
    sheet.append(headers)
    for cell in sheet[1]:
        cell.fill = _HEADER_FILL
        cell.font = _HEADER_FONT
        cell.alignment = _CENTER
        cell.border = _BORDER
    sheet.row_dimensions[1].height = 26
    sheet.freeze_panes = "A2"

    for idx, row in enumerate(rows, start=2):
        is_late = row.get("Durum") == "late_submitted"
        zebra = (idx % 2 == 0) and not is_late
        fill = _LATE_FILL if is_late else (_ZEBRA_FILL if zebra else None)

        week_iso = row.get("Hafta") or ""
        hafta_araligi, ay, yil = _week_iso_to_human(week_iso)

        bos_v = int(row.get("Boş") or 0)
        dolu_v = int(row.get("Dolu") or 0)
        hurda_v = int(row.get("Hurda") or 0)
        bdh_v = bos_v + dolu_v + hurda_v

        values = [
            week_iso,
            hafta_araligi,
            ay,
            yil if yil else "",
            row.get("Üretim Yeri", ""),
            row.get("Bölüm", ""),
            row.get("Renk", ""),
            row.get("Boş"),
            row.get("Dolu"),
            row.get("Kanban"),
            row.get("Hurda"),
            bdh_v,
            row.get("Gerçekleşen Tonaj"),
            _STATUS_LABEL.get(row.get("Durum"), row.get("Durum", "")),
            row.get("Giren Kullanıcı", ""),
            row.get("Sayım Tarihi", ""),
            row.get("Sayım Saati", ""),
            _fmt_ts(row.get("Gönderim Zamanı")),
        ]
        sheet.append(values)

        for col_idx in range(1, len(values) + 1):
            cell = sheet.cell(row=idx, column=col_idx)
            cell.border = _BORDER
            if fill:
                cell.fill = fill
            if col_idx in (8, 9, 10, 11, 12):
                cell.alignment = _RIGHT
                cell.number_format = "#,##0"
            elif col_idx == 13:
                cell.alignment = _RIGHT
                cell.number_format = "#,##0"
            elif col_idx == 14:
                cell.alignment = _CENTER
                if is_late:
                    cell.font = Font(bold=True, color="92400E")
            elif col_idx in (1, 4):
                cell.alignment = _CENTER
            else:
                cell.alignment = _LEFT

    _autofit(sheet, headers)

    # Cover sheet
    info = wb.create_sheet("Bilgi", 0)
    info.column_dimensions["A"].width = 24
    info.column_dimensions["B"].width = 60
    info["A1"] = "Norm Konteyner — Tüm Haftalar Sayım Raporu"
    info["A1"].font = Font(bold=True, size=16, color="1F3A8A")
    info.merge_cells("A1:B1")
    info["A3"] = "Toplam satır"
    info["B3"] = len(rows)
    weeks = sorted({r.get("Hafta") for r in rows if r.get("Hafta")}, reverse=True)
    info["A4"] = "Hafta sayısı"
    info["B4"] = len(weeks)
    if weeks:
        info["A5"] = "En yeni hafta"
        info["B5"] = weeks[0]
        info["A6"] = "En eski hafta"
        info["B6"] = weeks[-1]
    info["A7"] = "Oluşturulma"
    info["B7"] = now_tr().strftime("%Y-%m-%d %H:%M")
    for r in range(3, 8):
        info.cell(row=r, column=1).font = Font(bold=True)
        info.cell(row=r, column=1).alignment = _LEFT
        info.cell(row=r, column=2).alignment = _LEFT

    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()
