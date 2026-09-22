"""Isolated browser acceptance server with an explicit deterministic extractor."""

import sys
from pathlib import Path
from threading import Event, Thread

import uvicorn

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from answer_double import FixtureResponder  # noqa: E402
from memory_double import FixtureExtractor  # noqa: E402

from jarvis.api import create_app
from jarvis.config import Settings
from jarvis.db import make_engine
from jarvis.services import Service
from jarvis.worker import run_worker

settings = Settings.from_env()
settings.require_test_database()  # Fail before any fixture or worker operation.
engine = make_engine(settings)
service = Service(
    engine,
    extractor=FixtureExtractor(),
    responder=FixtureResponder(private_direct=True),
)
stop = Event()
worker = Thread(target=run_worker, args=(service, stop), daemon=True)
worker.start()
try:
    uvicorn.run(
        create_app(service), host="0.0.0.0", port=8000, access_log=False, log_level="critical"
    )
finally:
    stop.set()
    worker.join(timeout=5)
    engine.dispose()
