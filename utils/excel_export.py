"""Excel export helpers for the admin panel.

Per-week workbook (``build_week_excel``) layout:

    1. Renk Kırılımı           — selected week, per (dept × color) detail
    2. Üretim Yeri Kırılımı    — selected week, per-department aggregate
    3. Üretim Yeri Özeti       — selected week, per-site aggregate with %
                                 and ton/dolu KPI
    4. Renk Özeti              — selected week, per-color aggregate
    5. GRAFİKLER               — ALL weeks, charts only
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
from openpyxl.chart.data_source import NumFmt
from openpyxl.chart.label import DataLabelList
from openpyxl.chart.layout import Layout, ManualLayout
from openpyxl.chart.marker import Marker
from openpyxl.chart.shapes import GraphicalProperties
from openpyxl.chart.text import RichText, Text
from openpyxl.chart.title import Title
from openpyxl.drawing.line import LineProperties
from openpyxl.drawing.text import (
    CharacterProperties,
    Paragraph,
    ParagraphProperties,
    RegularTextRun,
    RichTextProperties,
)
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
    "Mor": "8B5CF6",
    "Kırmızı": "DC2626",
    "Siyah": "111827",
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

    for idx, ((site, dept), agg) in enumerate(
        sorted(
            aggregates.items(),
            key=lambda kv: (_site_sort_key(kv[0][0]), kv[0][1]),
        ),
        start=2,
    ):
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
    for idx, (site, s) in enumerate(
        sorted(site_aggs.items(), key=lambda kv: _site_sort_key(kv[0])),
        start=2,
    ):
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
    manual_aggs: list[dict[str, Any]] | None = None,
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

    ``manual_aggs`` lets the caller fold historical / pre-system data
    (rows from the ``manual_site_aggregates`` table) into the weekly +
    site aggregates without polluting the per-color or per-department
    structures (which have no manual-data counterpart).
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

    # Fold in the manual aggregates (no color / dept granularity); these
    # only touch ``weekly_totals`` and ``weekly_site``. Per-color charts
    # skip these weeks naturally because there are no color rows.
    if manual_aggs:
        for m in manual_aggs:
            week = m.get("week_iso") or ""
            site = m.get("site") or ""
            if not week or not site:
                continue
            empty_v = int(m.get("empty") or 0)
            full_v = int(m.get("full") or 0)
            scrap_v = int(m.get("scrap") or 0)
            bdh_v = empty_v + full_v + scrap_v
            tonnage_v = m.get("tonnage")

            wt = weekly_totals.setdefault(week, {
                "empty": 0, "full": 0, "kanban": 0, "scrap": 0,
                "bdh": 0, "tonnage": 0.0,
            })
            wt["empty"] += empty_v
            wt["full"] += full_v
            wt["scrap"] += scrap_v
            wt["bdh"] += bdh_v

            ws_agg = weekly_site.setdefault(week, {}).setdefault(site, {
                "empty": 0, "full": 0, "kanban": 0, "scrap": 0,
                "bdh": 0, "tonnage": 0.0,
            })
            ws_agg["empty"] += empty_v
            ws_agg["full"] += full_v
            ws_agg["scrap"] += scrap_v
            ws_agg["bdh"] += bdh_v

            if tonnage_v is not None:
                try:
                    t_f = float(tonnage_v)
                    wt["tonnage"] += t_f
                    ws_agg["tonnage"] += t_f
                except (TypeError, ValueError):
                    pass

    return weekly_totals, weekly_site, weekly_color, color_order


# ---------------------------------------------------------------------------
# ÖZET — charts across all weeks
# ---------------------------------------------------------------------------

# Display order used by the color-breakdown chart. Anything outside this
# list is appended at the end in discovery order.
_DEFINED_COLOR_ORDER = [
    "Mavi", "Turuncu", "Yeşil", "Gri", "MS Vida", "Sarı",
    "Mor", "Kırmızı", "Siyah",
]


# Production-site display order for charts where üretim yerleri sit on the
# X axis (charts 3 and 4). Anything not listed falls in alphabetically at
# the end so a newly-added site is still visible without a code change.
_SITE_ORDER = [
    "Norm Cıvata İzmir",
    "Norm Cıvata Salihli",
    "Norm Somun İzmir",
    "Norm Somun Salihli",
    "Uysal İzmir",
    "Uysal Salihli",
    "MS Vida",
    "Nedu",
    "Sac Şekillendirme",
    "Sıcak Dövme",
    "Norm Holding",
]


def _site_sort_key(site: str) -> tuple[int, str]:
    """Sort by ``_SITE_ORDER`` position; unknown sites fall to the end."""
    try:
        return (_SITE_ORDER.index(site), site)
    except ValueError:
        return (len(_SITE_ORDER), site)


def _short_week(week_iso: str) -> str:
    """Strip the year prefix from an ISO week code for chart axis use.

    ``2026-W18`` → ``W18``. Falls back to the original string if the
    input doesn't match the expected shape.
    """
    if not week_iso:
        return ""
    if "-W" in week_iso:
        try:
            _, suffix = week_iso.split("-W", 1)
            return f"W{suffix}"
        except ValueError:
            return week_iso
    return week_iso


def _clean_axis(axis) -> None:
    """Common axis styling: visible labels, no major gridlines."""
    axis.delete = False
    axis.majorGridlines = None
    axis.majorTickMark = "out"


def _horizontal_axis_title(text: str) -> Title:
    """Build an axis title rendered horizontally and anchored near the
    top of the axis instead of the default vertically-centered rotated
    layout.

    Excel's default Y-axis title is rotated 90° and centered along the
    axis. This helper forces ``rot=0`` (horizontal) and positions the
    title near the top edge so it reads naturally above the topmost
    Y-axis tick.
    """
    body_pr = RichTextProperties(rot=0, vert="horz")
    char_props = CharacterProperties(b=True, sz=1000)
    para_props = ParagraphProperties(defRPr=char_props)
    run = RegularTextRun(t=text)
    para = Paragraph(pPr=para_props, r=[run])
    rt = RichText(bodyPr=body_pr, p=[para])
    tx = Text(rich=rt)
    layout = Layout(
        manualLayout=ManualLayout(
            x=0.02, y=0.05, xMode="edge", yMode="edge",
        )
    )
    return Title(tx=tx, layout=layout, overlay=False)


def _top_left_chart_title(text: str) -> Title:
    """Chart title anchored at the top-left corner instead of top-center.

    Useful when data labels above the bars would otherwise overlap the
    centered title (e.g. chart 4 has tall stacks with Toplam labels on
    top — centered title collides with the tallest site's label).
    """
    body_pr = RichTextProperties(rot=0, vert="horz")
    char_props = CharacterProperties(b=True, sz=1100)
    para_props = ParagraphProperties(defRPr=char_props)
    run = RegularTextRun(t=text)
    para = Paragraph(pPr=para_props, r=[run])
    rt = RichText(bodyPr=body_pr, p=[para])
    tx = Text(rich=rt)
    layout = Layout(
        manualLayout=ManualLayout(
            x=0.02, y=0.02, xMode="edge", yMode="edge",
        )
    )
    return Title(tx=tx, layout=layout, overlay=False)


def _end_x_axis_title(text: str) -> Title:
    """Build an X-axis title anchored near the right edge of the chart
    (i.e. at the *end* of the X axis) instead of below its center.

    Matches ``_horizontal_axis_title`` styling so X and Y titles look
    visually consistent across charts.
    """
    body_pr = RichTextProperties(rot=0, vert="horz")
    char_props = CharacterProperties(b=True, sz=1000)
    para_props = ParagraphProperties(defRPr=char_props)
    run = RegularTextRun(t=text)
    para = Paragraph(pPr=para_props, r=[run])
    rt = RichText(bodyPr=body_pr, p=[para])
    tx = Text(rich=rt)
    layout = Layout(
        manualLayout=ManualLayout(
            x=0.93, y=0.93, xMode="edge", yMode="edge",
        )
    )
    return Title(tx=tx, layout=layout, overlay=False)


def _value_only_labels(
    position: str, num_format: str = "[$-tr-TR]#,##0"
) -> DataLabelList:
    """Data labels that show ONLY the numeric value.

    openpyxl/Excel sometimes display series name and category name
    alongside the value when those flags are left unset (interpreted
    as 'show by default'). Setting every other show* flag to False
    keeps the label to just the number.

    The ``num_format`` is written to the ``<c:dLbls><c:numFmt/>``
    element, but Excel still falls back to the source-cell format
    when ``sourceLinked`` defaults to true (and openpyxl can't write
    ``sourceLinked="0"`` here — its DataLabelList only accepts the
    format code as a string). To make the format actually take
    effect, ALSO call ``cell.number_format = num_format`` on the
    backing ``_veri`` sheet cells. The string passed here is
    redundant-but-harmless fallback.
    """
    return DataLabelList(
        showVal=True,
        showCatName=False,
        showSerName=False,
        showLegendKey=False,
        showPercent=False,
        showBubbleSize=False,
        dLblPos=position,
        numFmt=num_format,
    )


def _build_ozet_charts_sheet(
    wb: Workbook,
    all_rows: list[dict[str, Any]],
    manual_aggs: list[dict[str, Any]] | None = None,
) -> None:
    """Sheet 5 (ÖZET): four charts only.

    Backing data tables live in a ``veryHidden`` ``_veri`` sheet so the
    visible ÖZET sheet shows the title and the four charts and nothing
    else. Hidden-but-referenced cells continue to feed the charts.
    """
    ws = wb.create_sheet("GRAFİKLER")
    ws["A1"] = "GRAFİKLER — Tüm Haftaların Görüntüsü"
    ws["A1"].font = Font(bold=True, size=16, color="1F3A8A")
    ws.merge_cells("A1:K1")
    ws["A2"] = "Aşağıdaki grafikler tüm haftaların verisi üzerinden hesaplanır."
    ws["A2"].font = Font(italic=True, color="64748B")
    ws.merge_cells("A2:K2")

    if not all_rows and not manual_aggs:
        ws["A4"] = "Henüz veri yok — sayım girildikçe burada grafikler oluşacak."
        return

    # Hidden helper sheet: 'veryHidden' keeps it out of the unhide menu so
    # casual users can't stumble onto the raw data tables.
    data_ws = wb.create_sheet("_veri")
    data_ws.sheet_state = "veryHidden"

    weekly_totals, weekly_site, weekly_color, color_order = _aggregate_all_weeks(
        all_rows, manual_aggs,
    )
    weeks = sorted(weekly_totals.keys())
    # Custom site order — see _SITE_ORDER. Anything not on that list
    # falls through alphabetically at the end.
    all_sites = sorted(
        {s for sd in weekly_site.values() for s in sd.keys()},
        key=_site_sort_key,
    )
    last_3_weeks = weeks[-3:] if len(weeks) >= 3 else weeks[:]
    latest_week = weeks[-1] if weeks else None

    # ================================================================
    # Chart 1 — Clustered column: weekly total split by category
    #   X = weeks
    #   Series order: Boş, Dolu, Dolu İçindeki Kanban, Hurda (matches
    #   the per-week tables elsewhere in the workbook)
    # ================================================================
    # Kanban analitik olarak Dolu'nun alt kümesidir; bu grafikte ayrı
    # bir kategori olarak göstermek yanıltıcı toplam üretirdi. Yalnızca
    # üç AYRIK kategori stackleniyor: Boş, Dolu (Kanban dahil), Hurda.
    t1_col = 1
    t1_headers = ["Hafta", "Boş", "Dolu", "Hurdaya Ayrılacak", "Toplam"]
    for j, h in enumerate(t1_headers):
        data_ws.cell(row=1, column=t1_col + j, value=h)
    for i, w in enumerate(weeks):
        wt = weekly_totals[w]
        # Short label on the X axis ('W18' instead of '2026-W18') keeps
        # the category labels compact and readable across all charts.
        data_ws.cell(row=2 + i, column=t1_col, value=_short_week(w))
        # Apply Turkish thousand-separated format to data cells so the
        # chart data labels (which Excel pulls via sourceLinked=true)
        # inherit the format. See _value_only_labels() for rationale.
        for col_offset, key in enumerate(
            ["empty", "full", "scrap"], start=1
        ):
            cell = data_ws.cell(
                row=2 + i, column=t1_col + col_offset, value=wt[key]
            )
            cell.number_format = "[$-tr-TR]#,##0"
        # Toplam = B + D + H (workbook genelinde tutarlı tanım; stack
        # yüksekliği de aynı bu üç kategorinin toplamı, dolayısıyla
        # overlay etiketi stack tepesine birebir oturur).
        total = wt["empty"] + wt["full"] + wt["scrap"]
        total_cell = data_ws.cell(
            row=2 + i, column=t1_col + 4, value=total
        )
        total_cell.number_format = "[$-tr-TR]#,##0"
    t1_last = 1 + len(weeks)

    chart1 = BarChart()
    chart1.type = "col"
    chart1.style = 2
    chart1.grouping = "stacked"
    chart1.overlap = 100
    chart1.title = "Haftalık Toplam Konteyner Dağılımı"
    chart1.y_axis.title = _horizontal_axis_title("Konteyner Adedi")
    chart1.x_axis.title = _end_x_axis_title("Hafta")
    data_ref = Reference(
        data_ws,
        min_col=t1_col + 1, min_row=1,
        max_col=t1_col + 3, max_row=t1_last,
    )
    chart1.add_data(data_ref, titles_from_data=True)
    cats_ref = Reference(data_ws, min_col=t1_col, min_row=2, max_row=t1_last)
    chart1.set_categories(cats_ref)
    _clean_axis(chart1.x_axis)
    _clean_axis(chart1.y_axis)
    # Turkish thousand-separated format on Y-axis tick labels (5000 → 5.000)
    chart1.y_axis.numFmt = "[$-tr-TR]#,##0"
    # Per-segment data labels centered inside each stack segment so the
    # user sees Boş / Dolu / Hurda values without breaking the stack
    # visual. Toplam still goes on top via the overlay line.
    chart1.dataLabels = _value_only_labels("ctr")
    chart1.legend.position = "b"
    chart1.legend.overlay = False
    chart1.height = 11
    chart1.width = 26

    # Invisible "Toplam" line at the top of each stack — same value as
    # the stack height (B + D + H), so the data label lands right at
    # the stack top.
    total_line = LineChart()
    total_ref = Reference(
        data_ws,
        min_col=t1_col + 4, min_row=1,
        max_col=t1_col + 4, max_row=t1_last,
    )
    total_line.add_data(total_ref, titles_from_data=True)
    total_line.set_categories(cats_ref)
    for s in total_line.series:
        gp = GraphicalProperties()
        gp.line = LineProperties(noFill=True)
        s.graphicalProperties = gp
        s.marker = Marker(symbol="none")
    total_line.dataLabels = _value_only_labels("t")
    chart1 += total_line

    ws.add_chart(chart1, "A4")

    # ================================================================
    # Chart 2 — Line chart: overall ton/Dolu per week
    #   Single series across all weeks with markers + data labels.
    #   Data column layout: each row is one week so the chart resolves
    #   to ONE series with N points (not N series with 1 point each).
    # ================================================================
    t2_col = 7  # well clear of table 1
    data_ws.cell(row=1, column=t2_col, value="Hafta")
    data_ws.cell(row=1, column=t2_col + 1, value="Ton / Dolu Konteyner")
    for i, w in enumerate(weeks):
        wt = weekly_totals[w]
        ton_per = (wt["tonnage"] / wt["full"]) if wt["full"] else None
        data_ws.cell(row=2 + i, column=t2_col, value=_short_week(w))
        cell = data_ws.cell(row=2 + i, column=t2_col + 1, value=ton_per)
        cell.number_format = "[$-tr-TR]#,##0.00"
    t2_last = 1 + len(weeks)

    chart2 = LineChart()
    chart2.style = 2
    chart2.title = "Dolu Konteyner Başına Yük — Genel (Haftalık)"
    chart2.y_axis.title = _horizontal_axis_title("Ton / Dolu Konteyner")
    chart2.x_axis.title = _end_x_axis_title("Hafta")
    data_ref = Reference(
        data_ws,
        min_col=t2_col + 1, min_row=1,
        max_col=t2_col + 1, max_row=t2_last,
    )
    chart2.add_data(data_ref, titles_from_data=True)
    cats_ref = Reference(data_ws, min_col=t2_col, min_row=2, max_row=t2_last)
    chart2.set_categories(cats_ref)
    _clean_axis(chart2.x_axis)
    _clean_axis(chart2.y_axis)
    # ton/Dolu is fractional → two decimal places on both the Y-axis
    # tick labels and the per-point data labels.
    chart2.y_axis.numFmt = "[$-tr-TR]#,##0.00"
    # Tight Y-axis band (0.20 → 0.90) — values typically cluster in this
    # range, and forcing the floor/ceiling surfaces week-on-week variance
    # that Excel's auto-scale would otherwise flatten.
    chart2.y_axis.scaling.min = 0.20
    chart2.y_axis.scaling.max = 0.90
    chart2.dataLabels = _value_only_labels("t", "[$-tr-TR]#,##0.00")
    for series in chart2.series:
        series.marker = Marker(symbol="circle", size=7)
        # Force a single solid line color (navy blue) so the line reads
        # as one continuous series instead of a default per-segment
        # auto-gradient.
        gp = GraphicalProperties()
        gp.line = LineProperties(solidFill="1F3A8A", w=22000)
        series.graphicalProperties = gp
    chart2.legend = None  # single series — legend is just noise
    chart2.height = 11
    chart2.width = 26
    ws.add_chart(chart2, "A26")

    # ================================================================
    # Chart 3 — Clustered column: ton/Dolu per site for last 3 weeks
    #   X = production sites
    #   Series = last 3 weeks (one cluster of 3 bars per site)
    # ================================================================
    t3_col = 10
    data_ws.cell(row=1, column=t3_col, value="Üretim Yeri")
    for j, w in enumerate(last_3_weeks):
        # Series headers become legend entries → short week label.
        data_ws.cell(row=1, column=t3_col + 1 + j, value=_short_week(w))
    for i, site in enumerate(all_sites):
        data_ws.cell(row=2 + i, column=t3_col, value=site)
        for j, w in enumerate(last_3_weeks):
            sd = weekly_site.get(w, {}).get(site)
            val = (sd["tonnage"] / sd["full"]) if (sd and sd["full"]) else None
            cell = data_ws.cell(row=2 + i, column=t3_col + 1 + j, value=val)
            cell.number_format = "[$-tr-TR]#,##0.00"
    t3_last = 1 + len(all_sites)

    chart3 = BarChart()
    chart3.type = "col"
    chart3.style = 2
    chart3.grouping = "clustered"
    chart3.title = "Dolu Konteyner Başına Yük — Üretim Yeri Kırılımı (Son 3 Hafta)"
    chart3.y_axis.title = _horizontal_axis_title("Ton / Dolu Konteyner")
    chart3.x_axis.title = _end_x_axis_title("Üretim Yeri")
    if last_3_weeks and all_sites:
        data_ref = Reference(
            data_ws,
            min_col=t3_col + 1, min_row=1,
            max_col=t3_col + len(last_3_weeks), max_row=t3_last,
        )
        chart3.add_data(data_ref, titles_from_data=True)
        cats_ref = Reference(data_ws, min_col=t3_col, min_row=2, max_row=t3_last)
        chart3.set_categories(cats_ref)
    _clean_axis(chart3.x_axis)
    _clean_axis(chart3.y_axis)
    # ton/Dolu is fractional → two decimal places everywhere (Y-axis +
    # data labels).
    chart3.y_axis.numFmt = "[$-tr-TR]#,##0.00"
    chart3.dataLabels = _value_only_labels("outEnd", "[$-tr-TR]#,##0.00")
    chart3.legend.position = "b"
    chart3.legend.overlay = False
    # Wider than other charts: 11 sites × 3 weekly bars per site = 33
    # columns, so the chart needs the extra width to keep labels
    # legible without overlapping.
    chart3.height = 13
    chart3.width = 38
    ws.add_chart(chart3, "A48")

    # ================================================================
    # Chart 4 — Stacked column: color breakdown per site (latest week)
    #   X = production sites
    #   Stacks = colors in defined order
    #   Each color series painted with its brand hex
    # ================================================================
    # Aggregate per (site, color) for the latest week.
    site_color_latest: dict[str, dict[str, int]] = {}
    if latest_week:
        for r in all_rows:
            if r.get("Hafta") != latest_week:
                continue
            site = r.get("Üretim Yeri") or ""
            color = r.get("Renk") or ""
            cnt = (
                int(r.get("Boş") or 0)
                + int(r.get("Dolu") or 0)
                + int(r.get("Hurda") or 0)
            )
            site_color_latest.setdefault(site, {})
            site_color_latest[site][color] = (
                site_color_latest[site].get(color, 0) + cnt
            )

    # Color order: defined order first, then any extras in discovery order.
    chart4_colors = (
        [c for c in _DEFINED_COLOR_ORDER if c in color_order]
        + [c for c in color_order if c not in _DEFINED_COLOR_ORDER]
    )
    # Custom production-site order on the X axis.
    chart4_sites = sorted(site_color_latest.keys(), key=_site_sort_key)

    t4_col = 18
    data_ws.cell(row=1, column=t4_col, value="Üretim Yeri")
    for j, color in enumerate(chart4_colors):
        data_ws.cell(row=1, column=t4_col + 1 + j, value=color)
    # Column after the last color holds the per-site stack total used by
    # the invisible 'Toplam' overlay line.
    t4_total_col = t4_col + 1 + len(chart4_colors)
    data_ws.cell(row=1, column=t4_total_col, value="Toplam")
    for i, site in enumerate(chart4_sites):
        data_ws.cell(row=2 + i, column=t4_col, value=site)
        sc = site_color_latest.get(site, {})
        for j, color in enumerate(chart4_colors):
            cell = data_ws.cell(
                row=2 + i, column=t4_col + 1 + j, value=sc.get(color, 0)
            )
            cell.number_format = "[$-tr-TR]#,##0"
        total = sum(sc.values())
        total_cell = data_ws.cell(row=2 + i, column=t4_total_col, value=total)
        total_cell.number_format = "[$-tr-TR]#,##0"
    t4_last = 1 + len(chart4_sites)

    chart4 = BarChart()
    chart4.type = "col"
    chart4.style = 2
    chart4.grouping = "stacked"
    chart4.overlap = 100
    title_suffix = f" ({_short_week(latest_week)})" if latest_week else ""
    # Top-left positioning so the title doesn't sit above the tallest
    # stack and collide with that stack's Toplam label (Uysal Salihli
    # routinely hits the centered-title zone).
    chart4.title = _top_left_chart_title(
        f"Üretim Yerleri Renk Dağılımı{title_suffix}"
    )
    chart4.y_axis.title = _horizontal_axis_title("Konteyner Adedi")
    chart4.x_axis.title = _end_x_axis_title("Üretim Yeri")
    if chart4_colors and chart4_sites:
        data_ref = Reference(
            data_ws,
            min_col=t4_col + 1, min_row=1,
            max_col=t4_col + len(chart4_colors), max_row=t4_last,
        )
        chart4.add_data(data_ref, titles_from_data=True)
        cats_ref4 = Reference(
            data_ws, min_col=t4_col, min_row=2, max_row=t4_last,
        )
        chart4.set_categories(cats_ref4)
        for series, color_name in zip(chart4.series, chart4_colors):
            hex_code = _COLOR_HEX.get(color_name, "94A3B8")
            try:
                _set_bar_series_color(series, hex_code)
            except Exception:
                pass
    _clean_axis(chart4.x_axis)
    _clean_axis(chart4.y_axis)
    chart4.y_axis.numFmt = "[$-tr-TR]#,##0"
    # No per-segment data labels: with 6 stacked colors × 11 sites the
    # values pile on top of each other. We do show a single 'Toplam'
    # label above each stack via an invisible overlay line (below).
    chart4.legend.position = "b"
    chart4.legend.overlay = False
    # Taller chart gives the Toplam labels room above the stacks so the
    # title (now anchored top-left) and the labels don't fight for the
    # same vertical band.
    chart4.height = 16
    chart4.width = 38

    # Invisible 'Toplam' line that sits at the top of each stack and
    # carries the total-count data label. Mirrors the chart-1 pattern.
    if chart4_colors and chart4_sites:
        chart4_total_line = LineChart()
        total_ref4 = Reference(
            data_ws,
            min_col=t4_total_col, min_row=1,
            max_col=t4_total_col, max_row=t4_last,
        )
        chart4_total_line.add_data(total_ref4, titles_from_data=True)
        chart4_total_line.set_categories(cats_ref4)
        for s in chart4_total_line.series:
            gp = GraphicalProperties()
            gp.line = LineProperties(noFill=True)
            s.graphicalProperties = gp
            s.marker = Marker(symbol="none")
        chart4_total_line.dataLabels = _value_only_labels("t")
        chart4 += chart4_total_line

    ws.add_chart(chart4, "A74")


# ---------------------------------------------------------------------------
# Üretim Yeri Karşılaştırma — weekly site-summary tables side by side
# ---------------------------------------------------------------------------

def _build_uretim_yeri_karsilastirma_sheet(
    wb: Workbook,
    all_rows: list[dict[str, Any]],
    manual_aggs: list[dict[str, Any]] | None = None,
) -> None:
    """Sheet 6: per-week ``Üretim Yeri Özeti`` tables stacked vertically.

    Each week renders its own table top-to-bottom (week-title row, header
    row, one row per production site, then a TOPLAM row). A two-row gap
    separates consecutive weeks. Newest week first.
    """
    ws = wb.create_sheet("Üretim Yeri Karşılaştırma")
    ws["A1"] = "Üretim Yeri Özeti — Haftalık Karşılaştırma"
    ws["A1"].font = Font(bold=True, size=14, color="1F3A8A")

    if not all_rows and not manual_aggs:
        ws["A3"] = "Henüz veri yok."
        return

    _, weekly_site, _, _ = _aggregate_all_weeks(all_rows, manual_aggs)
    # Newest week at the top — admins typically open this sheet to compare
    # 'this week' against the recent past.
    weeks = sorted(weekly_site.keys(), reverse=True)

    sub_headers = [
        "Üretim Yeri", "Boş", "Dolu", "Dolu içindeki Kanban", "Hurdaya ayrılacak",
        "Toplam Konteyner", "Toplam (%)", "Toplam Tonaj",
        "Dolu Konteyner Başına Yük",
    ]
    cols_per_table = len(sub_headers)
    gap_rows = 2

    # Column widths — set once for the whole sheet (same columns reused
    # by every weekly sub-table).
    ws.column_dimensions[get_column_letter(1)].width = 22
    for j in range(2, cols_per_table + 1):
        ws.column_dimensions[get_column_letter(j)].width = 14

    start_row = 3
    for w in weeks:
        # Week title row, merged across the table width.
        title_cell = ws.cell(row=start_row, column=1, value=w)
        title_cell.font = Font(bold=True, size=12, color="1F3A8A")
        title_cell.alignment = _CENTER
        title_cell.fill = _TOTAL_FILL
        ws.merge_cells(
            start_row=start_row, start_column=1,
            end_row=start_row, end_column=cols_per_table,
        )

        # Column header row
        header_row = start_row + 1
        for j, h in enumerate(sub_headers):
            cell = ws.cell(row=header_row, column=1 + j, value=h)
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
            sorted(
                sites_in_week.items(),
                key=lambda kv: _site_sort_key(kv[0]),
            ),
            start=header_row + 1,
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
                cell = ws.cell(row=r_offset, column=1 + j, value=val)
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

        total_row = header_row + 1 + len(sites_in_week)
        ton_per_total = (totals["tonnage"] / totals["full"]) if totals["full"] else 0
        total_values = [
            "TOPLAM",
            totals["empty"], totals["full"], totals["kanban"], totals["scrap"],
            totals["bdh"], 1.0, totals["tonnage"], ton_per_total,
        ]
        for j, val in enumerate(total_values):
            cell = ws.cell(row=total_row, column=1 + j, value=val)
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

        # Move start_row past this week's table plus the gap.
        start_row = total_row + 1 + gap_rows

    ws.freeze_panes = "A3"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_week_excel(
    rows: list[dict[str, Any]],
    week_iso: str,
    week_human: str,
    all_weeks_rows: list[dict[str, Any]] | None = None,
    manual_aggs: list[dict[str, Any]] | None = None,
) -> bytes:
    """Return an .xlsx byte string for the selected week.

    ``rows``           — output of ``get_week_export_rows(week_iso)``.
    ``all_weeks_rows`` — output of ``get_all_weeks_export_rows()``; used
                        for the GRAFİKLER (charts) and Üretim Yeri
                        Karşılaştırma sheets.
    ``manual_aggs``    — output of ``get_manual_site_aggregates()``;
                        per-(week, site) totals for historical weeks
                        counted outside the normal flow. Folded into
                        the charts + comparison sheet via
                        ``_aggregate_all_weeks``.
    ``week_iso`` and ``week_human`` are accepted for backwards-compatible
    call sites but no longer surfaced in a 'Bilgi' cover sheet.
    """
    wb = Workbook()
    _build_renk_kirilim_sheet(wb, rows)
    dept_aggs = _build_uretim_yeri_kirilim_sheet(wb, rows)
    _build_uretim_yeri_ozeti_sheet(wb, dept_aggs)
    _build_renk_ozeti_sheet(wb, rows)
    _build_ozet_charts_sheet(wb, all_weeks_rows or [], manual_aggs or [])
    _build_uretim_yeri_karsilastirma_sheet(
        wb, all_weeks_rows or [], manual_aggs or []
    )

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
