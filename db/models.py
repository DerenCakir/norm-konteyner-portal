"""
SQLAlchemy ORM models for the Norm container tracking portal.

Mirrors sql/schema.sql one-to-one. Modern SQLAlchemy 2.0 style is used
throughout (Mapped + mapped_column). Database-level CHECK / UNIQUE
constraints are also declared here so that schema reflection from the
ORM side stays accurate, but the source of truth is the schema running
in Supabase.

Imports only Base — never engine or SessionLocal — so that this module
can be loaded without DATABASE_URL being configured.
"""

from __future__ import annotations

from datetime import date, datetime, time
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    JSON,
    CheckConstraint,
    Date,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Time,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB

# JSONB on Postgres, plain JSON on SQLite (used by tests).
# Production schema in Supabase remains JSONB; this only affects the
# in-memory SQLite engine the test suite spins up.
_JSON_VARIANT = JSONB().with_variant(JSON(), "sqlite")
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base import Base


# ---------------------------------------------------------------------------
# 1. PRODUCTION SITES
# ---------------------------------------------------------------------------
class ProductionSite(Base):
    """Top-level facility. 11 fixed sites, never managed from the UI."""

    __tablename__ = "production_sites"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(10), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    is_active: Mapped[bool] = mapped_column(default=True, server_default="true")
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    departments: Mapped[list["Department"]] = relationship(
        back_populates="production_site",
        cascade="all",
    )

    def __repr__(self) -> str:
        return f"<ProductionSite id={self.id} code={self.code!r} name={self.name!r}>"


