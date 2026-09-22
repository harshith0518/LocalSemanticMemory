FROM node:24-bookworm-slim@sha256:2fe369e969550cde8e867afc3fe370b260140cab4a23d467074295b42163d553 AS frontend
WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

FROM ghcr.io/astral-sh/uv:0.12.13@sha256:b485bd65cc2cf1c9a93b3554012c9c3778cf7b1b5fd3d3096ce9e1226c97e1e6 AS uv
FROM python:3.12-slim-bookworm@sha256:782412e85d0f0984994c290652577d4018aff08145c85b262bb63dc0c7522254 AS tooling
COPY --from=uv /uv /uvx /bin/
ENV UV_PYTHON_DOWNLOADS=never UV_LINK_MODE=copy PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app

FROM tooling AS application
COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --locked --no-install-project
COPY src/ src/
COPY --from=frontend /build/src/jarvis/web/ src/jarvis/web/
RUN uv sync --locked --no-editable --no-build-isolation
COPY alembic.ini ./
COPY migrations/ migrations/
COPY tests/ tests/
COPY data/synthetic/sample-dictations.jsonl data/synthetic/sample-dictations.jsonl
COPY data/synthetic/control-observations.json data/synthetic/control-observations.json
COPY eval/fixtures/sample-evaluation-cases.json eval/fixtures/sample-evaluation-cases.json
COPY eval/fixtures/s08-retrieval.json eval/fixtures/s08-retrieval.json
COPY eval/retrieval.py eval/retrieval.py
COPY eval/live.py eval/live.py
COPY eval/efficiency.py eval/efficiency.py
COPY data/synthetic/corpus-540.jsonl data/synthetic/corpus-540.jsonl
COPY eval/fixtures/corpus-cases.json eval/fixtures/corpus-cases.json
COPY eval/fixtures/corpus-manifest.json eval/fixtures/corpus-manifest.json
COPY eval/corpus.py eval/corpus.py
COPY eval/showcase.py eval/showcase.py
COPY eval/semantic_turns.py eval/semantic_turns.py
COPY eval/build_corpus.py eval/build_corpus.py
COPY eval/reports/*-review.json eval/reports/
RUN useradd --uid 10001 --create-home jarvis
ENV PATH="/app/.venv/bin:$PATH"
USER jarvis
CMD ["uvicorn", "jarvis.api:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
