# Run and verify the backend

S04 is implemented and checked on 11 September 2026 in the existing Windows checkout using Docker Desktop Linux containers. Typed evidence contracts and Normal/Private gates extend the S03 foundation; the isolated suite now has 75 passing checks. Use the synthetic fixtures below. General corpus import, a processing worker, models, retrieval, UI and complete Correct/Forget are not implemented.

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

Check `$LASTEXITCODE` after Docker/CLI commands; nonzero means failure. PowerShell does not automatically stop on native command failures. `/health` and `jarvis health` report process liveness without querying personal data or the database. `/ready` and `jarvis ready` call the same service to verify the DB connection, Alembic revision and pgvector extension. Expected readiness is `{"status":"ready","schema":"0002_evidence_contracts","pgvector":"0.8.6"}`. Readiness failures return HTTP 503 / CLI exit 1 with a short category, without raw database errors or credentials.

The API is published only on `127.0.0.1`; PostgreSQL has no published host port. The server owns the fixed local identity. No endpoint accepts an owner selector or durable user-content writes. S04 adds validation-only POST endpoints that return a fixed receipt without echoing the input. Application containers run as UID 10001. Source is copied into the image, so rebuild after code changes. uv and the build backend use the checked-in lock; the development checks are included in the same image for this milestone.

## Migrations and schema effects

On an empty named volume, `docker/postgres/init-db.sh` creates the pgvector extension, the `jarvis` schema, a migration login and a separate runtime login. PostgreSQL's administrator handles the extension because it requires elevated database privileges. The migration role owns only the application schema; the runtime role has DML on application records and read-only access to Alembic's revision table, with no DDL, superuser, role-creation or database-creation privileges.

Compose waits for DB health, runs the one-shot `migrate` service, then starts the API. To repeat/check migrations explicitly:

```powershell
docker compose run --rm migrate alembic upgrade head
docker compose run --rm migrate alembic current
docker compose run --rm migrate alembic check
```

Revision `0001_bootstrap` creates `jarvis.policies`, `jarvis.sources` and `jarvis.jobs`, plus Alembic's version table. Policies store the owner and nonnegative revision. Sources pair raw/formatted text, source identity/revision, SHA-256 and actual import time; supplied capture time/metadata remain nullable. The hash covers a UTF-8 JSON pair and does not define observation identity. Jobs have an owner-scoped idempotency key, pending status, attempts, and expected source/policy revisions. A composite foreign key requires the job to match its source's owner and revision. There are no embeddings, vector columns or search indexes yet.

The synthetic service creates the source and pending job in one transaction under the owner's policy-row lock. It cannot process the job. S04 now gates every implemented personal-store service operation, but complete Correct/Forget and UI session behavior remain later work. Future schema changes need a new reviewed migration; do not edit an applied migration to change its meaning.

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

## S04 contracts and policy checks

`contracts.py` defines strict source input, stored observations, exact passages and claim revisions. API and CLI resolve the fixed local owner through the same `LocalIdentity`; an input body cannot select the owner. Mode is explicit for contract validation: HTTP uses `X-Jarvis-Mode: normal|private`, and CLI uses `--mode normal|private`. Missing/invalid mode fails closed. Inputs are limited to 1 MiB at the adapters; text fields have tighter limits. CLI reads JSON from stdin, keeping content out of command arguments.

The observation validation command checks only the supplied current input and never saves it in either mode. Claim validation reads saved evidence in Normal; Private rejects it before parsing or opening a DB session. Neither validation receipt authorizes a later commit: the shared internal write service revalidates under the policy-row lock. There is no general importer or claim-write HTTP/CLI endpoint in this milestone.

Run the supplied synthetic observation through both adapters from PowerShell:

```powershell
docker compose run --rm --no-deps --entrypoint sh cli -c 'jarvis contracts observation --mode private < tests/fixtures/s04-observation.json'
$s04Body = [System.Text.Encoding]::UTF8.GetBytes((Get-Content -Raw -Encoding utf8 tests/fixtures/s04-observation.json))
Invoke-RestMethod -Uri http://127.0.0.1:8000/contracts/observations/validate -Method Post -ContentType 'application/json; charset=utf-8' -Headers @{'X-Jarvis-Mode'='private'} -Body $s04Body
docker compose run --rm --no-deps cli probe read --mode private
```

The first two commands return `{"status":"valid","stored":false}`. The last command intentionally exits **1** with `private_operation_denied`; it does not read the saved probe. Normal claim validation uses `POST /contracts/claims/validate` or `jarvis contracts claim --mode normal` with `ClaimWrite` JSON containing real, owned source references. The integration tests create the synthetic source through the internal service and verify API/CLI parity; the proposal fixture is not imported as a source.

