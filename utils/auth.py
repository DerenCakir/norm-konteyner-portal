"""
Authentication primitives for the portal.

Two layers:

1. **Pure functions** (no Streamlit dependency, easily unit-tested):
       - ``hash_password`` / ``verify_password`` — bcrypt wrapper
       - ``authenticate``                       — DB-backed credential check
       - ``user_can_submit_for``                — permission predicate
       - ``get_user_departments``               — list of authorized depts

2. **Streamlit-bound functions** (require ``st.session_state``):
       - ``login_user`` / ``logout_user``
       - ``is_authenticated`` / ``get_current_user``
       - ``require_auth`` / ``require_admin``

Audit log conventions:
    login_success → user_id set, new_value={"username": ...}
    login_failed  → user_id NULL, new_value={"username_attempted": ...,
                                              "reason": "..." (optional)}
    logout        → user_id set, new_value={"username": ...}
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from base64 import urlsafe_b64decode, urlsafe_b64encode
from typing import Optional

import bcrypt
import streamlit as st
from sqlalchemy import select
from sqlalchemy.orm import Session

from config.settings import get_settings
from db.connection import get_session
from db.models import AuditLog, Department, User, UserDepartment
from utils.week import now_tr


# ---------------------------------------------------------------------------
# Signed-token session restore (via URL query param)
# ---------------------------------------------------------------------------
# When Streamlit's WebSocket reconnects (proxy hiccup, mobile network blip,
# Railway brief restart) it can hand the browser a fresh server-side session
# with empty session_state. That used to bounce the user back to the login
# screen mid-task. We avoid that by writing a short-lived signed token to a
# URL query parameter on login and reading it back on every page entry.
# Token format: base64url(json({uid, exp})) + "." + hex(hmac-sha256)
_QUERY_KEY = "s"
_TOKEN_TTL = 4 * 3600  # 4 hours — long enough for a Friday submission session


def _sign(payload: str, secret: str) -> str:
    return hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()


def _make_token(user_id: int) -> str:
    settings = get_settings()
    payload = {"uid": user_id, "exp": int(time.time()) + _TOKEN_TTL}
    payload_b64 = urlsafe_b64encode(
        json.dumps(payload, separators=(",", ":")).encode()
    ).decode().rstrip("=")
    return f"{payload_b64}.{_sign(payload_b64, settings.secret_key)}"


def _verify_token(token: str) -> Optional[int]:
    if not token or "." not in token:
        return None
    try:
        payload_b64, sig = token.split(".", 1)
        secret = get_settings().secret_key
        if not hmac.compare_digest(sig, _sign(payload_b64, secret)):
            return None
        padded = payload_b64 + "=" * (-len(payload_b64) % 4)
        payload = json.loads(urlsafe_b64decode(padded).decode())
        if int(payload.get("exp", 0)) < int(time.time()):
            return None
        return int(payload["uid"])
    except Exception:
        return None


def _drop_query_token() -> None:
    try:
        if _QUERY_KEY in st.query_params:
            del st.query_params[_QUERY_KEY]
    except Exception:
        pass


def restore_session_from_query() -> None:
    """Keep auth state and the URL token in sync.

    - If session_state has a user but the URL token is missing or stale
      (Streamlit's navigation can drop query params on page change), write
      a fresh token so the next F5 / WebSocket reconnect can restore.
    - If session_state is empty but the URL has a valid token, rehydrate
      session_state from the token.
    Must run before ``require_auth`` on each page.
    """
    current_uid = st.session_state.get("user_id")
    if current_uid is not None:
        try:
            existing = st.query_params.get(_QUERY_KEY)
            if not existing or _verify_token(existing) != current_uid:
                st.query_params[_QUERY_KEY] = _make_token(int(current_uid))
        except Exception:
            pass
        return

    token = st.query_params.get(_QUERY_KEY)
    if not token:
        return
    user_id = _verify_token(token)
    if user_id is None:
        _drop_query_token()
        return
    try:
        with get_session() as s:
            user = s.get(User, user_id)
            if user is None or not user.is_active:
                _drop_query_token()
                return
            _set_session_from_user(user)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Password hashing (pure)
# ---------------------------------------------------------------------------
def hash_password(plain: str) -> str:
    """Return a bcrypt hash of ``plain`` as a UTF-8 string."""
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """Return True iff ``plain`` matches ``hashed``.

    Never raises — a corrupt or malformed ``hashed`` value yields False.
    """
    if not plain or not hashed:
        return False
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False


# ---------------------------------------------------------------------------
# Authentication (DB-backed, Streamlit-free)
# ---------------------------------------------------------------------------
def _audit(session: Session, *, user_id: Optional[int], action: str, payload: dict) -> None:
    session.add(
        AuditLog(user_id=user_id, action=action, new_value=payload)
    )


def authenticate(username: str, password: str, session: Session) -> Optional[User]:
    """Verify credentials and return the ``User`` on success, else ``None``.

    Side effects:
      - Writes one ``AuditLog`` row (login_success / login_failed).
      - On success, updates ``user.last_login_at = now_tr()``.
      - Always commits.
    """
    user = session.execute(
        select(User).where(User.username == username)
    ).scalar_one_or_none()

    if user is None:
        _audit(session, user_id=None, action="login_failed",
               payload={"username_attempted": username, "reason": "unknown_user"})
        session.commit()
        return None

    if not user.is_active:
        _audit(session, user_id=user.id, action="login_failed",
               payload={"username_attempted": username, "reason": "inactive"})
        session.commit()
        return None

    if not verify_password(password, user.password_hash):
        _audit(session, user_id=user.id, action="login_failed",
               payload={"username_attempted": username, "reason": "bad_password"})
        session.commit()
        return None

    user.last_login_at = now_tr()
    _audit(session, user_id=user.id, action="login_success",
           payload={"username": username})
    session.commit()
    return user


# ---------------------------------------------------------------------------
# Authorization (pure)
# ---------------------------------------------------------------------------
def user_can_submit_for(user_id: int, department_id: int, session: Session) -> bool:
    """True if ``user_id`` is linked to ``department_id`` via user_departments."""
    link = session.execute(
        select(UserDepartment).where(
            UserDepartment.user_id == user_id,
            UserDepartment.department_id == department_id,
        )
    ).scalar_one_or_none()
    return link is not None


def get_user_departments(user_id: int, session: Session) -> list[Department]:
    """Return the active departments a user may submit for, ordered by name."""
    return list(
        session.execute(
            select(Department)
            .join(UserDepartment, UserDepartment.department_id == Department.id)
            .where(
                UserDepartment.user_id == user_id,
                Department.is_active.is_(True),
            )
            .order_by(Department.name)
        ).scalars()
    )


# ---------------------------------------------------------------------------
# Session state (Streamlit-bound)
# ---------------------------------------------------------------------------
_SESSION_KEYS = ("user_id", "username", "role", "full_name", "department_ids")


def _set_session_from_user(user: User) -> None:
    st.session_state["user_id"] = user.id
    st.session_state["username"] = user.username
    st.session_state["role"] = user.role
    st.session_state["full_name"] = user.full_name
    st.session_state["department_ids"] = [
        link.department_id for link in user.department_links
    ]


def clear_auth_state() -> None:
    """Clear local Streamlit auth state and the URL session token.

    The post-logout / post-login landing page is handled by app.py via
    `st.switch_page("pages/00_ana_sayfa.py")` after a successful login,
    so we don't need to manipulate the browser URL with JavaScript here.
    """
    for key in _SESSION_KEYS:
        st.session_state.pop(key, None)
    try:
        st.query_params.clear()
    except Exception:
        _drop_query_token()
    # Also wipe queued toasts and login_error so re-login is clean.
    st.session_state.pop("pending_toasts", None)
    st.session_state.pop("login_error", None)


def login_user(user: User) -> None:
    """Store the user's identity in session_state and drop a signed token
    in the URL so a WebSocket reconnect mid-session can rehydrate
    without bouncing to login. The actual redirect to Ana Sayfa is
    handled by the caller via ``st.switch_page("pages/00_ana_sayfa.py")``.
    """
    _set_session_from_user(user)
    try:
        st.query_params[_QUERY_KEY] = _make_token(user.id)
    except Exception:
        pass


def logout_user(session: Session) -> None:
    """Write a ``logout`` audit entry and clear session state."""
    user_id = st.session_state.get("user_id")
    username = st.session_state.get("username")
    if user_id is not None:
        _audit(session, user_id=user_id, action="logout",
               payload={"username": username})
        session.commit()
    clear_auth_state()


def is_authenticated() -> bool:
    """True iff there is a logged-in user in this Streamlit session."""
    return st.session_state.get("user_id") is not None


def get_current_user(session: Session) -> Optional[User]:
    """Reload the current user from DB (role / is_active may have changed)."""
    user_id = st.session_state.get("user_id")
    if user_id is None:
        return None
    return session.get(User, user_id)


def _redirect_to_login(message: str) -> None:
    st.warning(message)
    try:
        st.switch_page("app.py")
    except Exception:
        st.stop()


def require_auth(session: Session) -> User:
    """Block the page unless an active user is logged in.

    On failure (no session, deleted user, or deactivated account) clears
    the session state, shows an error, and stops Streamlit rendering.
    """
    if not is_authenticated():
        _redirect_to_login("Bu sayfayı görüntülemek için giriş yapmanız gerekiyor.")

    user = get_current_user(session)
    if user is None or not user.is_active:
        clear_auth_state()
        _redirect_to_login("Oturumunuz geçersiz, lütfen tekrar giriş yapın.")

    return user


def require_admin(session: Session) -> User:
    """Block the page unless the logged-in user has role='admin'."""
    user = require_auth(session)
    if user.role != "admin":
        st.error("Bu sayfaya yalnızca yöneticiler erişebilir.")
        st.stop()
    return user
