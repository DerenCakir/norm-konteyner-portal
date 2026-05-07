"""
Database engine, session factory, and declarative base.

Uses SQLAlchemy 2.0 style. The engine is created once at import time
from settings.database_url. Sessions are short-lived and obtained
through the get_session() context manager.
"""

from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from config.settings import get_settings
from db.base import Base  # re-exported for convenience

__all__ = ["Base", "engine", "SessionLocal", "get_session"]


def _build_engine() -> Engine:
    """Create the SQLAlchemy engine.

    Pool configuration is tuned for Supabase Transaction Pooler:
      - pool_pre_ping: detect dropped connections before use
      - pool_recycle=300: recycle connections every 5 minutes (pooler
        may close idle connections)
      - pool_size=15 / max_overflow=25: ~30 simultaneous users on
        Pazartesi 09:00–12:00 plus Streamlit rerun churn (every widget
        interaction respawns sessions). 40 total connections give us
        breathing room without being wasteful. Supabase Transaction
        Pooler multiplexes these onto fewer real Postgres backends, so
        this does not actually consume 40 Postgres backends.
      - connect_timeout=5: a hung Postgres handshake fails fast instead
        of freezing the user's request.
    """
    settings = get_settings()
    return create_engine(
        settings.database_url,
        pool_pre_ping=True,
        pool_recycle=300,
        pool_size=15,
        max_overflow=25,
        pool_timeout=10,
        connect_args={"connect_timeout": 5},
        future=True,
    )


engine: Engine = _build_engine()

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
)


@contextmanager
def get_session() -> Iterator[Session]:
    """Yield a SQLAlchemy session, committing on success and rolling
    back on error. Always closes the session.

    BaseException-but-not-Exception (e.g. Streamlit's RerunException,
    KeyboardInterrupt) is treated as a control-flow signal: the work the
    caller already did inside the ``with`` block is committed before the
    signal is allowed to propagate. Without this, calling ``st.rerun()``
    inside the block would silently discard the writes.

    Usage:
        with get_session() as session:
            session.add(obj)
    """
    session = SessionLocal()
    try:
        yield session
    except Exception:
        session.rollback()
        raise
    except BaseException:
        try:
            session.commit()
        except Exception:
            session.rollback()
        raise
    else:
        session.commit()
    finally:
        session.close()
