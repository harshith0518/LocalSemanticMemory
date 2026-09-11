# Run and verify the S03 backend

S03 is implemented and checked on 11 September 2026 in the existing Windows checkout using Docker Desktop Linux containers. This is an infrastructure milestone: no personal imports, processing worker, model calls, retrieval, memory controls or UI yet. Use only the fixed synthetic probe until later milestones establish the input and policy contracts.

## Start from a checkout

Prerequisites: Git, Docker Engine in Linux mode, Compose v2, and initial network access to Docker Hub, GHCR and PyPI. Host Python/uv are unnecessary. Run these commands in PowerShell from the repository root on `dev`:

```powershell
git status --short --branch
docker version
docker compose version
if (!(Test-Path -LiteralPath .env)) { Copy-Item .env.example .env }
```

Set the three local database passwords in `.env` before the first startup. Its example values are development placeholders, not shared credentials. The acceptance run generated separate random values locally. `.env` is ignored and excluded from the image context. Changing it later does not rotate passwords already stored in a volume. If port 8000 is occupied, set `JARVIS_API_PORT` before startup and use that port in the HTTP commands below.

```powershell
docker compose config --quiet
docker compose build api
docker compose up -d --wait --wait-timeout 120 api
docker compose ps -a
Invoke-RestMethod http://127.0.0.1:8000/health
Invoke-RestMethod http://127.0.0.1:8000/ready
docker compose run --rm --no-deps cli ready
```

Check `$LASTEXITCODE` after Docker/CLI commands; nonzero means failure. PowerShell does not automatically stop on native command failures. `/health` and `jarvis health` report process liveness without querying personal data or the database. `/ready` and `jarvis ready` call the same service to verify the DB connection, Alembic revision and pgvector extension. Expected readiness is `{"status":"ready","schema":"0001_bootstrap","pgvector":"0.8.6"}`. Readiness failures return HTTP 503 / CLI exit 1 with a short category, without raw database errors or credentials.

The API is published only on `127.0.0.1`; PostgreSQL has no published host port. The server owns the fixed local identity. No endpoint accepts an owner selector or user-content writes. Application containers run as UID 10001. Source is copied into the image, so rebuild after code changes. uv and the build backend use the checked-in lock; the development checks are included in the same image for this milestone.

## Migrations and schema effects

On an empty named volume, `docker/postgres/init-db.sh` creates the pgvector extension, the `jarvis` schema, a migration login and a separate runtime login. PostgreSQL's administrator handles the extension because it requires elevated database privileges. The migration role owns only the application schema; the runtime role has DML on application records and read-only access to Alembic's revision table, with no DDL, superuser, role-creation or database-creation privileges.

Compose waits for DB health, runs the one-shot `migrate` service, then starts the API. To repeat/check migrations explicitly:

```powershell
docker compose run --rm migrate alembic upgrade head
docker compose run --rm migrate alembic current
docker compose run --rm migrate alembic check
```

Revision `0001_bootstrap` creates `jarvis.policies`, `jarvis.sources` and `jarvis.jobs`, plus Alembic's version table. Policies store the owner and nonnegative revision. Sources pair raw/formatted text, source identity/revision, SHA-256 and actual import time; supplied capture time/metadata remain nullable. The hash covers a UTF-8 JSON pair and does not define observation identity. Jobs have an owner-scoped idempotency key, pending status, attempts, and expected source/policy revisions. A composite foreign key requires the job to match its source's owner and revision. There are no embeddings, vector columns or search indexes yet.

The synthetic service creates the source and pending job in one transaction under the owner's policy-row lock. It cannot process the job. These are foundations for later controls, not evidence that Private, Correct or Forget works. Future schema changes need a new reviewed migration; do not edit an applied migration to change its meaning.

## Verify persistence

This CLI accepts no personal input: it writes one fixed synthetic observation and returns all saved source/job fields. Repeated writes return that record without duplicating it.

```powershell
$s03Before = docker compose run --rm --no-deps cli probe write
if ($LASTEXITCODE -ne 0) { throw 'Probe write failed' }
$s03Api = docker compose ps -q api
$s03Db = docker compose ps -q db
docker compose down
if ($LASTEXITCODE -ne 0) { throw 'Compose stop failed' }
docker compose up -d --wait --wait-timeout 120 api
if ($LASTEXITCODE -ne 0) { throw 'Compose start failed' }
$s03After = docker compose run --rm --no-deps cli probe read
if ($LASTEXITCODE -ne 0) { throw 'Probe read failed' }
if ($s03Before -cne $s03After) { throw 'Persisted state changed' }
if ($s03Api -eq (docker compose ps -q api)) { throw 'API was not replaced' }
if ($s03Db -eq (docker compose ps -q db)) { throw 'Database was not replaced' }
'Persistence check passed'
```

Normal `docker compose down` removes containers/network and retains `jarvis_database`; the next `up` reuses it. `docker compose stop` / `docker compose start` also preserve state. Never add `--volumes` to the application shutdown command when retaining records. No reset of personal data is implemented in S03.

## Isolated checks and scoped test reset

Use the standalone test configuration exactly as shown; do not merge it with the application Compose file. It creates project `jarvis-tests`, a separate PostgreSQL service/network/volume, and synthetic test-only credentials. It supplies no application credentials or application-volume mount. The test guard checks the environment, hostname, port, database name and role before any migrations or fixture cleanup, and rejects normal application settings. Tests use PostgreSQL, not SQLite or simulated persistence.

```powershell
docker compose -f compose.test.yaml config --quiet
docker compose -f compose.test.yaml run --build --rm tests
docker run --rm jarvis:local ruff check --no-cache src migrations tests
docker run --rm jarvis:local ruff format --check --no-cache src migrations tests
```

