import json
from collections.abc import Callable

import typer
from sqlalchemy.exc import SQLAlchemyError

from jarvis.config import Settings
from jarvis.db import make_engine
from jarvis.services import Service

app = typer.Typer(no_args_is_help=True, pretty_exceptions_enable=False)
probe = typer.Typer(help="Write/read one fixed synthetic bootstrap observation; no user imports.")
app.add_typer(probe, name="probe")


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
        if result.get("status") in {"not_ready", "error"}:
            raise typer.Exit(1)
    except SQLAlchemyError:
        typer.echo('{"status":"error","reason":"database_operation_failed"}')
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


@probe.command("write")
def write_probe() -> None:
    run(lambda service: service.write_probe())


@probe.command("read")
def read_probe() -> None:
    run(lambda service: service.read_probe())
