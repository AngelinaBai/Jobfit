from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Settings:
    database_url: str
    log_level: str = "INFO"
    http_timeout_seconds: float = 15.0
    public_mode: bool = False
    admin_username: str = "admin"
    admin_password: str | None = None

    @classmethod
    def from_env(cls) -> "Settings":
        database_url = os.getenv("DATABASE_URL")
        if not database_url:
            raise RuntimeError("DATABASE_URL is required")

        public_mode = os.getenv("PUBLIC_MODE", "false").strip().lower() in {"1", "true", "yes", "on"}
        admin_password = os.getenv("ADMIN_PASSWORD")
        if public_mode and not admin_password:
            raise RuntimeError("ADMIN_PASSWORD is required when PUBLIC_MODE is enabled")

        return cls(
            database_url=database_url,
            log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
            http_timeout_seconds=float(os.getenv("HTTP_TIMEOUT_SECONDS", "15")),
            public_mode=public_mode,
            admin_username=os.getenv("ADMIN_USERNAME", "admin").strip() or "admin",
            admin_password=admin_password,
        )