The suite rebuilds its image and migrates the test database. It deletes only test records between tests. It checks migration downgrade to an empty application schema, upgrade/repeat and metadata drift; real API/CLI service parity; stale-schema/unavailable-DB responses; pgvector; runtime privileges; atomic rollback; source identity; ownership/revision constraints; invalid states; target isolation; and simultaneous idempotent probe writes using separate connections and a barrier. Full lifecycle concurrency tests belong to later milestones.

To discard only test state and then prove fresh test startup:

```powershell
docker compose -f compose.test.yaml down --volumes
docker compose -f compose.test.yaml run --build --rm tests
```

The fixed test project owns only `jarvis-tests_test-database`. This reset does not touch `jarvis_database`. Keep the application and test project names distinct; do not override their names to collide. A host uv workflow is optional: from the repository root, use Python 3.12 and `uv sync --locked`. The supported DB verification path remains the isolated Compose command above.

## Actual S03 results

All five approved acceptance gates passed on 11 September 2026:

| Check | Observed result |
| --- | --- |
| Locked Linux build and first startup | Passed from a new `jarvis_database` volume; DB healthy, migration exited 0, API healthy. |
| Empty/repeated migrations | Upgrade from an empty application schema, repeat upgrade and `alembic check` passed. Runtime DDL and revision-table mutation were denied. |
| API/CLI shared services | HTTP and CLI readiness agreed on `0001_bootstrap` and pgvector `0.8.6`; synthetic CLI write/read matched the shared service. |
| Restart and volume persistence | Complete synthetic source/job JSON remained identical after replacing both API and DB containers. Container IDs changed; named volume remained. |
| Actual database outage/recovery | Stopped only Jarvis's DB. HTTP returned 503, CLI exited 1 with `database_unavailable`, and liveness remained 200. Combined HTTP/CLI/liveness probe took 10.15 s including CLI container startup; recovery returned ready. This is not a general latency benchmark. |
| Isolated PostgreSQL tests | 23 passed, zero warnings in the final code run. Fresh test-volume startup and scoped reset passed without changing the application probe. |
| Code hygiene | Ruff lint and formatting passed for all 11 application/migration/test Python files. Ten UTF-8 Markdown files and 98 local links/anchors passed; staged whitespace and local-credential exclusion checks passed. |

Resolved during implementation: the initial lint run found long lines; the first formatter check needed `--no-cache` for the non-root image. The first tests passed with deprecation warnings; the final path uses HTTPX's ASGI transport with explicit lifespan handling and Alembic's explicit path separator. No test failures remain. No extraction, retrieval, live-model quality, Private/Correct/Forget or UI result is claimed.

Observed runtime: Python **3.12.14**, uv **0.12.13**, PostgreSQL **17.11**, pgvector **0.8.6**. Python, uv and PostgreSQL image digests are pinned in Dockerfile/Compose. `uv.lock` contains exact package versions/hashes, including the build backend: FastAPI 0.141.1, SQLAlchemy 2.0.52, psycopg 3.3.5, Alembic 1.19.2, Typer 0.27.2, pytest 9.1.1, HTTPX 0.28.1 and Ruff 0.16.7. Resolve upgrades deliberately, rebuild, and rerun the relevant gates.

## Environment recommendation

Keep the existing Windows checkout and Docker Desktop Linux engine. Ubuntu-24.04 WSL integration is available; no second checkout or Docker daemon is required. The host's Python 3.14 is independent of the container's Python 3.12. Docker client/server 28.4.0 and Compose 2.39.2-desktop.1 were verified. S02's earlier disposable Alpine volume probe was environment evidence; S03 above establishes actual application/database behavior. [Docker WSL guidance](https://docs.docker.com/desktop/features/wsl/best-practices/)

### Implementation-chat recheck

The first implementation-chat audit on 11 September found the Linux engine stopped and some tools absent from its PATH. That historical observation was superseded by the successful host checks and S03 runs. If Docker is stopped in a later session, start Docker Desktop and confirm `docker version` shows a Linux server before proceeding.

### Dev-branch readiness check

The requested read-only coding CLI session completed in the earlier readiness milestone. The Windows CLI at `C:/Users/ASUS/AppData/Roaming/npm/codex.cmd` reported version 0.153.4 and successful ChatGPT authentication via `login status`; credential files were not opened. Its restricted nested sandbox could read the checkout but denied CLI-status/Docker-context probes. The parent session verified those under the normal Windows account using approved execution outside that sandbox. Docker operations still need the appropriate execution context; no global sandbox relaxation or Git configuration change is required.

Assistant changes/commits/pushes use `dev`; `main` stays the reviewed default branch. The user controls merging. Use `git log -1 --oneline` and compare `git rev-parse HEAD` with `git ls-remote origin refs/heads/dev` to identify and verify the published milestone commit.

## Later review contract

S04 is next: source/claim contracts and backend policy boundaries, including Private gates before personal inputs. Subsequent milestones provide import, processing, model calls, retrieval, controls and the ordinary-user UI. Provider access, retention/no-training settings and a spend ceiling must be agreed before live inference. The final acceptance still needs a clean-checkout import/UI/evaluation/reset walkthrough and exact tested release commit; S03 is not that final product gate.

Implementation references: [uv Docker integration](https://docs.astral.sh/uv/guides/integration/docker/), [pgvector installation](https://github.com/pgvector/pgvector#docker), [Compose startup ordering](https://docs.docker.com/compose/how-tos/startup-order/), [FastAPI containers](https://fastapi.tiangolo.com/deployment/docker/).
