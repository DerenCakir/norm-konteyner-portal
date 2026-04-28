"""Unit tests for utils.auth (pure / DB-backed layer).

Streamlit-bound functions (login_user, logout_user, require_auth, ...)
are not covered here — they need a Streamlit runtime and will be
tested through the actual app pages.
"""

from __future__ import annotations

import pytest

from db.models import AuditLog, Department, ProductionSite, User, UserDepartment
from utils.auth import (
    authenticate,
    get_user_departments,
    hash_password,
    user_can_submit_for,
    verify_password,
)


# ---------------------------------------------------------------------------
# hash_password / verify_password
# ---------------------------------------------------------------------------
class TestPasswordHashing:
    def test_roundtrip(self):
        h = hash_password("secret123")
        assert verify_password("secret123", h) is True

    def test_wrong_password_returns_false(self):
        h = hash_password("secret123")
        assert verify_password("wrong-password", h) is False

    @pytest.mark.parametrize("bad_hash", [
        "",                         # empty
        "not-a-real-hash",          # malformed
        "$2b$12$tooShort",          # bcrypt-shaped but truncated
        "plain text password",      # wrong format entirely
    ])
    def test_corrupt_hash_returns_false(self, bad_hash):
        assert verify_password("anything", bad_hash) is False

    def test_empty_plain_returns_false(self):
        h = hash_password("real")
        assert verify_password("", h) is False

    def test_hash_is_not_plaintext(self):
        h = hash_password("secret123")
        assert "secret123" not in h
        assert h.startswith("$2")  # bcrypt prefix


# ---------------------------------------------------------------------------
# authenticate — DB-backed
# ---------------------------------------------------------------------------
def _make_user(session, *, username="alice", password="pw12345",
               role="user", active=True) -> User:
    user = User(
        username=username,
        password_hash=hash_password(password),
        full_name=f"{username.title()} Test",
        role=role,
        is_active=active,
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


class TestAuthenticate:
    def test_success_returns_user(self, session):
        _make_user(session)
        result = authenticate("alice", "pw12345", session)
        assert result is not None
        assert result.username == "alice"

    def test_success_updates_last_login(self, session):
        u = _make_user(session)
        assert u.last_login_at is None
        authenticate("alice", "pw12345", session)
        session.refresh(u)
        assert u.last_login_at is not None

    def test_success_writes_audit(self, session):
        _make_user(session)
        authenticate("alice", "pw12345", session)
        logs = session.query(AuditLog).filter_by(action="login_success").all()
        assert len(logs) == 1
        assert logs[0].new_value == {"username": "alice"}

    def test_wrong_password_returns_none(self, session):
        _make_user(session)
        assert authenticate("alice", "wrong", session) is None

    def test_wrong_password_writes_failure_audit(self, session):
        u = _make_user(session)
        authenticate("alice", "wrong", session)
        logs = session.query(AuditLog).filter_by(action="login_failed").all()
        assert len(logs) == 1
        assert logs[0].user_id == u.id
        assert logs[0].new_value["reason"] == "bad_password"

    def test_inactive_user_returns_none_even_with_correct_password(self, session):
        _make_user(session, username="bob", password="pw", active=False)
        assert authenticate("bob", "pw", session) is None

    def test_inactive_user_audit_records_reason(self, session):
        _make_user(session, username="bob", password="pw", active=False)
        authenticate("bob", "pw", session)
        log = session.query(AuditLog).filter_by(action="login_failed").one()
        assert log.new_value["reason"] == "inactive"

    def test_unknown_user_returns_none(self, session):
        assert authenticate("ghost", "any", session) is None

    def test_unknown_user_audit_has_null_user_id(self, session):
        authenticate("ghost", "any", session)
        log = session.query(AuditLog).filter_by(action="login_failed").one()
        assert log.user_id is None
        assert log.new_value["username_attempted"] == "ghost"
        assert log.new_value["reason"] == "unknown_user"


# ---------------------------------------------------------------------------
# Authorization helpers
# ---------------------------------------------------------------------------
@pytest.fixture
def two_depts(session):
    site = ProductionSite(code="2501", name="Norm Cıvata İzmir")
    session.add(site)
    session.commit()
    d1 = Department(production_site_id=site.id, name="Atölye A")
    d2 = Department(production_site_id=site.id, name="Atölye B")
    session.add_all([d1, d2])
    session.commit()
    session.refresh(d1)
    session.refresh(d2)
    return d1, d2


class TestUserCanSubmitFor:
    def test_authorized_returns_true(self, session, two_depts):
        d1, _ = two_depts
        u = _make_user(session)
        session.add(UserDepartment(user_id=u.id, department_id=d1.id))
        session.commit()
        assert user_can_submit_for(u.id, d1.id, session) is True

    def test_unauthorized_returns_false(self, session, two_depts):
        d1, d2 = two_depts
        u = _make_user(session)
        session.add(UserDepartment(user_id=u.id, department_id=d1.id))
        session.commit()
        assert user_can_submit_for(u.id, d2.id, session) is False


class TestGetUserDepartments:
    def test_returns_only_linked_active_depts_sorted(self, session, two_depts):
        d1, d2 = two_depts
        u = _make_user(session)
        # link to both, then deactivate d1
        session.add_all([
            UserDepartment(user_id=u.id, department_id=d1.id),
            UserDepartment(user_id=u.id, department_id=d2.id),
        ])
        d1.is_active = False
        session.commit()

        depts = get_user_departments(u.id, session)
        names = [d.name for d in depts]
        assert names == ["Atölye B"]

    def test_no_links_returns_empty(self, session):
        u = _make_user(session)
        assert get_user_departments(u.id, session) == []
