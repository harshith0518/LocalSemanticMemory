import json
import sys
from collections.abc import Callable

import typer
from sqlalchemy.exc import SQLAlchemyError

from jarvis.config import Settings
from jarvis.db import make_engine
from jarvis.errors import ApplicationError, ErrorCode
from jarvis.services import Service

app = typer.Typer(no_args_is_help=True, pretty_exceptions_enable=False)
probe = typer.Typer(help="Write/read one fixed synthetic bootstrap observation; no user imports.")
app.add_typer(probe, name="probe")
contracts = typer.Typer(help="Validate synthetic contract JSON from stdin; never saves input.")
app.add_typer(contracts, name="contracts")


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
