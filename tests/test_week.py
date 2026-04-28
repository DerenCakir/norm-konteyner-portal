"""Unit tests for utils.week.

These tests are pure: no DB, no clock dependency. Where the production
code talks to the database (``is_late_window_open``), we monkeypatch it.
"""

from __future__ import annotations

from datetime import date, datetime

import pytest
import pytz

from utils import week as week_mod
from utils.week import (
    TR_TZ,
    current_week_iso,
    format_week_human,
    get_submission_status,
    is_submission_open,
    now_tr,
    week_iso_from_date,
    week_iso_to_dates,
)


# ---------------------------------------------------------------------------
# now_tr
# ---------------------------------------------------------------------------
class TestNowTr:
    def test_none_returns_aware_tr(self):
        result = now_tr()
        assert result.tzinfo is not None
        # tzname check via utcoffset for stability across pytz versions
        offset = result.utcoffset()
        # TR is UTC+3 year-round (no DST since 2016)
        assert offset.total_seconds() == 3 * 3600

    def test_naive_datetime_attached_as_tr_no_lmt_bug(self):
        # Friday 2026-05-01 11:00 TR-local
        naive = datetime(2026, 5, 1, 11, 0)
        result = now_tr(naive)
        assert result.hour == 11
        assert result.utcoffset().total_seconds() == 3 * 3600  # +03:00, not LMT +01:57

    def test_aware_utc_converted_to_tr(self):
        utc_dt = datetime(2026, 5, 1, 8, 0, tzinfo=pytz.UTC)
        result = now_tr(utc_dt)
        assert result.hour == 11  # UTC 08:00 == TR 11:00
        assert result.utcoffset().total_seconds() == 3 * 3600


# ---------------------------------------------------------------------------
# is_submission_open  (naive TR datetimes)
# ---------------------------------------------------------------------------
class TestIsSubmissionOpenLocal:
    @pytest.mark.parametrize("dt, expected", [
        # 2026-05-01 is a Friday
        (datetime(2026, 5, 1, 11, 0),  True),   # Friday 11:00
        (datetime(2026, 5, 1, 9, 0),   True),   # Friday 09:00 (lower bound, inclusive)
        (datetime(2026, 5, 1, 11, 59), True),   # Friday 11:59
        (datetime(2026, 5, 1, 12, 0),  False),  # Friday 12:00 (upper bound, exclusive)
        (datetime(2026, 5, 1, 8, 59),  False),  # Friday 08:59
        # 2026-04-30 is Thursday, 2026-05-02 is Saturday
        (datetime(2026, 4, 30, 11, 0), False),  # Thursday 11:00
        (datetime(2026, 5, 2, 11, 0),  False),  # Saturday 11:00
    ])
    def test_window(self, dt, expected):
        assert is_submission_open(dt) is expected


# ---------------------------------------------------------------------------
# is_submission_open  (timezone-aware UTC inputs)
# ---------------------------------------------------------------------------
class TestIsSubmissionOpenUtc:
    def test_utc_friday_06_is_tr_09_open(self):
        utc_dt = datetime(2026, 5, 1, 6, 0, tzinfo=pytz.UTC)
        assert is_submission_open(utc_dt) is True

    def test_utc_friday_09_is_tr_12_closed(self):
        utc_dt = datetime(2026, 5, 1, 9, 0, tzinfo=pytz.UTC)
        assert is_submission_open(utc_dt) is False


# ---------------------------------------------------------------------------
# current_week_iso
# ---------------------------------------------------------------------------
class TestCurrentWeekIso:
    @pytest.mark.parametrize("dt, expected", [
        (datetime(2026, 4, 27, 9, 0),  "2026-W18"),  # Monday
        (datetime(2026, 5, 1, 11, 0),  "2026-W18"),  # Friday, same week
        (datetime(2026, 5, 4, 9, 0),   "2026-W19"),  # Following Monday
    ])
    def test_iso_week_boundary(self, dt, expected):
        assert current_week_iso(dt) == expected


