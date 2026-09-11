from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool

from jarvis.config import Settings
from jarvis.db import make_engine
from jarvis.errors import ApplicationError, ErrorCode
from jarvis.imports import MAX_IMPORT_BYTES
from jarvis.services import Service

WEB_ROOT = Path(__file__).parent / "web"


def create_app(service: Service | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if service is not None:
            app.state.service = service
            yield
        else:
            engine = make_engine(Settings.from_env())
            try:
                app.state.service = Service(engine)
                yield
            finally:
                engine.dispose()

    app = FastAPI(title="Hey Jarvis backend", lifespan=lifespan)
    app.mount("/assets", StaticFiles(directory=WEB_ROOT), name="assets")

    @app.get("/", include_in_schema=False)
    def interface() -> FileResponse:
        return FileResponse(WEB_ROOT / "index.html")

    @app.middleware("http")
    async def input_boundary(request: Request, call_next):
        try:
            response = await call_next(request)
        except Exception:
            # Consume unexpected failures here so Uvicorn cannot log private exception text.
            response = JSONResponse(
                ApplicationError(ErrorCode.OPERATION_FAILED).response(), status_code=500
            )
        response.headers["Cache-Control"] = "no-store"
        response.headers["Pragma"] = "no-cache"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Frame-Options"] = "DENY"
        if request.url.path == "/" or request.url.path.startswith("/assets/"):
            response.headers["Content-Security-Policy"] = (
                "default-src 'none'; script-src 'self'; style-src 'self'; "
                "connect-src 'self'; img-src 'self'; base-uri 'none'; "
                "form-action 'none'; frame-ancestors 'none'; object-src 'none'"
            )
        if response.headers.get("Content-Type") == "application/json":
            # Windows PowerShell 5 otherwise decodes JSON as a legacy single-byte encoding.
            response.headers["Content-Type"] = "application/json; charset=utf-8"
        return response

    @app.exception_handler(ApplicationError)
    async def application_error(request: Request, error: ApplicationError):
        status = {
            ErrorCode.PRIVATE_OPERATION: 403,
            ErrorCode.REFERENCE_UNAVAILABLE: 404,
            ErrorCode.STALE_REVISION: 409,
            ErrorCode.IMPORT_CONFLICT: 409,
            ErrorCode.DATABASE_UNAVAILABLE: 503,
            ErrorCode.OPERATION_FAILED: 500,
            ErrorCode.PROVIDER_DISABLED: 503,
            ErrorCode.BUDGET_EXHAUSTED: 429,
            ErrorCode.TRIAL_INPUT_DENIED: 403,
        }.get(error.code, 422)
        return JSONResponse(error.response(), status_code=status)

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request: Request, error: RequestValidationError):
        return JSONResponse(ApplicationError(ErrorCode.INVALID_INPUT).response(), status_code=422)

    async def current_input(request: Request) -> bytes:
        chunks = []
        size = 0
        async for chunk in request.stream():
            size += len(chunk)
            if size > MAX_IMPORT_BYTES:
                raise ApplicationError(ErrorCode.INVALID_INPUT)
            chunks.append(chunk)
        return b"".join(chunks)

    @app.post("/contracts/observations/validate")
    async def validate_observation(request: Request) -> dict:
        service = app.state.service
        context = service.identity.context(request.headers.get("X-Jarvis-Mode", ""))
        service.validate_observation(context, await current_input(request))
        return {"status": "valid", "stored": False}

    @app.post("/contracts/claims/validate")
    async def validate_claim(request: Request) -> dict:
        service = app.state.service
        context = service.identity.context(request.headers.get("X-Jarvis-Mode", ""))
        context.require_saved_access()
        payload = await current_input(request)
        await run_in_threadpool(service.validate_claim, context, payload)
        return {"status": "valid", "stored": False}

    @app.get("/health")
    def health() -> dict:
        return app.state.service.health()

    @app.post("/sources/import")
    async def import_sources(
        request: Request, namespace: str, expected_policy_revision: int
    ) -> dict:
        service = app.state.service
        context = service.identity.context(request.headers.get("X-Jarvis-Mode", ""))
        context.require_saved_access()
        payload = await current_input(request)
        receipt = await run_in_threadpool(
            service.import_observations,
            context,
            {"namespace": namespace, "expected_policy_revision": expected_policy_revision},
            payload,
        )
        return receipt.model_dump(mode="json")

    @app.get("/sources")
    def list_sources(
        request: Request, namespace: str, after: str | None = None, limit: int = 50
    ) -> dict:
        service = app.state.service
        context = service.identity.context(request.headers.get("X-Jarvis-Mode", ""))
        return service.list_sources(
            context, {"namespace": namespace, "after": after, "limit": limit}
        ).model_dump(mode="json")

    @app.get("/sources/{source_id}")
    def inspect_source(request: Request, source_id: str) -> dict:
        service = app.state.service
        context = service.identity.context(request.headers.get("X-Jarvis-Mode", ""))
        return service.inspect_source(context, source_id).model_dump(mode="json")

    @app.get("/ready")
    def ready(response: Response) -> dict:
        result = app.state.service.ready()
        if result["status"] != "ready":
            response.status_code = 503
        return result

    @app.post("/processing")
    async def process_sources(request: Request) -> dict:
        service = app.state.service
        context = service.identity.context(request.headers.get("X-Jarvis-Mode", ""))
        context.require_saved_access()
        payload = await current_input(request)
        return await run_in_threadpool(service.request_processing, context, payload)

    @app.get("/processing")
    def processing_status(request: Request, namespace: str) -> dict:
        service = app.state.service
        context = service.identity.context(request.headers.get("X-Jarvis-Mode", ""))
        return service.processing_status(context, {"namespace": namespace})

    @app.get("/memories")
    def memories(request: Request, namespace: str, after: str | None = None, limit: int = 50):
        service = app.state.service
        context = service.identity.context(request.headers.get("X-Jarvis-Mode", ""))
        return service.list_memories(
            context, {"namespace": namespace, "after": after, "limit": limit}
        )

    @app.get("/memories/{claim_id}")
    def memory_history(request: Request, claim_id: str):
        service = app.state.service
        context = service.identity.context(request.headers.get("X-Jarvis-Mode", ""))
        return service.memory_history(context, claim_id)

    return app
