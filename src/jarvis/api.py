from contextlib import asynccontextmanager

from fastapi import FastAPI, Response

from jarvis.config import Settings
from jarvis.db import make_engine
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

    app = FastAPI(title="Hey Jarvis bootstrap", lifespan=lifespan)

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