All saved personal reads and writes require a Normal backend context. Private validation retains no request/session state, opens no DB session and creates no jobs, traces, retries or files. Expected errors use fixed codes; unexpected exceptions are consumed at the API/CLI boundary without input, traceback or request logging. HTTP responses use `Cache-Control: no-store`. The supported Compose API and CLI services use logging driver `none`, so even a CLI result is not saved as a container activity log. This intentionally removes persistent operational logs for these two services; migration diagnostics still appear on their command output. Host shell history, explicit caller redirection, browser behavior and future provider retention are outside this backend test boundary; this milestone uses synthetic input only and makes no browser/provider claims.

Migration `0002_evidence_contracts` adds source `kind` with `unknown` for existing records, and creates `passages`, `claim_revisions`, and `claim_evidence`. It does not rewrite existing source text, hashes, timestamps, IDs, jobs or policy revisions. Unknown/generated provenance is ineligible for claim support. New synthetic probes have explicit synthetic provenance; old probes stay unknown rather than being silently reclassified.

Passage offsets are zero-based, half-open **Python Unicode code-point** offsets into the named raw/formatted variant: `text[start:end]` must equal `exact_text`. No byte offsets, Unicode normalization, whitespace repair or fuzzy matching. Raw/formatted passages reference the same observation revision. New supported writes require the latest revision of every referenced observation. Historical source/claim revision reads remain explicit owned inspection, not a current-memory retrieval policy.

Claim content preserves subject label, attribution, typed value/units, scope, negation, modality, conditions and evidence status separately from lifecycle. Unknown times are null. Calendar dates require `YYYY-MM-DD`; instants require an explicit timezone-aware timestamp. Event time, valid-from/to and record/import time are distinct. Conditional/hypothetical/question proposals cannot be promoted to `reported`; conditions cannot be dropped. Resolved entity IDs are rejected until a backend registry exists, so similar labels do not imply shared identity. These checks enforce structure; they cannot certify that the passage semantically entails the proposal.

Source writes atomically save one observation revision and its pending job. Claim writes atomically save a claim revision, exact passages and owned evidence links. Both use the same owner policy-row lock and check expected revisions within the transaction. Source checks batch their reads; no network/model work runs under the lock. Claim appends preserve prior revisions without automatically labeling them as Correct, Forget or world-change events. Initial claim creation has no replay receipt yet; a future worker must add replay protection before enabling automatic retries. Full lifecycle transitions and importer retry/idempotency rules are later milestones.

### Actual S04 results

| Check | Observed result on 11 September 2026 |
| --- | --- |
| S03 regression | All original 23 checks pass, with expected head/table assertions updated for the additive migration. |
| Complete isolated suite | **75 passed, zero warnings** using `docker compose -f compose.test.yaml run --build --rm tests`. |
| Evidence contracts | Wrong owner/version/variant/excerpt/offset, invalid scope/time/uncertainty, fabricated entity IDs and unknown provenance rejected; explicit unknowns, paired variants, quantity units and negation preserved. |
| Atomicity | Stale validation receipts fail at commit; a late evidence conflict rolls back the entire claim. Real separate PostgreSQL connections/barriers verify both policy-lock orderings and competing claim revisions. |
| Private paths | SQL/connection and file-write interceptors report zero attempts; all personal tables/jobs match before/after snapshots. Success, malformed/oversized/schema-invalid input, timeout/unexpected exceptions, saved-operation denial and no backfill pass. No warning/error records or input-bearing output observed. |
| Existing volume upgrade | Every original S03 source/job field is identical after migration; added provenance is `unknown`. Final API/DB container replacement preserves the migrated record. |
| Live adapters | Private HTTP/CLI validation succeeds; saved-probe access is denied; HTTP no-store and actual API logging driver `none` verified. |
| Hygiene | Ruff lint/format pass for all 18 application/migration/test Python files; repeated migrations and `alembic check` report no drift. Ten UTF-8 Markdown files and 102 local links/anchors pass. No dependency/image upgrades. |

The initial expanded suite passed 71 checks; review added file-write instrumentation and Normal adapter parity, then tightened timestamp/entity validation and batched source reads. All 75 final checks pass. Early lint line-length findings were fixed. No S04 test failures remain. This is deterministic contract evidence, not extraction accuracy or live-model evaluation.

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

S05 is next: import and inspect the diagnostic observations, including safe reimport and exact source identity. S04's contracts and Private gates are now the required service boundary. Subsequent milestones provide import, processing, model calls, retrieval, controls and the ordinary-user UI. Provider access, retention/no-training settings and a spend ceiling must be agreed before live inference. The final acceptance still needs a clean-checkout import/UI/evaluation/reset walkthrough and exact tested release commit; S03 is not that final product gate.

Implementation references: [uv Docker integration](https://docs.astral.sh/uv/guides/integration/docker/), [pgvector installation](https://github.com/pgvector/pgvector#docker), [Compose startup ordering](https://docs.docker.com/compose/how-tos/startup-order/), [FastAPI containers](https://fastapi.tiangolo.com/deployment/docker/).