# ---------------------------------------------------------------------------
# week_iso_from_date  (sanity)
# ---------------------------------------------------------------------------
class TestWeekIsoFromDate:
    def test_monday_and_friday_same_week(self):
        assert week_iso_from_date(date(2026, 4, 27)) == "2026-W18"
        assert week_iso_from_date(date(2026, 5, 1)) == "2026-W18"


# ---------------------------------------------------------------------------
# week_iso_to_dates
# ---------------------------------------------------------------------------
class TestWeekIsoToDates:
    def test_normal_week(self):
        start, end = week_iso_to_dates("2026-W18")
        assert start == date(2026, 4, 27)
        assert end == date(2026, 5, 3)

    def test_cross_year_week(self):
        # 2020 has 53 ISO weeks (started on Wednesday + leap year).
        start, end = week_iso_to_dates("2020-W53")
        assert start == date(2020, 12, 28)
        assert end == date(2021, 1, 3)

    @pytest.mark.parametrize("bad", ["2026-W99", "", "abc", "2026W18", "2026-18"])
    def test_invalid_inputs_raise(self, bad):
        with pytest.raises(ValueError):
            week_iso_to_dates(bad)


# ---------------------------------------------------------------------------
# format_week_human
# ---------------------------------------------------------------------------
class TestFormatWeekHuman:
    def test_same_month(self):
        # 2026-W17: 2026-04-20 .. 2026-04-26
        assert format_week_human("2026-W17") == "20-26 Nisan 2026"

    def test_cross_month_same_year(self):
        # 2026-W18: 2026-04-27 .. 2026-05-03
        assert format_week_human("2026-W18") == "27 Nisan - 03 Mayıs 2026"

    def test_cross_year(self):
        # 2020-W53: 2020-12-28 .. 2021-01-03
        assert format_week_human("2020-W53") == "28 Aralık 2020 - 03 Ocak 2021"


# ---------------------------------------------------------------------------
# get_submission_status — monkeypatch is_late_window_open
# ---------------------------------------------------------------------------
class TestGetSubmissionStatus:
    """Tests focus on the decision logic; DB lookup is stubbed."""

    @pytest.fixture
    def stub_late_closed(self, monkeypatch):
        monkeypatch.setattr(
            week_mod, "is_late_window_open",
            lambda week_iso, session, now=None: False,
        )

    @pytest.fixture
    def stub_late_open(self, monkeypatch):
        monkeypatch.setattr(
            week_mod, "is_late_window_open",
            lambda week_iso, session, now=None: True,
        )

    # ----- late closed -----
    def test_open_during_friday_for_current_week(self, stub_late_closed):
        now = datetime(2026, 5, 1, 11, 0)  # Friday 11:00, week = 2026-W18
        assert get_submission_status("2026-W18", session=None, now=now) == "open"

    def test_locked_for_past_week_even_in_window(self, stub_late_closed):
        now = datetime(2026, 5, 1, 11, 0)  # Friday 11:00
        assert get_submission_status("2026-W17", session=None, now=now) == "locked"

    def test_locked_outside_friday_window(self, stub_late_closed):
        now = datetime(2026, 5, 1, 13, 0)  # Friday 13:00, after cutoff
        assert get_submission_status("2026-W18", session=None, now=now) == "locked"

    def test_locked_on_monday(self, stub_late_closed):
        now = datetime(2026, 4, 27, 11, 0)  # Monday
        assert get_submission_status("2026-W18", session=None, now=now) == "locked"

    # ----- late open -----
    def test_open_takes_precedence_over_late(self, stub_late_open):
        now = datetime(2026, 5, 1, 11, 0)  # in regular window
        assert get_submission_status("2026-W18", session=None, now=now) == "open"

    def test_late_when_outside_window_but_override_active(self, stub_late_open):
        now = datetime(2026, 5, 1, 13, 0)  # Friday 13:00, regular closed
        assert get_submission_status("2026-W18", session=None, now=now) == "late"
