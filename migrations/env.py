from alembic import context

from jarvis.config import Settings
from jarvis.db import make_engine
from jarvis.models import Base


def migrate(connection):
    context.configure(
        connection=connection,
        target_metadata=Base.metadata,
        include_schemas=True,
        version_table_schema="jarvis",
        # pgvector is infrastructure owned by the DB administrator.
        include_name=lambda name, kind, parents: kind != "schema" or name == "jarvis",
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()
        connection.exec_driver_sql("GRANT SELECT ON jarvis.alembic_version TO jarvis_runtime")


if context.is_offline_mode():
    raise RuntimeError("Run migrations online against the configured PostgreSQL database")
elif context.config.attributes.get("connection") is not None:
    migrate(context.config.attributes["connection"])
else:
    engine = make_engine(Settings.from_env())
    try:
        with engine.connect() as connection:
            migrate(connection)
    finally:
        engine.dispose()
