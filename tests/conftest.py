import os
from dataclasses import replace

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text

from jarvis.config import Settings
from jarvis.db import make_engine
from jarvis.services import Service


@pytest.fixture(scope="session")
def settings():
    result = Settings.from_env()
    result.require_test_database()
    return result


@pytest.fixture(scope="session")
def migration_engine(settings):
    migration_settings = replace(
        settings,
        user="jarvis_test_migrate",
        password=os.environ["JARVIS_TEST_MIGRATION_PASSWORD"],
    )
    migration_settings.require_test_database()
    engine = make_engine(migration_settings)
    yield engine
    engine.dispose()


@pytest.fixture(scope="session")
def migrations(migration_engine):
    def run(action, target=None):
        config = Config("alembic.ini")
        with migration_engine.begin() as connection:
            config.attributes["connection"] = connection
            if target is None:
                action(config)
            else:
                action(config, target)

    run(command.upgrade, "head")
    return run


@pytest.fixture
def engine(settings, migrations):
    engine = make_engine(settings)
    # Only the isolated, validated test target reaches this fixture.
    with engine.begin() as connection:
        for table in ("jobs", "sources", "policies"):
            connection.execute(text(f"DELETE FROM jarvis.{table}"))
    yield engine
    engine.dispose()


@pytest.fixture
def service(engine):
    return Service(engine)
