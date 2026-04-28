"""
Declarative base for ORM models.

Kept separate from db/connection.py so that importing models does not
trigger engine creation (which would require DATABASE_URL to be set).
All model files import Base from here.
"""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""
    pass
