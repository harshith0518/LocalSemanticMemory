from sqlalchemy import Engine, create_engine

from jarvis.config import Settings


def make_engine(settings: Settings) -> Engine:
    return create_engine(
        settings.url,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=0,
        pool_timeout=3,
        hide_parameters=True,
        connect_args={"connect_timeout": 3, "options": "-c statement_timeout=3000"},
    )
