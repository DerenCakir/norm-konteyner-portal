"""Integration tests for the weekly submission flow.

These exercise the same invariants the Streamlit page enforces, but at
the model + session layer so we don't need a Streamlit runtime:

  - DB-level CHECK / UNIQUE constraints
      kanban_count <= full_count
      empty/full/kanban >= 0
      one (department, week_iso) row at most
      valid status values only
  - Audit log shape on submit / update / override
  - Permission predicate (user_can_submit_for) blocks unauthorized writes
  - The UPSERT pattern used by pages/01_sayim_girisi.py:
      first save creates the row, second save updates the same row,
      old details are replaced not duplicated.
"""

from __future__ import annotations

from datetime import date, time
from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError

from db.models import (
    AuditLog,
    Color,
    CountDetail,
    CountSubmission,
    Department,
    ProductionSite,
    User,
    UserDepartment,
)
from utils.auth import hash_password, user_can_submit_for


# ---------------------------------------------------------------------------
# Fixtures — minimal world: 1 site, 2 depts, 2 colors, 1 user authorized to dept A
# ---------------------------------------------------------------------------
@pytest.fixture
def world(session):
    site = ProductionSite(code="2501", name="Norm Cıvata İzmir")
    session.add(site)
    session.commit()

    dept_a = Department(production_site_id=site.id, name="Atölye A")
    dept_b = Department(production_site_id=site.id, name="Atölye B")
    session.add_all([dept_a, dept_b])
    session.commit()

    blue = Color(name="Mavi", hex_code="#1E40AF", sort_order=1)
    orange = Color(name="Turuncu", hex_code="#EA580C", sort_order=2)
    session.add_all([blue, orange])
    session.commit()

    user = User(
        username="alice",
        password_hash=hash_password("pw12345"),
        full_name="Alice Test",
        role="user",
        is_active=True,
    )
    session.add(user)
    session.commit()

    session.add(UserDepartment(user_id=user.id, department_id=dept_a.id))
    session.commit()

    return {
        "site": site,
        "dept_a": dept_a,
        "dept_b": dept_b,
        "blue": blue,
        "orange": orange,
        "user": user,
    }


def _make_submission(session, world, week="2026-W18", tonnage=10.0):
    sub = CountSubmission(
        department_id=world["dept_a"].id,
        user_id=world["user"].id,
        week_iso=week,
        count_date=date(2026, 5, 1),
        count_time=time(10, 0),
        actual_tonnage=Decimal(str(tonnage)),
        status="submitted",
    )
    session.add(sub)
    session.commit()
    return sub


# ---------------------------------------------------------------------------
# DB-level constraints
# ---------------------------------------------------------------------------
class TestKanbanLeFullConstraint:
    """kanban_count <= full_count must be enforced by the DB, not just the UI."""

    def test_valid_kanban_passes(self, session, world):
        sub = _make_submission(session, world)
        session.add(CountDetail(
            submission_id=sub.id, color_id=world["blue"].id,
            empty_count=2, full_count=10, kanban_count=5,
        ))
        session.commit()  # should succeed

    def test_kanban_greater_than_full_rejected(self, session, world):
        sub = _make_submission(session, world)
        session.add(CountDetail(
            submission_id=sub.id, color_id=world["blue"].id,
            empty_count=0, full_count=3, kanban_count=5,
        ))
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()

    def test_kanban_equal_to_full_passes(self, session, world):
        sub = _make_submission(session, world)
        session.add(CountDetail(
            submission_id=sub.id, color_id=world["blue"].id,
            empty_count=0, full_count=4, kanban_count=4,
        ))
        session.commit()  # equality is allowed


class TestNonNegativeConstraint:
    @pytest.mark.parametrize("empty,full,kanban", [
        (-1, 0, 0),
        (0, -1, 0),
        (0, 0, -1),
    ])
    def test_negative_counts_rejected(self, session, world, empty, full, kanban):
        sub = _make_submission(session, world)
        session.add(CountDetail(
            submission_id=sub.id, color_id=world["blue"].id,
            empty_count=empty, full_count=full, kanban_count=kanban,
        ))
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()


