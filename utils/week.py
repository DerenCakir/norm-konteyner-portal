"""
ISO week and submission-window helpers, anchored to Europe/Istanbul.

Submission rules (per CLAUDE.md):

    Friday 09:00 → 12:00 (TR)        open       → status='submitted'
    Otherwise (default)              locked     → users cannot submit
    Late window (admin-opened only)  late       → status='late_submitted'

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
from sqlalchemy.orm import Session

# Imported lazily-friendly: db.models pulls in db.base only.
from db.models import LateWindowOverride

TR_TZ = pytz.timezone("Europe/Istanbul")

# Submission window — narrow on-time slot.
SUBMISSION_DAY = 5            # ISO weekday: Friday
SUBMISSION_OPEN_HOUR = 9      # 09:00 inclusive
SUBMISSION_CLOSE_HOUR = 12    # 12:00 exclusive

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
def is_submission_open(now: Optional[datetime] = None) -> bool:
    """True if the regular on-time submission window is active.

    Window: Friday 09:00 (inclusive) → Friday 12:00 (exclusive), TR.
    """
    n = now_tr(now)
    if n.isoweekday() != SUBMISSION_DAY:
        return False
    return SUBMISSION_OPEN_HOUR <= n.hour < SUBMISSION_CLOSE_HOUR


def is_late_window_open(
    week_iso: str,
    session: Session,
    now: Optional[datetime] = None,
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
        return False
    return now_tr(now) < now_tr(override.closes_at)


def get_submission_status(
    week_iso: str,
    session: Session,
    now: Optional[datetime] = None,
) -> SubmissionStatus:
    """Resolve the current submission status for a given week.

    Order of checks:
      1. ``open``   — only if the regular window is active *and* the
                      requested week is the current TR week.
      2. ``late``   — admin-opened late window for this specific week.
      3. ``locked`` — otherwise (default, applies to past/future weeks
                      and to the current week outside the Friday slot).
    """
    if is_submission_open(now) and week_iso == current_week_iso(now):
        return "open"
    if is_late_window_open(week_iso, session, now):
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
