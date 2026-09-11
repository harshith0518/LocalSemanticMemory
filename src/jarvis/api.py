from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from jarvis.config import Settings
from jarvis.db import make_engine
from jarvis.errors import ApplicationError, ErrorCode
from jarvis.services import Service


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
        return response

    @app.exception_handler(ApplicationError)
    async def application_error(request: Request, error: ApplicationError):
        status = {
            ErrorCode.PRIVATE_OPERATION: 403,
            ErrorCode.REFERENCE_UNAVAILABLE: 404,
            ErrorCode.STALE_REVISION: 409,
            ErrorCode.DATABASE_UNAVAILABLE: 503,
            ErrorCode.OPERATION_FAILED: 500,
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
            if size > 1024 * 1024:
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

    @app.get("/ready")
    def ready(response: Response) -> dict:
        result = app.state.service.ready()
        if result["status"] != "ready":
            response.status_code = 503
        return result

    return app