# ---------------------------------------------------------------------------
# 2. DEPARTMENTS
# ---------------------------------------------------------------------------
class Department(Base):
    """A department belongs to one production site. Unique per (site, name)."""

    __tablename__ = "departments"
    __table_args__ = (
        UniqueConstraint("production_site_id", "name", name="departments_site_name_key"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    production_site_id: Mapped[int] = mapped_column(
        ForeignKey("production_sites.id"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    weekly_tonnage_target: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2))
    is_active: Mapped[bool] = mapped_column(default=True, server_default="true", index=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now()
    )

    production_site: Mapped["ProductionSite"] = relationship(back_populates="departments")
    user_links: Mapped[list["UserDepartment"]] = relationship(
        back_populates="department", cascade="all, delete-orphan"
    )
    submissions: Mapped[list["CountSubmission"]] = relationship(
        back_populates="department"
    )

    def __repr__(self) -> str:
        return f"<Department id={self.id} name={self.name!r} site_id={self.production_site_id}>"


# ---------------------------------------------------------------------------
# 3. COLORS
# ---------------------------------------------------------------------------
class Color(Base):
    """Container color/category. Includes 'MS Vida' as a regular color."""

    __tablename__ = "colors"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    hex_code: Mapped[Optional[str]] = mapped_column(String(7))
    sort_order: Mapped[int] = mapped_column(default=0, server_default="0")
    is_active: Mapped[bool] = mapped_column(default=True, server_default="true", index=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    details: Mapped[list["CountDetail"]] = relationship(back_populates="color")

    def __repr__(self) -> str:
        return f"<Color id={self.id} name={self.name!r} active={self.is_active}>"


# ---------------------------------------------------------------------------
# 4. USERS
# ---------------------------------------------------------------------------
class User(Base):
    """Application user. Created only by an admin; passwords stored as bcrypt."""

    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("role IN ('user', 'admin')", name="valid_role"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(100), nullable=False)
    email: Mapped[Optional[str]] = mapped_column(String(150))
    role: Mapped[str] = mapped_column(String(20), nullable=False, default="user", server_default="user")
    is_active: Mapped[bool] = mapped_column(default=True, server_default="true")
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    last_login_at: Mapped[Optional[datetime]] = mapped_column()

    department_links: Mapped[list["UserDepartment"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    submissions: Mapped[list["CountSubmission"]] = relationship(back_populates="user")
    audit_entries: Mapped[list["AuditLog"]] = relationship(back_populates="user")
    late_overrides_opened: Mapped[list["LateWindowOverride"]] = relationship(
        back_populates="opened_by_user"
    )
    late_user_overrides: Mapped[list["LateUserWindowOverride"]] = relationship(
        foreign_keys="LateUserWindowOverride.user_id",
        back_populates="user",
    )
    late_user_overrides_opened: Mapped[list["LateUserWindowOverride"]] = relationship(
        foreign_keys="LateUserWindowOverride.opened_by",
        back_populates="opened_by_user",
    )

    def __repr__(self) -> str:
        return f"<User id={self.id} username={self.username!r} role={self.role!r}>"


# ---------------------------------------------------------------------------
# 5. USER ↔ DEPARTMENT (association)
# ---------------------------------------------------------------------------
class UserDepartment(Base):
    """Composite-PK link between a user and a department they may submit for."""

    __tablename__ = "user_departments"

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True, index=True
    )
    department_id: Mapped[int] = mapped_column(
        ForeignKey("departments.id", ondelete="CASCADE"), primary_key=True
    )
    assigned_at: Mapped[datetime] = mapped_column(server_default=func.now())

    user: Mapped["User"] = relationship(back_populates="department_links")
    department: Mapped["Department"] = relationship(back_populates="user_links")

    def __repr__(self) -> str:
        return f"<UserDepartment user_id={self.user_id} dept_id={self.department_id}>"


# ---------------------------------------------------------------------------
# 6. COUNT SUBMISSIONS
# ---------------------------------------------------------------------------
class CountSubmission(Base):
    """One submission per (department, ISO week)."""

    __tablename__ = "count_submissions"
    __table_args__ = (
        UniqueConstraint("department_id", "week_iso", name="count_submissions_dept_week_key"),
        CheckConstraint(
            "status IN ('draft', 'submitted', 'late_submitted')",
            name="valid_status",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    department_id: Mapped[int] = mapped_column(
        ForeignKey("departments.id"), nullable=False
    )
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    week_iso: Mapped[str] = mapped_column(String(8), nullable=False, index=True)
    count_date: Mapped[date] = mapped_column(Date, nullable=False)
    count_time: Mapped[time] = mapped_column(Time, nullable=False)
    actual_tonnage: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2))
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="draft", server_default="draft", index=True
    )
    submitted_at: Mapped[Optional[datetime]] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now()
    )

    department: Mapped["Department"] = relationship(back_populates="submissions")
    user: Mapped["User"] = relationship(back_populates="submissions")
    details: Mapped[list["CountDetail"]] = relationship(
        back_populates="submission", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return (
            f"<CountSubmission id={self.id} dept_id={self.department_id} "
            f"week={self.week_iso!r} status={self.status!r}>"
        )


# ---------------------------------------------------------------------------
# 7. COUNT DETAILS (per-color row inside a submission)
# ---------------------------------------------------------------------------
class CountDetail(Base):
    """Per-color counts for one submission. Kanban is a subset of full."""

    __tablename__ = "count_details"
    __table_args__ = (
        UniqueConstraint("submission_id", "color_id", name="count_details_sub_color_key"),
        CheckConstraint(
            "empty_count >= 0 AND full_count >= 0 AND kanban_count >= 0",
            name="non_negative",
        ),
        CheckConstraint("kanban_count <= full_count", name="kanban_le_full"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    submission_id: Mapped[int] = mapped_column(
        ForeignKey("count_submissions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    color_id: Mapped[int] = mapped_column(
        ForeignKey("colors.id"), nullable=False, index=True
    )
    empty_count: Mapped[int] = mapped_column(default=0, server_default="0")
    full_count: Mapped[int] = mapped_column(default=0, server_default="0")
    kanban_count: Mapped[int] = mapped_column(default=0, server_default="0")

    submission: Mapped["CountSubmission"] = relationship(back_populates="details")
    color: Mapped["Color"] = relationship(back_populates="details")

    def __repr__(self) -> str:
        return (
            f"<CountDetail id={self.id} sub_id={self.submission_id} "
            f"color_id={self.color_id} empty={self.empty_count} "
            f"full={self.full_count} kanban={self.kanban_count}>"
        )


# ---------------------------------------------------------------------------
# 8. LATE WINDOW OVERRIDES
# ---------------------------------------------------------------------------
class LateWindowOverride(Base):
    """Admin-opened late submission window for a specific ISO week.

    Default state for any week is *closed*. An admin inserts a row here
    to allow late submissions until ``closes_at``. Presence of the row
    plus ``now < closes_at`` means the late window is open.
    """

    __tablename__ = "late_window_overrides"

    week_iso: Mapped[str] = mapped_column(String(8), primary_key=True)
    opened_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    opened_at: Mapped[datetime] = mapped_column(server_default=func.now())
    closes_at: Mapped[datetime] = mapped_column(nullable=False, index=True)
    reason: Mapped[Optional[str]] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    opened_by_user: Mapped["User"] = relationship(back_populates="late_overrides_opened")

    def __repr__(self) -> str:
        return (
            f"<LateWindowOverride week={self.week_iso!r} "
            f"opened_by={self.opened_by} closes_at={self.closes_at}>"
        )


class LateUserWindowOverride(Base):
    """Admin-opened late submission window scoped to one user.

    If ``department_id`` is NULL, the user may submit for any department they
    are already authorized for in the selected week. If ``department_id`` is
    set, the late window applies only to that department.
    """

    __tablename__ = "late_user_window_overrides"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    week_iso: Mapped[str] = mapped_column(String(8), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    department_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("departments.id"), index=True
    )
    opened_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    opened_at: Mapped[datetime] = mapped_column(server_default=func.now())
    closes_at: Mapped[datetime] = mapped_column(nullable=False, index=True)
    reason: Mapped[Optional[str]] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    user: Mapped["User"] = relationship(
        foreign_keys=[user_id],
        back_populates="late_user_overrides",
    )
    opened_by_user: Mapped["User"] = relationship(
        foreign_keys=[opened_by],
        back_populates="late_user_overrides_opened",
    )
    department: Mapped[Optional["Department"]] = relationship()

    def __repr__(self) -> str:
        return (
            f"<LateUserWindowOverride week={self.week_iso!r} user_id={self.user_id} "
            f"department_id={self.department_id} closes_at={self.closes_at}>"
        )


# ---------------------------------------------------------------------------
# 8b. SUBMISSION SCHEDULE (admin-configurable on-time window)
# ---------------------------------------------------------------------------
class SubmissionSchedule(Base):
    """Single-row table that controls when the on-time submission window
    opens each week. Admin edits day_of_week (1=Mon..7=Sun) and the
    inclusive open/exclusive close hours. Defaults to Monday 09:00–12:00
    if no row exists.
    """

    __tablename__ = "submission_schedules"
    __table_args__ = (
        CheckConstraint("day_of_week BETWEEN 1 AND 7", name="valid_day_of_week"),
        CheckConstraint("open_hour BETWEEN 0 AND 23", name="valid_open_hour"),
        CheckConstraint("close_hour BETWEEN 1 AND 24", name="valid_close_hour"),
        CheckConstraint("close_hour > open_hour", name="close_after_open"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    day_of_week: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )
    open_hour: Mapped[int] = mapped_column(
        Integer, nullable=False, default=9, server_default="9"
    )
    close_hour: Mapped[int] = mapped_column(
        Integer, nullable=False, default=12, server_default="12"
    )
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now()
    )
    updated_by: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"))

    def __repr__(self) -> str:
        return (
            f"<SubmissionSchedule id={self.id} day={self.day_of_week} "
            f"open={self.open_hour} close={self.close_hour}>"
        )


# ---------------------------------------------------------------------------
# 9. AUDIT LOG
# ---------------------------------------------------------------------------
class AuditLog(Base):
    """Append-only audit trail for security-relevant actions."""

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id"), index=True
    )
    action: Mapped[str] = mapped_column(String(50), nullable=False)
    entity_type: Mapped[Optional[str]] = mapped_column(String(50))
    entity_id: Mapped[Optional[int]] = mapped_column(Integer)
    old_value: Mapped[Optional[dict]] = mapped_column(_JSON_VARIANT)
    new_value: Mapped[Optional[dict]] = mapped_column(_JSON_VARIANT)
    ip_address: Mapped[Optional[str]] = mapped_column(String(45))
    timestamp: Mapped[datetime] = mapped_column(server_default=func.now(), index=True)

    user: Mapped[Optional["User"]] = relationship(back_populates="audit_entries")

    def __repr__(self) -> str:
        return (
            f"<AuditLog id={self.id} user_id={self.user_id} "
            f"action={self.action!r} entity={self.entity_type}:{self.entity_id}>"
        )
