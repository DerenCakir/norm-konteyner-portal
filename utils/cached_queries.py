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


CACHE_TTL_SECONDS = 60


def clear_cached_queries() -> None:
    """Clear cached read models after admin mutations."""
    get_available_weeks.clear()
    get_active_sites_departments.clear()
    get_active_colors.clear()
    get_week_submissions_with_users.clear()
    get_week_count_details.clear()
    get_department_users.clear()


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
            "submitted_at": sub.submitted_at.isoformat() if sub.submitted_at else None,
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