class TestUniquePerDeptWeek:
    """A department can have at most one submission per ISO week."""

    def test_same_dept_same_week_rejects_second_insert(self, session, world):
        _make_submission(session, world, week="2026-W18")
        # Naively trying to insert a second row for the same (dept, week)
        dup = CountSubmission(
            department_id=world["dept_a"].id,
            user_id=world["user"].id,
            week_iso="2026-W18",
            count_date=date(2026, 5, 1),
            actual_tonnage=Decimal("11.0"),
            status="submitted",
        )
        session.add(dup)
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()

    def test_same_dept_different_weeks_allowed(self, session, world):
        _make_submission(session, world, week="2026-W18")
        _make_submission(session, world, week="2026-W19")
        rows = session.query(CountSubmission).filter_by(
            department_id=world["dept_a"].id
        ).all()
        assert len(rows) == 2

    def test_different_depts_same_week_allowed(self, session, world):
        _make_submission(session, world, week="2026-W18")
        sub_b = CountSubmission(
            department_id=world["dept_b"].id,
            user_id=world["user"].id,
            week_iso="2026-W18",
            count_date=date(2026, 5, 1),
            actual_tonnage=Decimal("8.0"),
            status="submitted",
        )
        session.add(sub_b)
        session.commit()  # different dept, no conflict


class TestUniquePerSubmissionColor:
    """Each (submission, color) pair appears at most once in count_details."""

    def test_duplicate_color_rejected(self, session, world):
        sub = _make_submission(session, world)
        session.add(CountDetail(
            submission_id=sub.id, color_id=world["blue"].id,
            empty_count=1, full_count=1, kanban_count=0,
        ))
        session.commit()
        session.add(CountDetail(
            submission_id=sub.id, color_id=world["blue"].id,
            empty_count=2, full_count=2, kanban_count=0,
        ))
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()


class TestValidStatusConstraint:
    @pytest.mark.parametrize("status", ["submitted", "late_submitted", "draft"])
    def test_valid_status_accepted(self, session, world, status):
        sub = CountSubmission(
            department_id=world["dept_a"].id,
            user_id=world["user"].id,
            week_iso="2026-W18",
            count_date=date(2026, 5, 1),
            actual_tonnage=Decimal("10.0"),
            status=status,
        )
        session.add(sub)
        session.commit()  # all three are allowed by CHECK

    def test_invalid_status_rejected(self, session, world):
        sub = CountSubmission(
            department_id=world["dept_a"].id,
            user_id=world["user"].id,
            week_iso="2026-W18",
            count_date=date(2026, 5, 1),
            actual_tonnage=Decimal("10.0"),
            status="approved",  # not in CHECK list
        )
        session.add(sub)
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()


