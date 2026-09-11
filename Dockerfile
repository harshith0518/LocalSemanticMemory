FROM ghcr.io/astral-sh/uv:0.12.13@sha256:b485bd65cc2cf1c9a93b3554012c9c3778cf7b1b5fd3d3096ce9e1226c97e1e6 AS uv
FROM python:3.12-slim-bookworm@sha256:782412e85d0f0984994c290652577d4018aff08145c85b262bb63dc0c7522254 AS tooling
COPY --from=uv /uv /uvx /bin/
ENV UV_PYTHON_DOWNLOADS=never UV_LINK_MODE=copy PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app

FROM tooling AS application
COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --locked --no-install-project
COPY src/ src/
RUN uv sync --locked --no-editable --no-build-isolation
COPY alembic.ini ./
COPY migrations/ migrations/
COPY tests/ tests/
RUN useradd --uid 10001 --create-home jarvis
ENV PATH="/app/.venv/bin:$PATH"
USER jarvis
CMD ["uvicorn", "jarvis.api:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
