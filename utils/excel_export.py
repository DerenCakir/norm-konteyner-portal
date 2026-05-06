"""Excel export helpers for the admin panel.

Builds a styled .xlsx workbook from the rows returned by
``get_week_export_rows``. Output goal: open in Excel and immediately be
readable — frozen header, auto-fit column widths, Turkish status labels,
human-readable timestamps, alternating row tint, summary sheet on top.
"""

from __future__ import annotations

from datetime import datetime
from io import BytesIO
from typing import Any

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill, Border, Side
from openpyxl.utils import get_column_letter


_STATUS_LABEL = {
    "submitted": "Zamanında",
    "late_submitted": "Geç giriş",
    "draft": "Taslak",
}

_HEADER_FILL = PatternFill("solid", fgColor="1F3A8A")
_HEADER_FONT = Font(bold=True, color="FFFFFF", size=11)
_ZEBRA_FILL = PatternFill("solid", fgColor="F1F5F9")
_LATE_FILL = PatternFill("solid", fgColor="FEF3C7")
_THIN = Side(style="thin", color="D8E4F2")
_BORDER = Border(left=_THIN, right=_THIN, top=_THIN, bottom=_THIN)
_CENTER = Alignment(horizontal="center", vertical="center")
_LEFT = Alignment(horizontal="left", vertical="center")
_RIGHT = Alignment(horizontal="right", vertical="center")


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


