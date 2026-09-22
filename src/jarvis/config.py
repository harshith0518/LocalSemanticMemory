"""Explicit database and bounded local-provider configuration; never user input."""

import os
from dataclasses import dataclass, field
from urllib.parse import urlsplit
from uuid import UUID

from sqlalchemy import URL

LOCAL_OWNER = UUID("ce9e9be0-bcfa-4d45-b875-6ea50815910a")

OLLAMA_HOST = "host.docker.internal"
OLLAMA_PORT = 11434
OLLAMA_BASE_URL = f"http://{OLLAMA_HOST}:{OLLAMA_PORT}/v1"
OLLAMA_CHAT_MODEL = "qwen3:4b"
OLLAMA_EMBEDDING_MODEL = "qwen3-embedding:0.6b"


def _strict_bool(name: str, default: bool = False) -> bool:
    value = os.environ.get(name, str(default).lower())
    if value not in {"true", "false"}:
        raise ValueError(f"{name} must be true or false")
    return value == "true"


@dataclass(frozen=True)
class OllamaSettings:
    """Local-only OpenAI-compatible Ollama route, deliberately unable to target a cloud host."""

    enabled: bool
    base_url: str
    api_key: str = field(repr=False)
    extractor_model: str = OLLAMA_CHAT_MODEL
    responder_model: str = OLLAMA_CHAT_MODEL
    embedding_model: str = OLLAMA_EMBEDDING_MODEL
    private_direct: bool = False

    @classmethod
    def from_env(cls) -> "OllamaSettings":
        raw_url = os.environ.get("JARVIS_OLLAMA_BASE_URL", OLLAMA_BASE_URL)
        try:
            parsed = urlsplit(raw_url)
            port = parsed.port
        except ValueError as error:
            raise ValueError("JARVIS_OLLAMA_BASE_URL is invalid") from error
        if (
            parsed.scheme != "http"
            or parsed.hostname != OLLAMA_HOST
            or port != OLLAMA_PORT
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
            or parsed.path.rstrip("/") != "/v1"
        ):
            raise ValueError(
                "JARVIS_OLLAMA_BASE_URL must be the local Docker host gateway /v1 endpoint"
            )
        extractor_model = os.environ.get("JARVIS_OLLAMA_EXTRACTOR_MODEL", OLLAMA_CHAT_MODEL)
        responder_model = os.environ.get("JARVIS_OLLAMA_RESPONDER_MODEL", OLLAMA_CHAT_MODEL)
        embedding_model = os.environ.get("JARVIS_OLLAMA_EMBEDDING_MODEL", OLLAMA_EMBEDDING_MODEL)
        if (
            extractor_model != OLLAMA_CHAT_MODEL
            or responder_model != OLLAMA_CHAT_MODEL
            or embedding_model != OLLAMA_EMBEDDING_MODEL
        ):
            raise ValueError("Only the configured local Qwen demo models are supported")
        api_key = os.environ.get("JARVIS_OLLAMA_API_KEY", "ollama")
        if api_key != "ollama":
            raise ValueError("JARVIS_OLLAMA_API_KEY must use Ollama's ignored dummy value")
        return cls(
            enabled=_strict_bool("JARVIS_OLLAMA_ENABLED"),
            base_url=OLLAMA_BASE_URL,
            api_key=api_key,
            extractor_model=extractor_model,
            responder_model=responder_model,
            embedding_model=embedding_model,
            private_direct=_strict_bool("JARVIS_OLLAMA_PRIVATE_DIRECT"),
        )

    @property
    def chat_endpoint(self) -> str:
        return f"{self.base_url}/chat/completions"


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
