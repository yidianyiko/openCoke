from __future__ import annotations

from dataclasses import dataclass
import os
from typing import Mapping


class ConfigurationError(RuntimeError):
    """Raised when required runtime configuration is missing or invalid."""


@dataclass(frozen=True, slots=True)
class Settings:
    database_url: str
    redis_url: str
    app_env: str = "local"

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> "Settings":
        source = os.environ if environ is None else environ

        database_url = (source.get("DATABASE_URL") or "").strip()
        redis_url = (source.get("REDIS_URL") or "").strip()
        app_env = (source.get("APP_ENV") or "local").strip() or "local"

        if not database_url:
            raise ConfigurationError("DATABASE_URL is required for Coke backend startup")
        if not redis_url:
            raise ConfigurationError("REDIS_URL is required for Coke backend startup")

        return cls(
            database_url=database_url,
            redis_url=redis_url,
            app_env=app_env,
        )
