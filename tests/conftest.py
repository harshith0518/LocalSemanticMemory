import json
import os
from dataclasses import replace
from pathlib import Path

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
        for table in (
            "feedback_receipts",
            "passage_exclusions",
            "source_exclusions",
            "control_receipts",
            "claim_relations",
            "processing_receipts",
            "model_calls",
            "model_budgets",
            "claim_evidence",
            "claim_revisions",
            "passages",
            "jobs",
            "sources",
            "policies",
        ):
            connection.execute(text(f"DELETE FROM jarvis.{table}"))
    yield engine
    engine.dispose()


@pytest.fixture
def service(engine):
    return Service(engine)


@pytest.fixture
def observation():
    return json.loads(Path("tests/fixtures/s04-observation.json").read_text())


@pytest.fixture
def claim_content():
    # A deterministic proposal; never imported as a source observation or an answer key.
    return json.loads(Path("tests/fixtures/s04-proposal.json").read_text())


@pytest.fixture
def normal(service):
    return service.identity.context("normal")


@pytest.fixture
def private(service):
    return service.identity.context("private")


@pytest.fixture
def source(service, normal, observation):
    return service.save_observation(
        normal,
        {
            "observation": observation,
            "expected_policy_revision": 0,
            "expected_source_revision": 0,
        },
    )


@pytest.fixture
def proposal(source, claim_content):
    return {
        "expected_policy_revision": 0,
        "content": claim_content,
        "passages": [
            {
                "source_id": str(source.id),
                "source_revision": source.revision,
                "variant": "raw",
                "start": 0,
                "end": len(source.raw_text),
                "exact_text": source.raw_text,
            }
        ],
    }
