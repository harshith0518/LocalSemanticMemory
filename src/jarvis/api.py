import json
from contextlib import asynccontextmanager
from pathlib import Path
from secrets import token_urlsafe

from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool

from jarvis.config import Settings
from jarvis.db import make_engine
from jarvis.errors import ApplicationError, ErrorCode
from jarvis.imports import MAX_IMPORT_BYTES
from jarvis.metrics import capture_timings, stage
from jarvis.services import Service
from jarvis.worker import process_one

WEB_ROOT = Path(__file__).parent / "web"
PUBLIC_REPORTS = {
    "lightning": "s12-lightning-backup-review.json",
    "comparison": "s12-free-provider-review.json",
    "showcase": "s15-showcase-review.json",
    "showcase_baseline": "s14-showcase-review.json",
    "readiness": "s14-readiness-review.json",
}


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
    def interface(request: Request) -> HTMLResponse:
        return HTMLResponse(
            (WEB_ROOT / "index.html")
            .read_text(encoding="utf-8")
            .replace("__JARVIS_STYLE_NONCE__", request.state.style_nonce)
        )

    @app.middleware("http")
    async def input_boundary(request: Request, call_next):
        # Radix's scroll lock uses a generated style tag, authorized per response.
        request.state.style_nonce = token_urlsafe(24)
        with capture_timings(enabled=request.headers.get("X-Jarvis-Mode") == "normal") as timings:
            with stage("request"):
                try:
                    response = await call_next(request)
                except Exception:
                    # Never allow Uvicorn to log private exception text.
                    response = JSONResponse(
                        ApplicationError(ErrorCode.OPERATION_FAILED).response(), status_code=500
                    )
            if timings is not None:
                response.headers["Server-Timing"] = ", ".join(
                    f"{name};dur={value['elapsed_ms']:.3f}" for name, value in timings.items()
                )
        response.headers["Cache-Control"] = "no-store"
        response.headers["Pragma"] = "no-cache"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Frame-Options"] = "DENY"
        if request.url.path == "/" or request.url.path.startswith("/assets/"):
            response.headers["Content-Security-Policy"] = (
                "default-src 'none'; script-src 'self'; "
                f"style-src 'self' 'nonce-{request.state.style_nonce}'; "
                "font-src 'self'; connect-src 'self'; img-src 'self'; base-uri 'none'; "
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
            ErrorCode.RATE_LIMITED: 429,
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

    @app.post("/processing/step")
    async def processing_step(request: Request, namespace: str):
        service = app.state.service
        context = service.identity.context(request.headers.get("X-Jarvis-Mode", ""))
        context.require_saved_access()
        # Existing backend lease, eligibility, budget and commit fences remain authoritative.
        result = await run_in_threadpool(process_one, service, context, namespace=namespace)
        return {"result": result, "pause_ms": 6100 if service.extractor.live else 0}

    @app.get("/processing/report")
    def processing_report(request: Request, namespace: str):
        service = app.state.service
        context = service.identity.context(request.headers.get("X-Jarvis-Mode", ""))
        return service.processing_report(context, {"namespace": namespace})

    @app.get("/evaluation/reports/{report_id}")
    def evaluation_report(request: Request, report_id: str):
        service = app.state.service
        context = service.identity.context(request.headers.get("X-Jarvis-Mode", ""))
        service._authorize(context)
        filename = PUBLIC_REPORTS.get(report_id)
        if filename is None:
            raise ApplicationError(ErrorCode.REFERENCE_UNAVAILABLE)
        path = Path("eval/reports") / filename
        if not path.is_file():
            return {"status": "not_recorded", "report": filename}
        # Fixed curated synthetic summaries only, never arbitrary paths or private exports.
        with path.open("rb") as stream:
            payload = stream.read(2_000_001)
        if len(payload) > 2_000_000:
            raise ApplicationError(ErrorCode.CONTEXT_LIMIT)
        return json.loads(payload.decode("utf-8-sig"))

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

    @app.post("/search")
    async def search(request: Request):
        service = app.state.service
        context = service.identity.context(request.headers.get("X-Jarvis-Mode", ""))
        context.require_saved_access()  # Before receiving a query, even on failure paths.
        payload = await current_input(request)
        return await run_in_threadpool(service.search, context, payload, JSONResponse)

    @app.post("/ask")
    async def ask(request: Request):
        service = app.state.service
        context = service.identity.context(request.headers.get("X-Jarvis-Mode", ""))
        context.require_saved_access()
        payload = await current_input(request)
        return await run_in_threadpool(service.ask, context, payload, JSONResponse)

    @app.post("/conversation/messages")
    async def save_message(request: Request):
        service = app.state.service
        context = service.identity.context(request.headers.get("X-Jarvis-Mode", ""))
        context.require_saved_access()
        return await run_in_threadpool(service.save_message, context, await current_input(request))

    @app.post("/conversation/messages/{source_id}/learn")
    async def learn_message(request: Request, source_id: str):
        service = app.state.service
        context = service.identity.context(request.headers.get("X-Jarvis-Mode", ""))
        context.require_saved_access()
        return await run_in_threadpool(
            service.learn_message, context, source_id, await current_input(request)
        )

    @app.get("/conversation/messages/{source_id}")
    def message_learning(request: Request, source_id: str):
        service = app.state.service
        context = service.identity.context(request.headers.get("X-Jarvis-Mode", ""))
        return service.message_learning(context, source_id)

    @app.post("/private/ask")
    async def private_ask(request: Request):
        service = app.state.service
        context = service.identity.context(request.headers.get("X-Jarvis-Mode", ""))
        # Authorize this narrowly-scoped provider route before receiving its body.
        service.private_answer_gate(context)
        payload = await current_input(request)
        return await run_in_threadpool(service.ask_private, context, payload)

    @app.post("/controls/preview")
    async def preview_control(request: Request):
        service = app.state.service
        context = service.identity.context(request.headers.get("X-Jarvis-Mode", ""))
        context.require_saved_access()
        return await run_in_threadpool(
            service.preview_control, context, await current_input(request)
        )

    @app.post("/controls/apply")
    async def apply_control(request: Request):
        service = app.state.service
        context = service.identity.context(request.headers.get("X-Jarvis-Mode", ""))
        context.require_saved_access()
        return await run_in_threadpool(service.apply_control, context, await current_input(request))

    @app.get("/usage")
    def usage(request: Request):
        service = app.state.service
        context = service.identity.context(request.headers.get("X-Jarvis-Mode", ""))
        return service.usage_snapshot(context, JSONResponse)

    @app.get("/trial/sources")
    def sample_sources(request: Request):
        # Check policy before touching even this public fixture on a Private request.
        service = app.state.service
        context = service.identity.context(request.headers.get("X-Jarvis-Mode", ""))
        service._authorize(context)
        return {"jsonl": Path("data/synthetic/sample-dictations.jsonl").read_text(encoding="utf-8")}

    @app.get("/trial/questions")
    def questions():
        from jarvis.answers import trial_questions

        return {"questions": trial_questions()}

    @app.get("/inference")
    def inference(request: Request):
        service = app.state.service
        context = service.identity.context(request.headers.get("X-Jarvis-Mode", ""))
        return service.inference_status(context)

    @app.get("/trial/corpus")
    def corpus(request: Request):
        service = app.state.service
        context = service.identity.context(request.headers.get("X-Jarvis-Mode", ""))
        service._authorize(context)
        return {"jsonl": Path("data/synthetic/corpus-540.jsonl").read_text(encoding="utf-8")}

    @app.get("/trial/showcase")
    def showcase(request: Request):
        import json

        service = app.state.service
        context = service.identity.context(request.headers.get("X-Jarvis-Mode", ""))
        service._authorize(context)
        data = json.loads(Path("eval/fixtures/corpus-cases.json").read_text(encoding="utf-8"))
        return {
            "cases": [
                {"title": c["title"], "request": c["request"], "category": c["category"]}
                for c in data["cases"]
                if c["split"] == "showcase"
            ]
        }

    @app.post("/feedback")
    async def feedback(request: Request):
        service = app.state.service
        context = service.identity.context(request.headers.get("X-Jarvis-Mode", ""))
        context.require_saved_access()
        return await run_in_threadpool(
            service.feedback, context, await current_input(request), JSONResponse
        )

    return app