def build_week_excel(rows: list[dict[str, Any]], week_iso: str, week_human: str) -> bytes:
    """Return an .xlsx byte string for the given week's submissions."""
    wb = Workbook()

    # -----------------------------------------------------------------
    # Sheet 1: Detay (one row per department × color)
    # -----------------------------------------------------------------
    detail = wb.active
    detail.title = "Detay"

    headers = [
        "Üretim Yeri",
        "Bölüm",
        "Renk",
        "Boş",
        "Dolu",
        "Kanban",
        "Gerçekleşen Tonaj (t)",
        "Durum",
        "Giren Kullanıcı",
        "Sayım Tarihi",
        "Sayım Saati",
        "Gönderim Zamanı",
    ]
    detail.append(headers)
    for cell in detail[1]:
        cell.fill = _HEADER_FILL
        cell.font = _HEADER_FONT
        cell.alignment = _CENTER
        cell.border = _BORDER

    detail.row_dimensions[1].height = 26
    detail.freeze_panes = "A2"

    for idx, row in enumerate(rows, start=2):
        is_late = row.get("Durum") == "late_submitted"
        zebra = (idx % 2 == 0) and not is_late
        fill = _LATE_FILL if is_late else (_ZEBRA_FILL if zebra else None)

        values = [
            row.get("Üretim Yeri", ""),
            row.get("Bölüm", ""),
            row.get("Renk", ""),
            row.get("Boş"),
            row.get("Dolu"),
            row.get("Kanban"),
            row.get("Gerçekleşen Tonaj"),
            _STATUS_LABEL.get(row.get("Durum"), row.get("Durum", "")),
            row.get("Giren Kullanıcı", ""),
            row.get("Sayım Tarihi", ""),
            row.get("Sayım Saati", ""),
            _fmt_ts(row.get("Gönderim Zamanı")),
        ]
        detail.append(values)

        for col_idx, val in enumerate(values, start=1):
            cell = detail.cell(row=idx, column=col_idx)
            cell.border = _BORDER
            if fill:
                cell.fill = fill
            if col_idx in (4, 5, 6):  # numeric counts
                cell.alignment = _RIGHT
                cell.number_format = "#,##0"
            elif col_idx == 7:  # tonnage
                cell.alignment = _RIGHT
                cell.number_format = "#,##0.00"
            elif col_idx == 8:  # status
                cell.alignment = _CENTER
                if is_late:
                    cell.font = Font(bold=True, color="92400E")
            else:
                cell.alignment = _LEFT

    _autofit(detail, headers)

    # -----------------------------------------------------------------
    # Sheet 2: Özet (per-department aggregate)
    # -----------------------------------------------------------------
    summary = wb.create_sheet("Özet")
    summary_headers = [
        "Üretim Yeri",
        "Bölüm",
        "Toplam Boş",
        "Toplam Dolu",
        "Toplam Kanban",
        "Tonaj (t)",
        "Durum",
        "Giren Kullanıcı",
        "Gönderim Zamanı",
    ]
    summary.append(summary_headers)
    for cell in summary[1]:
        cell.fill = _HEADER_FILL
        cell.font = _HEADER_FONT
        cell.alignment = _CENTER
        cell.border = _BORDER
    summary.row_dimensions[1].height = 26
    summary.freeze_panes = "A2"

    aggregates: dict[tuple[str, str], dict[str, Any]] = {}
    for row in rows:
        key = (row.get("Üretim Yeri", ""), row.get("Bölüm", ""))
        agg = aggregates.setdefault(key, {
            "empty": 0, "full": 0, "kanban": 0,
            "tonnage": row.get("Gerçekleşen Tonaj"),
            "status": row.get("Durum"),
            "user": row.get("Giren Kullanıcı", ""),
            "submitted_at": row.get("Gönderim Zamanı"),
        })
        agg["empty"] += int(row.get("Boş") or 0)
        agg["full"] += int(row.get("Dolu") or 0)
        agg["kanban"] += int(row.get("Kanban") or 0)

    for idx, ((site, dept), agg) in enumerate(sorted(aggregates.items()), start=2):
        is_late = agg["status"] == "late_submitted"
        fill = _LATE_FILL if is_late else (_ZEBRA_FILL if idx % 2 == 0 else None)
        values = [
            site, dept,
            agg["empty"], agg["full"], agg["kanban"],
            agg["tonnage"],
            _STATUS_LABEL.get(agg["status"], agg["status"] or ""),
            agg["user"],
            _fmt_ts(agg["submitted_at"]),
        ]
        summary.append(values)
        for col_idx, val in enumerate(values, start=1):
            cell = summary.cell(row=idx, column=col_idx)
            cell.border = _BORDER
            if fill:
                cell.fill = fill
            if col_idx in (3, 4, 5):
                cell.alignment = _RIGHT
                cell.number_format = "#,##0"
            elif col_idx == 6:
                cell.alignment = _RIGHT
                cell.number_format = "#,##0.00"
            elif col_idx == 7:
                cell.alignment = _CENTER
                if is_late:
                    cell.font = Font(bold=True, color="92400E")
            else:
                cell.alignment = _LEFT

    _autofit(summary, summary_headers)

    # -----------------------------------------------------------------
    # Sheet 3: Bilgi (cover info)
    # -----------------------------------------------------------------
    info = wb.create_sheet("Bilgi", 0)
    info.column_dimensions["A"].width = 24
    info.column_dimensions["B"].width = 60

    info["A1"] = "Norm Konteyner — Sayım Raporu"
    info["A1"].font = Font(bold=True, size=16, color="1F3A8A")
    info.merge_cells("A1:B1")

    info["A3"] = "Hafta"
    info["B3"] = f"{week_iso} ({week_human})"
    info["A4"] = "Bölüm sayısı (giren)"
    info["B4"] = len(aggregates)
    info["A5"] = "Detay satır sayısı"
    info["B5"] = len(rows)
    info["A6"] = "Geç giriş kayıt"
    info["B6"] = sum(1 for a in aggregates.values() if a["status"] == "late_submitted")
    info["A7"] = "Oluşturulma"
    info["B7"] = datetime.now().strftime("%Y-%m-%d %H:%M")

    for r in range(3, 8):
        info.cell(row=r, column=1).font = Font(bold=True)
        info.cell(row=r, column=1).alignment = _LEFT
        info.cell(row=r, column=2).alignment = _LEFT

    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


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
