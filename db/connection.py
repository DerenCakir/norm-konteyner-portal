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
      - pool_size / max_overflow: small footprint suitable for
        Streamlit's per-session usage
    """
    settings = get_settings()
    return create_engine(
        settings.database_url,
        pool_pre_ping=True,
        pool_recycle=300,
        pool_size=5,
        max_overflow=10,
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

    Usage:
        with get_session() as session:
            session.add(obj)
    """
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