# ---------------------------------------------------------------------------
# UPSERT semantics — the pattern pages/01_sayim_girisi.py uses
# ---------------------------------------------------------------------------
class TestUpsertPattern:
    """Re-submitting the same week updates rather than duplicates."""

    def _submit(self, session, world, *, blue_full, blue_kanban, orange_full=0):
        """Apply the same UPSERT pattern the page uses."""
        existing = (
            session.query(CountSubmission)
            .filter_by(department_id=world["dept_a"].id, week_iso="2026-W18")
            .one_or_none()
        )
        if existing is None:
            sub = CountSubmission(
                department_id=world["dept_a"].id,
                user_id=world["user"].id,
                week_iso="2026-W18",
                count_date=date(2026, 5, 1),
                actual_tonnage=Decimal("10.0"),
                status="submitted",
            )
            session.add(sub)
            session.flush()
        else:
            sub = existing
            for d in list(sub.details):
                session.delete(d)
            session.flush()
        for color, full, kanban in [
            (world["blue"], blue_full, blue_kanban),
            (world["orange"], orange_full, 0),
        ]:
            session.add(CountDetail(
                submission_id=sub.id, color_id=color.id,
                empty_count=0, full_count=full, kanban_count=kanban,
            ))
        session.commit()
        return sub

    def test_second_submit_updates_same_row(self, session, world):
        first = self._submit(session, world, blue_full=10, blue_kanban=4)
        second = self._submit(session, world, blue_full=20, blue_kanban=8)
        assert first.id == second.id

    def test_old_details_are_replaced_not_duplicated(self, session, world):
        self._submit(session, world, blue_full=10, blue_kanban=4)
        self._submit(session, world, blue_full=20, blue_kanban=8, orange_full=5)
        details = (
            session.query(CountDetail)
            .filter_by(submission_id=session.query(CountSubmission).one().id)
            .all()
        )
        # Exactly two rows (blue + orange), not four.
        assert len(details) == 2
        by_color = {d.color_id: d for d in details}
        assert by_color[world["blue"].id].full_count == 20
        assert by_color[world["blue"].id].kanban_count == 8
        assert by_color[world["orange"].id].full_count == 5


# ---------------------------------------------------------------------------
# Audit log
# ---------------------------------------------------------------------------
class TestAuditLogOnSubmit:
    def test_count_submit_audit_records_full_payload(self, session, world):
        sub = _make_submission(session, world)
        session.add(CountDetail(
            submission_id=sub.id, color_id=world["blue"].id,
            empty_count=1, full_count=10, kanban_count=4,
        ))
        # The page also writes a count_submit audit row at submit-time.
        session.add(AuditLog(
            user_id=world["user"].id,
            action="count_submit",
            entity_type="count_submission",
            entity_id=sub.id,
            new_value={
                "week_iso": "2026-W18",
                "department_id": world["dept_a"].id,
                "status": "submitted",
                "details": {str(world["blue"].id): {"empty": 1, "full": 10, "kanban": 4}},
            },
        ))
        session.commit()

        log = session.query(AuditLog).filter_by(action="count_submit").one()
        assert log.entity_id == sub.id
        assert log.new_value["status"] == "submitted"
        assert log.new_value["details"][str(world["blue"].id)]["full"] == 10

    def test_count_update_audit_preserves_old_value(self, session, world):
        """Mirrors the pattern in 01_sayim_girisi.py: count_update saves old payload."""
        sub = _make_submission(session, world)
        old_payload = {
            "week_iso": "2026-W18",
            "status": "submitted",
            "details": {str(world["blue"].id): {"empty": 0, "full": 5, "kanban": 2}},
        }
        new_payload = {
            "week_iso": "2026-W18",
            "status": "submitted",
            "details": {str(world["blue"].id): {"empty": 0, "full": 12, "kanban": 6}},
        }
        session.add(AuditLog(
            user_id=world["user"].id,
            action="count_update",
            entity_type="count_submission",
            entity_id=sub.id,
            old_value=old_payload,
            new_value=new_payload,
        ))
        session.commit()

        log = session.query(AuditLog).filter_by(action="count_update").one()
        assert log.old_value["details"][str(world["blue"].id)]["full"] == 5
        assert log.new_value["details"][str(world["blue"].id)]["full"] == 12


# ---------------------------------------------------------------------------
# Permission gate — user_can_submit_for
# ---------------------------------------------------------------------------
class TestPermissionGate:
    def test_authorized_dept_returns_true(self, session, world):
        assert user_can_submit_for(world["user"].id, world["dept_a"].id, session)

    def test_unauthorized_dept_returns_false(self, session, world):
        # Alice is only linked to dept_a; dept_b is forbidden.
        assert not user_can_submit_for(world["user"].id, world["dept_b"].id, session)

    def test_nonexistent_user_returns_false(self, session, world):
        assert not user_can_submit_for(99999, world["dept_a"].id, session)
