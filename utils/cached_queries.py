"""Cached read queries shared by Streamlit pages.

The portal is read-heavy and Streamlit reruns the active page on each
interaction. A short TTL keeps the production UI responsive without making
admin changes feel stale for long.
"""

from __future__ import annotations

from typing import Any

import streamlit as st
from sqlalchemy import select

from db.connection import get_session
from db.models import (
    Color,
    CountDetail,
    CountSubmission,
    Department,
    ProductionSite,
    User,
    UserDepartment,
)
from utils.week import now_tr


def _to_tr_iso(dt) -> str | None:
    """Convert a (UTC-aware or naive) datetime to TR-aware ISO string.

    PostgreSQL TIMESTAMPTZ comes back as UTC-aware. Without conversion
    the ISO string ends up displaying 3 hours behind in the UI.
    """
    if dt is None:
        return None
    return now_tr(dt).isoformat()


CACHE_TTL_SECONDS = 300


def clear_cached_queries() -> None:
    """Clear cached read models after admin mutations."""
    get_available_weeks.clear()
    get_active_sites_departments.clear()
    get_active_colors.clear()
    get_week_submissions_with_users.clear()
    get_week_count_details.clear()
    get_department_users.clear()
    get_analysis_rows.clear()
    get_active_department_count.clear()
    get_week_export_rows.clear()
    get_all_weeks_export_rows.clear()


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def get_available_weeks(default_week: str) -> list[str]:
    with get_session() as s:
        weeks = list(s.execute(
            select(CountSubmission.week_iso)
            .distinct()
            .order_by(CountSubmission.week_iso.desc())
        ).scalars())

    if default_week not in weeks:
        weeks = [default_week] + weeks
    return weeks


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def get_active_sites_departments() -> list[dict[str, Any]]:
    with get_session() as s:
        rows = list(s.execute(
            select(ProductionSite, Department)
            .join(Department, Department.production_site_id == ProductionSite.id)
            .where(Department.is_active.is_(True))
            .order_by(ProductionSite.name, Department.name)
        ).all())

    return [
        {
            "site_id": site.id,
            "site_name": site.name,
            "department_id": dept.id,
            "department_name": dept.name,
            "weekly_tonnage_target": (
                float(dept.weekly_tonnage_target)
                if dept.weekly_tonnage_target is not None else None
            ),
        }
        for site, dept in rows
    ]


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def get_active_colors() -> list[dict[str, Any]]:
    with get_session() as s:
        colors = list(s.execute(
            select(Color)
            .where(Color.is_active.is_(True))
            .order_by(Color.sort_order, Color.id)
        ).scalars())

    return [
        {
            "color_id": color.id,
            "name": color.name,
            "hex_code": color.hex_code,
            "sort_order": color.sort_order,
        }
        for color in colors
    ]


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def get_week_submissions_with_users(week_iso: str) -> list[dict[str, Any]]:
    with get_session() as s:
        rows = list(s.execute(
            select(CountSubmission, User)
            .join(User, CountSubmission.user_id == User.id)
            .where(CountSubmission.week_iso == week_iso)
        ).all())

    result: list[dict[str, Any]] = []
    for sub, user in rows:
        result.append({
            "submission_id": sub.id,
            "department_id": sub.department_id,
            "user_id": user.id,
            "user_full_name": user.full_name,
            "week_iso": sub.week_iso,
            "status": sub.status,
            "count_date": str(sub.count_date),
            "submitted_at": _to_tr_iso(sub.submitted_at),
            "actual_tonnage": float(sub.actual_tonnage) if sub.actual_tonnage else None,
        })
    return result


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def get_week_count_details(week_iso: str) -> list[dict[str, int]]:
    with get_session() as s:
        rows = list(s.execute(
            select(CountSubmission, CountDetail)
            .join(CountDetail, CountDetail.submission_id == CountSubmission.id)
            .where(CountSubmission.week_iso == week_iso)
        ).all())

    return [
        {
            "submission_id": sub.id,
            "department_id": sub.department_id,
            "color_id": detail.color_id,
            "empty_count": detail.empty_count,
            "full_count": detail.full_count,
            "kanban_count": detail.kanban_count,
            "scrap_count": detail.scrap_count,
        }
        for sub, detail in rows
    ]


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def get_department_users(include_inactive: bool = False) -> dict[int, list[dict[str, Any]]]:
    with get_session() as s:
        query = (
            select(UserDepartment.department_id, User)
            .join(User, User.id == UserDepartment.user_id)
            .order_by(User.full_name)
        )
        if not include_inactive:
            query = query.where(User.is_active.is_(True))
        rows = list(s.execute(query).all())

    dept_users: dict[int, list[dict[str, Any]]] = {}
    for dept_id, user in rows:
        dept_users.setdefault(dept_id, []).append({
            "user_id": user.id,
            "full_name": user.full_name,
            "username": user.username,
            "is_active": user.is_active,
        })
    return dept_users


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def get_active_department_count() -> int:
    with get_session() as s:
        rows = s.execute(
            select(Department.id).where(Department.is_active.is_(True))
        ).all()
    return len(rows)


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def get_analysis_rows(week_isos: tuple[str, ...]) -> list[dict[str, Any]]:
    with get_session() as s:
        rows = s.execute(
            select(
                CountSubmission.id.label("submission_id"),
                CountSubmission.week_iso,
                CountSubmission.department_id,
                CountSubmission.user_id,
                CountSubmission.status,
                CountSubmission.actual_tonnage,
                CountSubmission.submitted_at,
                CountDetail.color_id,
                CountDetail.empty_count,
                CountDetail.full_count,
                CountDetail.kanban_count,
                CountDetail.scrap_count,
                Color.sort_order.label("color_sort_order"),
                Department.name.label("department"),
                Department.weekly_tonnage_target,
                ProductionSite.id.label("site_id"),
                ProductionSite.name.label("site"),
                Color.name.label("color"),
            )
            .join(CountDetail, CountDetail.submission_id == CountSubmission.id)
            .join(Department, Department.id == CountSubmission.department_id)
            .join(ProductionSite, ProductionSite.id == Department.production_site_id)
            .join(Color, Color.id == CountDetail.color_id)
            .where(CountSubmission.week_iso.in_(week_isos))
        ).all()

    return [
        {
            "submission_id": row.submission_id,
            "week_iso": row.week_iso,
            "department_id": row.department_id,
            "user_id": row.user_id,
            "status": row.status,
            "actual_tonnage": float(row.actual_tonnage) if row.actual_tonnage is not None else None,
            "submitted_at": _to_tr_iso(row.submitted_at),
            "color_id": row.color_id,
            "empty_count": row.empty_count,
            "full_count": row.full_count,
            "kanban_count": row.kanban_count,
            "scrap_count": row.scrap_count,
            "department": row.department,
            "weekly_tonnage_target": (
                float(row.weekly_tonnage_target)
                if row.weekly_tonnage_target is not None else None
            ),
            "site_id": row.site_id,
            "site": row.site,
            "color": row.color,
            "color_sort_order": row.color_sort_order,
        }
        for row in rows
    ]


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def get_all_weeks_export_rows() -> list[dict[str, Any]]:
    """Same shape as ``get_week_export_rows`` but for every week with data.

    Used by the 'tüm haftalar' Excel export. Ordered by week (descending),
    site, department, color so the resulting workbook reads naturally
    when scrolling.
    """
    with get_session() as s:
        rows = s.execute(
            select(
                CountSubmission.id.label("submission_id"),
                CountSubmission.week_iso,
                CountSubmission.status,
                CountSubmission.count_date,
                CountSubmission.count_time,
                CountSubmission.actual_tonnage,
                CountSubmission.submitted_at,
                ProductionSite.name.label("site"),
                Department.name.label("department"),
                User.username,
                User.full_name,
                Color.name.label("color"),
                CountDetail.empty_count,
                CountDetail.full_count,
                CountDetail.kanban_count,
                CountDetail.scrap_count,
            )
            .join(Department, Department.id == CountSubmission.department_id)
            .join(ProductionSite, ProductionSite.id == Department.production_site_id)
            .join(User, User.id == CountSubmission.user_id)
            .join(CountDetail, CountDetail.submission_id == CountSubmission.id)
            .join(Color, Color.id == CountDetail.color_id)
            .order_by(
                CountSubmission.week_iso.desc(),
                ProductionSite.name,
                Department.name,
                Color.sort_order,
                Color.id,
            )
        ).all()

    return [
        {
            "Hafta": row.week_iso,
            "Üretim Yeri": row.site,
            "Bölüm": row.department,
            "Renk": row.color,
            "Boş": row.empty_count,
            "Dolu": row.full_count,
            "Kanban": row.kanban_count,
            "Hurda": row.scrap_count,
            "Gerçekleşen Tonaj": (
                float(row.actual_tonnage) if row.actual_tonnage is not None else None
            ),
            "Durum": row.status,
            "Giren Kullanıcı": row.full_name,
            "Kullanıcı Adı": row.username,
            "Sayım Tarihi": str(row.count_date) if row.count_date else None,
            "Sayım Saati": str(row.count_time) if row.count_time else None,
            "Gönderim Zamanı": _to_tr_iso(row.submitted_at),
            "Submission ID": row.submission_id,
        }
        for row in rows
    ]


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def get_week_export_rows(week_iso: str) -> list[dict[str, Any]]:
    with get_session() as s:
        rows = s.execute(
            select(
                CountSubmission.id.label("submission_id"),
                CountSubmission.week_iso,
                CountSubmission.status,
                CountSubmission.count_date,
                CountSubmission.count_time,
                CountSubmission.actual_tonnage,
                CountSubmission.submitted_at,
                ProductionSite.name.label("site"),
                Department.name.label("department"),
                User.username,
                User.full_name,
                Color.name.label("color"),
                CountDetail.empty_count,
                CountDetail.full_count,
                CountDetail.kanban_count,
                CountDetail.scrap_count,
            )
            .join(Department, Department.id == CountSubmission.department_id)
            .join(ProductionSite, ProductionSite.id == Department.production_site_id)
            .join(User, User.id == CountSubmission.user_id)
            .join(CountDetail, CountDetail.submission_id == CountSubmission.id)
            .join(Color, Color.id == CountDetail.color_id)
            .where(CountSubmission.week_iso == week_iso)
            .order_by(ProductionSite.name, Department.name, Color.sort_order, Color.id)
        ).all()

    return [
        {
            "Hafta": row.week_iso,
            "Üretim Yeri": row.site,
            "Bölüm": row.department,
            "Renk": row.color,
            "Boş": row.empty_count,
            "Dolu": row.full_count,
            "Kanban": row.kanban_count,
            "Hurda": row.scrap_count,
            "Gerçekleşen Tonaj": (
                float(row.actual_tonnage) if row.actual_tonnage is not None else None
            ),
            "Durum": row.status,
            "Giren Kullanıcı": row.full_name,
            "Kullanıcı Adı": row.username,
            "Sayım Tarihi": str(row.count_date) if row.count_date else None,
            "Sayım Saati": str(row.count_time) if row.count_time else None,
            "Gönderim Zamanı": _to_tr_iso(row.submitted_at),
            "Submission ID": row.submission_id,
        }
        for row in rows
    ]
