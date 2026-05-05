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
from datetime import datetime, timedelta
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
# Cookie-based persistent auth
# ---------------------------------------------------------------------------
_COOKIE_NAME = "norm_auth"
_QUERY_TOKEN_NAME = "auth"
_COOKIE_TTL_DAYS = 7
_SESSION_REFRESH_SECONDS = 30
_LOGOUT_REQUESTED_KEY = "_logout_requested"
_LOGOUT_COOKIE_CLEARED_KEY = "_logout_cookie_cleared"


def _sign(payload: str, secret: str) -> str:
    return hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()


def _make_token(user_id: int) -> str:
    """Süresi sınırlı, imzalı bir auth token üret."""
    settings = get_settings()
    payload = {"uid": user_id, "exp": int(time.time()) + _COOKIE_TTL_DAYS * 86400}
    payload_json = json.dumps(payload, separators=(",", ":"))
    payload_b64 = urlsafe_b64encode(payload_json.encode()).decode().rstrip("=")
    sig = _sign(payload_b64, settings.secret_key)
    return f"{payload_b64}.{sig}"


def _verify_token(token: str) -> Optional[int]:
    """Token geçerliyse user_id döndür, değilse None."""
    if not token or "." not in token:
        return None
    try:
        payload_b64, sig = token.split(".", 1)
        settings = get_settings()
        expected_sig = _sign(payload_b64, settings.secret_key)
        if not hmac.compare_digest(sig, expected_sig):
            return None
        # Restore base64 padding
        padded = payload_b64 + "=" * (-len(payload_b64) % 4)
        payload = json.loads(urlsafe_b64decode(padded).decode())
        if int(payload.get("exp", 0)) < int(time.time()):
            return None
        return int(payload["uid"])
    except Exception:
        return None


def _clear_query_token() -> None:
    try:
        if _QUERY_TOKEN_NAME in st.query_params:
            del st.query_params[_QUERY_TOKEN_NAME]
    except Exception:
        pass


def _set_session_from_user(user: User) -> None:
    st.session_state["user_id"] = user.id
    st.session_state["username"] = user.username
    st.session_state["role"] = user.role
    st.session_state["full_name"] = user.full_name
    st.session_state["department_ids"] = [
        link.department_id for link in user.department_links
    ]
    st.session_state["_session_refreshed_at"] = time.time()


def _get_cookie_controller():
    """Cookie controller'ı tek seferlik üret (lazy import — test'lerde import edilmesin)."""
    from streamlit_cookies_controller import CookieController
    if "_cookie_controller" not in st.session_state:
        st.session_state["_cookie_controller"] = CookieController()
    return st.session_state["_cookie_controller"]


def restore_session_from_cookie() -> None:
    """Sayfa yüklendiğinde cookie'den session'ı tazele.

    Eğer cookie geçerli bir token içeriyorsa ve session_state'te user_id
    yoksa (örn. F5 sonrası), kullanıcıyı DB'den çekip session_state'i doldur.

    ``app.py`` ve her sayfanın en başında (require_auth'tan önce) çağrılmalı.
    """
    if st.session_state.get(_LOGOUT_REQUESTED_KEY):
        if not st.session_state.get(_LOGOUT_COOKIE_CLEARED_KEY):
            _clear_auth_cookie()
            st.session_state[_LOGOUT_COOKIE_CLEARED_KEY] = True
        return

    if st.session_state.get("user_id") is not None:
        last_refresh = float(st.session_state.get("_session_refreshed_at", 0))
        if time.time() - last_refresh < _SESSION_REFRESH_SECONDS:
            return
        try:
            with get_session() as s:
                user = s.get(User, st.session_state["user_id"])
                if user is None or not user.is_active:
                    st.session_state.clear()
                    _clear_auth_cookie()
                    return
                st.session_state["username"] = user.username
                st.session_state["role"] = user.role
                st.session_state["full_name"] = user.full_name
                st.session_state["department_ids"] = [
                    link.department_id for link in user.department_links
                ]
                st.session_state["_session_refreshed_at"] = time.time()
        except Exception:
            pass
        return

    try:
        controller = _get_cookie_controller()
        controller.refresh()
        token = controller.get(_COOKIE_NAME)
        if not token:
            token = controller.getAll().get(_COOKIE_NAME)
    except Exception:
        return

    if not token:
        if not st.session_state.get("_cookie_restore_checked"):
            st.session_state["_cookie_restore_checked"] = True
            time.sleep(0.3)
            st.rerun()
        st.session_state["_cookie_restore_checked"] = False
        return

    user_id = _verify_token(token)
    if user_id is None:
        # geçersiz / süresi dolmuş — temizle
        try:
            controller.remove(_COOKIE_NAME)
        except Exception:
            pass
        return

    # DB'den user'ı tazele
    try:
        with get_session() as s:
            user = s.get(User, user_id)
            if user is None or not user.is_active:
                return
            _set_session_from_user(user)
            st.session_state["_cookie_restore_checked"] = False
    except Exception:
        return


def _set_auth_cookie(user_id: int) -> None:
    try:
        controller = _get_cookie_controller()
        token = _make_token(user_id)
        st.session_state["_auth_token"] = token
        _clear_query_token()
        controller.set(
            _COOKIE_NAME,
            token,
            max_age=_COOKIE_TTL_DAYS * 86400,
            expires=datetime.now() + timedelta(days=_COOKIE_TTL_DAYS),
            same_site="lax",
        )
        time.sleep(0.25)
    except Exception:
        pass


def _clear_auth_cookie() -> None:
    try:
        controller = _get_cookie_controller()
        controller.remove(_COOKIE_NAME)
        time.sleep(0.2)
        controller.refresh()
    except Exception:
        pass
    _clear_query_token()
    st.session_state.pop("_auth_token", None)


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
_AUTH_INTERNAL_KEYS = (
    "_auth_token",
    "_session_refreshed_at",
    "_cookie_restore_checked",
    _LOGOUT_COOKIE_CLEARED_KEY,
)


def clear_auth_state() -> None:
    """Clear local Streamlit auth state and persistent auth tokens.

    Logout must block the cookie restore path on the next rerun; otherwise a
    still-visible browser cookie or query token can immediately sign the user
    back in before the frontend cookie component finishes removing it.
    """
    for key in (*_SESSION_KEYS, *_AUTH_INTERNAL_KEYS):
        st.session_state.pop(key, None)
    st.session_state[_LOGOUT_REQUESTED_KEY] = True
    st.session_state[_LOGOUT_COOKIE_CLEARED_KEY] = False
    _clear_auth_cookie()


def login_user(user: User) -> None:
    """Store the authenticated user's identity in ``st.session_state``
    and persist a signed cookie so login survives page refreshes.
    """
    st.session_state.pop(_LOGOUT_REQUESTED_KEY, None)
    st.session_state.pop(_LOGOUT_COOKIE_CLEARED_KEY, None)
    st.session_state.pop("_cookie_restore_checked", None)
    _set_session_from_user(user)
    _set_auth_cookie(user.id)


def logout_user(session: Session) -> None:
    """Write a ``logout`` audit entry, clear session state and cookie."""
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
        # Stale session — wipe it.
        for key in _SESSION_KEYS:
            st.session_state.pop(key, None)
        _clear_auth_cookie()
        _redirect_to_login("Oturumunuz geçersiz, lütfen tekrar giriş yapın.")

    return user


def require_admin(session: Session) -> User:
    """Block the page unless the logged-in user has role='admin'."""
    user = require_auth(session)
    if user.role != "admin":
        st.error("Bu sayfaya yalnızca yöneticiler erişebilir.")
        st.stop()
    return user
