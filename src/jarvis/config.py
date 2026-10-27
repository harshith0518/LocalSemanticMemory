"""Explicit database and bounded local-provider configuration; never user input."""

import os
from dataclasses import dataclass, field
from uuid import UUID

from sqlalchemy import URL

LOCAL_OWNER = UUID("ce9e9be0-bcfa-4d45-b875-6ea50815910a")


def _strict_bool(name: str, default: bool = False) -> bool:
    value = os.environ.get(name, str(default).lower())
    if value not in {"true", "false"}:
        raise ValueError(f"{name} must be true or false")
    return value == "true"


@dataclass(frozen=True)
class Settings:
    host: str
    database: str
    user: str
    password: str = field(repr=False)
    port: int = 5432
    environment: str = "development"

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            host=os.environ["JARVIS_DB_HOST"],
            database=os.environ["JARVIS_DB_NAME"],
            user=os.environ["JARVIS_DB_USER"],
            password=os.environ["JARVIS_DB_PASSWORD"],
            port=int(os.environ.get("JARVIS_DB_PORT", "5432")),
            environment=os.environ.get("JARVIS_ENV", "development"),
        )

    @property
    def url(self) -> URL:
        return URL.create(
            "postgresql+psycopg",
            username=self.user,
            password=self.password,
            host=self.host,
            port=self.port,
            database=self.database,
        )

    def require_test_database(self) -> None:
        # Fail closed before migration, cleanup, or fixture writes.
        if (
            self.environment != "test"
            or self.host != "test-db"
            or self.port != 5432
            or self.database != "jarvis_test"
            or self.user not in {"jarvis_test_app", "jarvis_test_migrate"}
        ):
            raise ValueError("Database checks require the isolated Compose test database")
