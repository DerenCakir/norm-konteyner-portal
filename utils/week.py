"""
ISO week and submission-window helpers, anchored to Europe/Istanbul.

Submission rules:

    Configured day, open_hour → close_hour (TR)   open    → status='submitted'
    Otherwise (default)                           locked  → users cannot submit
    Late window (admin-opened only)               late    → status='late_submitted'

The on-time window day/hours are stored in the ``submission_schedules``
table (single row, id=1). Admins edit them from the admin panel.
Defaults to Monday 09:00–12:00 if no row exists.

The late window is NOT automatic. An admin inserts a row into the
``late_window_overrides`` table for a specific ``week_iso`` with a
``closes_at`` timestamp. While that row exists and ``now < closes_at``
the late window is considered open for that week.

All time-based predicates accept an optional ``now`` argument so they
can be unit tested with a frozen clock. Naive datetimes are interpreted
as TR-local; aware datetimes are converted to TR.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Literal, Optional

import pytz
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

# Imported lazily-friendly: db.models pulls in db.base only.
from db.models import LateUserWindowOverride, LateWindowOverride, SubmissionSchedule

TR_TZ = pytz.timezone("Europe/Istanbul")

# Default schedule used when DB row absent or no session is available
# (tests, scripts). Production reads the actual values from the
# ``submission_schedules`` table.
DEFAULT_SUBMISSION_DAY = 1            # ISO weekday: Monday
DEFAULT_SUBMISSION_OPEN_HOUR = 9      # 09:00 inclusive
DEFAULT_SUBMISSION_CLOSE_HOUR = 12    # 12:00 exclusive

# Backwards-compatible aliases — older code paths may still import these.
SUBMISSION_DAY = DEFAULT_SUBMISSION_DAY
SUBMISSION_OPEN_HOUR = DEFAULT_SUBMISSION_OPEN_HOUR
SUBMISSION_CLOSE_HOUR = DEFAULT_SUBMISSION_CLOSE_HOUR

# Tuple type: (iso_weekday, open_hour, close_hour)
ScheduleTuple = tuple[int, int, int]
DEFAULT_SCHEDULE: ScheduleTuple = (
    DEFAULT_SUBMISSION_DAY,
    DEFAULT_SUBMISSION_OPEN_HOUR,
    DEFAULT_SUBMISSION_CLOSE_HOUR,
)

_TR_WEEKDAY_NAMES = [
    "Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar",
]


def weekday_name_tr(iso_weekday: int) -> str:
    """Return the Turkish name for an ISO weekday (1=Mon..7=Sun)."""
    if 1 <= iso_weekday <= 7:
        return _TR_WEEKDAY_NAMES[iso_weekday - 1]
    return "?"


def load_schedule(session: Optional[Session]) -> ScheduleTuple:
    """Read the active submission schedule from the database.

    Falls back to ``DEFAULT_SCHEDULE`` when no session is provided
    (test mode) or when the table has no row yet.
    """
    if session is None:
        return DEFAULT_SCHEDULE
    try:
        row = session.execute(
            select(SubmissionSchedule).where(SubmissionSchedule.id == 1)
        ).scalar_one_or_none()
    except SQLAlchemyError:
        return DEFAULT_SCHEDULE
    if row is None:
        return DEFAULT_SCHEDULE
    return (row.day_of_week, row.open_hour, row.close_hour)


def format_schedule_human(schedule: ScheduleTuple) -> str:
    """Render a schedule tuple as ``"Pazartesi 09:00–12:00"``."""
    day, open_h, close_h = schedule
    return f"{weekday_name_tr(day)} {open_h:02d}:00–{close_h:02d}:00"

_TR_MONTHS = [
    "Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran",
    "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık",
]

SubmissionStatus = Literal["open", "late", "locked"]


# ---------------------------------------------------------------------------
# Time helpers
# ---------------------------------------------------------------------------
def now_tr(now: Optional[datetime] = None) -> datetime:
    """Return a TR-aware datetime.

    - None             → current TR time
    - naive datetime   → assumed TR-local, attach TR tz via pytz.localize
    - aware datetime   → converted to TR

    Always returns timezone-aware, in Europe/Istanbul.
    """
    if now is None:
        return datetime.now(TR_TZ)
    if now.tzinfo is None:
        return TR_TZ.localize(now)
    return now.astimezone(TR_TZ)


# ---------------------------------------------------------------------------
# ISO week helpers
# ---------------------------------------------------------------------------
def week_iso_from_date(d: date) -> str:
    """Return the ISO week code (e.g. ``2026-W18``) for the given date."""
    iso = d.isocalendar()
    return f"{iso[0]}-W{iso[1]:02d}"


def current_week_iso(now: Optional[datetime] = None) -> str:
    """Return the ISO week code for *now* (default: current TR time)."""
    return week_iso_from_date(now_tr(now).date())


def week_iso_to_dates(week_iso: str) -> tuple[date, date]:
    """Parse ``YYYY-Www`` into (Monday date, Sunday date)."""
    try:
        year_str, week_str = week_iso.split("-W")
        year = int(year_str)
        week = int(week_str)
    except (ValueError, AttributeError) as exc:
        raise ValueError(f"Invalid ISO week code: {week_iso!r}") from exc

    monday = date.fromisocalendar(year, week, 1)
    sunday = monday + timedelta(days=6)
    return monday, sunday


# ---------------------------------------------------------------------------
# Submission window predicates
# ---------------------------------------------------------------------------
def is_submission_open(
    now: Optional[datetime] = None,
    schedule: Optional[ScheduleTuple] = None,
) -> bool:
    """True if the regular on-time submission window is active.

    The window is configurable via ``submission_schedules`` (one row).
    When no schedule is passed, the module-level default is used —
    Monday 09:00 (inclusive) → 12:00 (exclusive), TR.
    """
    day, open_h, close_h = schedule if schedule is not None else DEFAULT_SCHEDULE
    n = now_tr(now)
    if n.isoweekday() != day:
        return False
    return open_h <= n.hour < close_h


def is_late_window_open(
    week_iso: str,
    session: Session,
    now: Optional[datetime] = None,
    user_id: Optional[int] = None,
    department_id: Optional[int] = None,
) -> bool:
    """True if an admin has opened a late window for *week_iso* and it
    has not yet expired.

    Looks up ``late_window_overrides`` by ``week_iso``. If no row
    exists, the late window is closed (default).
    """
    override = session.execute(
        select(LateWindowOverride).where(LateWindowOverride.week_iso == week_iso)
    ).scalar_one_or_none()
    if override is None:
        global_open = False
    else:
        global_open = now_tr(now) < now_tr(override.closes_at)

    if global_open:
        return True

    if user_id is None:
        return False

    query = select(LateUserWindowOverride).where(
        LateUserWindowOverride.week_iso == week_iso,
        LateUserWindowOverride.user_id == user_id,
        LateUserWindowOverride.closes_at > now_tr(now),
    )
    if department_id is not None:
        query = query.where(
            (LateUserWindowOverride.department_id.is_(None))
            | (LateUserWindowOverride.department_id == department_id)
        )
    try:
        override_user = session.execute(
            query.order_by(LateUserWindowOverride.closes_at.desc())
        ).scalars().first()
    except SQLAlchemyError:
        return False
    return override_user is not None


def get_submission_status(
    week_iso: str,
    session: Session,
    now: Optional[datetime] = None,
    user_id: Optional[int] = None,
    department_id: Optional[int] = None,
) -> SubmissionStatus:
    """Resolve the current submission status for a given week.

    Order of checks:
      1. ``open``   — only if the regular window is active *and* the
                      requested week is the current TR week.
      2. ``late``   — admin-opened late window for this specific week.
      3. ``locked`` — otherwise (default, applies to past/future weeks
                      and to the current week outside the Friday slot).
    """
    schedule = load_schedule(session)
    if is_submission_open(now, schedule) and week_iso == current_week_iso(now):
        return "open"
    if is_late_window_open(week_iso, session, now, user_id=user_id, department_id=department_id):
        return "late"
    return "locked"


# ---------------------------------------------------------------------------
# Human-readable formatting
# ---------------------------------------------------------------------------
def format_week_human(week_iso: str) -> str:
    """Render an ISO week code as a Turkish date range.

    Examples:
        ``2026-W17`` → ``20-26 Nisan 2026``                (same month)
        ``2026-W18`` → ``27 Nisan - 03 Mayıs 2026``        (cross-month)
        ``2025-W53`` → ``29 Aralık 2025 - 04 Ocak 2026``   (cross-year)
    """
    start, end = week_iso_to_dates(week_iso)

    if start.year == end.year and start.month == end.month:
        return f"{start.day:02d}-{end.day:02d} {_TR_MONTHS[start.month - 1]} {start.year}"

    if start.year == end.year:
        return (
            f"{start.day:02d} {_TR_MONTHS[start.month - 1]} - "
            f"{end.day:02d} {_TR_MONTHS[end.month - 1]} {start.year}"
        )

    return (
        f"{start.day:02d} {_TR_MONTHS[start.month - 1]} {start.year} - "
        f"{end.day:02d} {_TR_MONTHS[end.month - 1]} {end.year}"
    )
