import json
import signal
import sys
from collections.abc import Callable
from threading import Event

import typer
from sqlalchemy.exc import SQLAlchemyError

from jarvis.config import Settings
from jarvis.db import make_engine
from jarvis.errors import ApplicationError, ErrorCode
from jarvis.evaluation import extraction_pilot
from jarvis.imports import MAX_IMPORT_BYTES
from jarvis.services import Service
from jarvis.worker import process_one, run_worker

app = typer.Typer(no_args_is_help=True, pretty_exceptions_enable=False)
probe = typer.Typer(help="Write/read one fixed synthetic bootstrap observation; no user imports.")
app.add_typer(probe, name="probe")
contracts = typer.Typer(help="Validate synthetic contract JSON from stdin; never saves input.")
app.add_typer(contracts, name="contracts")
sources = typer.Typer(help="Import UTF-8 JSONL dictations and inspect saved source evidence.")
app.add_typer(sources, name="sources")


def run(operation: Callable[[Service], dict | None]) -> None:
    try:
        settings = Settings.from_env()
    except (KeyError, ValueError):
        typer.echo('{"status":"error","reason":"invalid_configuration"}')
        raise typer.Exit(1) from None
    engine = make_engine(settings)
    try:
        result = operation(Service(engine))
        if result is None:
            result = {"status": "error", "reason": "probe_missing"}
        typer.echo(json.dumps(result, default=str, sort_keys=True))
        if result.get("status") in {"not_ready", "error", "failed"}:
            raise typer.Exit(1)
    except ApplicationError as error:
        typer.echo(json.dumps(error.response()))
        raise typer.Exit(1) from None
    except SQLAlchemyError:
        typer.echo('{"status":"error","reason":"database_operation_failed"}')
        raise typer.Exit(1) from None
    except typer.Exit:
        raise
    except Exception:
        typer.echo(json.dumps(ApplicationError(ErrorCode.OPERATION_FAILED).response()))
        raise typer.Exit(1) from None
    finally:
        engine.dispose()


@app.command()
def health() -> None:
    """Process liveness; does not query the database."""
    run(lambda service: service.health())


@app.command()
def ready() -> None:
    """Check database connectivity, schema revision and pgvector."""
    run(lambda service: service.ready())


@app.command("process")
def process_sources(
    namespace: str = typer.Option(...),
    expected_policy_revision: int = typer.Option(...),
    mode: str = typer.Option(...),
    retry_failed: bool = False,
):
    """Queue a collection through the same service used by the browser."""
    run(
        lambda service: service.request_processing(
            service.identity.context(mode),
            {
                "namespace": namespace,
                "expected_policy_revision": expected_policy_revision,
                "retry_failed": retry_failed,
            },
        )
    )


@app.command("memories")
def memories(
    namespace: str = typer.Option(...), mode: str = typer.Option(...), after: str | None = None
):
    """Inspect memory through shared services; the browser is the primary user surface."""
    run(
        lambda service: service.list_memories(
            service.identity.context(mode),
            {
                "namespace": namespace,
                "after": after,
            },
        )
    )


@app.command("worker")
def worker(once: bool = False):
    """Run the DB-backed worker; never prints inputs, model responses or exception details."""

    def work(service):
        if once:
            return process_one(service, service.identity.context("normal")) or {"status": "idle"}
        stop = Event()
        for sig in (signal.SIGTERM, signal.SIGINT):
            signal.signal(sig, lambda *_: stop.set())
        run_worker(service, stop)
        return {"status": "stopped"}

    run(work)


@app.command("evaluate-extraction")
def evaluate_extraction(repeats: int = 3):
    """Synthetic-only live pilot, subject to the persisted S07 allowance; no automatic grade."""
    run(lambda service: extraction_pilot(service, repeats=repeats))


@app.command("search")
def search(mode: str = typer.Option(...)):
    """Read a search request from stdin; use the browser for ordinary searches."""

    def operation(service):
        context = service.identity.context(mode)
        context.require_saved_access()
        payload = sys.stdin.read(8193)
        if len(payload.encode("utf-8")) > 8192:
            raise ApplicationError(ErrorCode.INVALID_INPUT)
        return service.search(context, payload)

    run(operation)


@probe.command("write")
def write_probe(mode: str = "normal") -> None:
    run(lambda service: service.write_probe(service.identity.context(mode)))


@probe.command("read")
def read_probe(mode: str = "normal") -> None:
    run(lambda service: service.read_probe(service.identity.context(mode)))


def validate(service: Service, kind: str, mode: str) -> dict:
    context = service.identity.context(mode)
    if kind == "claim":
        context.require_saved_access()
    payload = sys.stdin.read(1024 * 1024 + 1)
    if len(payload.encode("utf-8")) > 1024 * 1024:
        raise ApplicationError(ErrorCode.INVALID_INPUT)
    operation = service.validate_observation if kind == "observation" else service.validate_claim
    operation(context, payload)
    return {"status": "valid", "stored": False}


@contracts.command("observation")
def validate_observation(mode: str = typer.Option(...)) -> None:
    run(lambda service: validate(service, "observation", mode))


@contracts.command("claim")
def validate_claim(mode: str = typer.Option(...)) -> None:
    run(lambda service: validate(service, "claim", mode))


@sources.command("import")
def import_sources(
    namespace: str = typer.Option(...),
    expected_policy_revision: int = typer.Option(...),
    mode: str = typer.Option(...),
) -> None:
    """Read one bounded JSONL batch from stdin; retries preserve observation identity."""

    def operation(service: Service) -> dict:
        context = service.identity.context(mode)
        context.require_saved_access()  # Before any stdin read, including malformed input.
        stream = getattr(sys.stdin, "buffer", sys.stdin)
        payload = stream.read(MAX_IMPORT_BYTES + 1)
        return service.import_observations(
            context,
            {
                "namespace": namespace,
                "expected_policy_revision": expected_policy_revision,
            },
            payload,
        ).model_dump(mode="json")

    run(operation)


@sources.command("list")
def list_sources(
    namespace: str = typer.Option(...),
    mode: str = typer.Option(...),
    after: str | None = None,
    limit: int = 50,
) -> None:
    run(
        lambda service: service.list_sources(
            service.identity.context(mode),
            {
                "namespace": namespace,
                "after": after,
                "limit": limit,
            },
        ).model_dump(mode="json")
    )


@sources.command("inspect")
def inspect_source(source_id: str, mode: str = typer.Option(...)) -> None:
    run(
        lambda service: service.inspect_source(
            service.identity.context(mode),
            source_id,
        ).model_dump(mode="json")
    )
