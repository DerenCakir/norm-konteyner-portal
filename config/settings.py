"""
Application configuration loaded from environment variables.

Uses pydantic-settings to read from .env (development) or process
environment (Railway / production). Never hardcode secrets here.
"""

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration. All values come from environment."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    database_url: str = Field(
        ...,
        description=(
            "Supabase Transaction Pooler connection string (port 6543, IPv4). "
            "Direct connection (5432) does not work on Railway due to IPv6."
        ),
    )

    secret_key: str = Field(
        ...,
        min_length=32,
        description="Secret key for session signing. Use a long random string.",
    )

    app_env: Literal["development", "staging", "production"] = "development"
    timezone: str = "Europe/Istanbul"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached Settings instance. Call this from app code."""
    return Settings()
