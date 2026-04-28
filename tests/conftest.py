"""Shared pytest fixtures.

The ``session`` fixture spins up an in-memory SQLite database, creates
the full schema from the ORM metadata, and yields a SQLAlchemy session.
This lets tests exercise queries / inserts without a Postgres instance.

Production runs on Supabase Postgres; SQLite-vs-Postgres deltas:
  - JSONB → JSON via ``with_variant`` in models.py
  - TIMESTAMPTZ → naive datetime (SQLite has no tz storage). Tests
    that don't depend on tz semantics are fine.
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from db.base import Base
import db.models  # noqa: F401  -- side-effect: register models on Base.metadata


@pytest.fixture
def session() -> Session:
    """Yield a clean SQLAlchemy session backed by in-memory SQLite."""
    engine = create_engine("sqlite:///:memory:", future=True)

    # Enforce FK constraints in SQLite (off by default).
    @event.listens_for(engine, "connect")
    def _enable_fk(dbapi_conn, _):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()
        engine.dispose()
