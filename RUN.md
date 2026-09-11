# Run and verify Hey Jarvis

S05 is implemented and checked on 11 September 2026 in the existing Windows checkout using Docker Desktop Linux containers. Bounded import/inspection extends the S03 foundation and S04 evidence/policy contracts; the isolated suite now has 111 passing checks. Use the included synthetic fixtures below. The user subsequently approved the minimal browser workspace below; no CLI is required for import/inspection. A processing worker, models, retrieval and complete Correct/Forget are not implemented. Milestone-specific results below retain their historical test counts and scope.

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
```

Check `$LASTEXITCODE` after Docker/CLI commands; nonzero means failure. PowerShell does not automatically stop on native command failures. `/health` and `jarvis health` report process liveness without querying personal data or the database. `/ready` and `jarvis ready` call the same service to verify the DB connection, Alembic revision and pgvector extension. Expected readiness is `{"status":"ready","schema":"0002_evidence_contracts","pgvector":"0.8.6"}`. Readiness failures return HTTP 503 / CLI exit 1 with a short category, without raw database errors or credentials.

The API is published only on `127.0.0.1`; PostgreSQL has no published host port. The server owns the fixed local identity; no endpoint accepts an owner selector. S04 validation endpoints return a receipt without echoing input. S05 import writes eligible dictations only in Normal mode, and inspection returns owned saved evidence. JSON responses explicitly declare UTF-8 so Windows PowerShell 5 decodes multilingual text correctly. Application containers run as UID 10001. Source is copied into the image, so rebuild after code changes. uv and the build backend use the checked-in lock; development checks are included in the same image.

## Browser workflow

After the setup above, open **[http://127.0.0.1:8000/](http://127.0.0.1:8000/)** (use your configured port if different). Importing and inspecting sources require no CLI, Python, Node or API key. The browser is the primary ordinary-user surface; CLI/HTTP examples later in this file are optional developer diagnostics and historical acceptance commands. Initial Compose setup remains an operator step.

1. Check that the top bar says **Workspace connected**. Leave **Normal** selected to work with saved sources.
2. Choose a **Collection name**. Use `diagnostic-v1` with the bundled synthetic sample; keep the name stable on reimport. Select **Open** to browse an existing collection, or select `data/synthetic/sample-dictations.jsonl` under **Add dictations** and choose **Import to collection**. The UI handles policy revisions; the backend rechecks them atomically.
3. Read the saved/unchanged receipt. Exact retries preserve IDs and job state. Invalid or conflicting batches show a bounded error; fix the source of a conflict instead of renaming old records. Use **Load more sources** for larger collections.
4. Select a source. Original and formatted text belong to one observation. `dict_0008` retains the ₹15,000/₹50,000 disagreement; `dict_0007` has no capture time even though its content mentions a date. **Source details** exposes original metadata and processing status. Pending means memory extraction has not run.
5. Switch to **Private**. The displayed collection/evidence and selected file are cleared; import/browsing are unavailable. Switching back does not restore them or import anything. Private conversation, Ask, Correct and Forget are not yet available; the UI makes no fabricated model/action claims.

The supported page keeps no local/session storage, cookies, IndexedDB, service worker or analytics and loads no third-party assets. Saved data loads only after an explicit Normal action. Mode changes abort pending requests and reject late responses; page hide/restoration clears context. A Normal import accepted before the switch may still commit. Cancellation cannot undo that write; safely reopen/reimport the same collection/file if the result was interrupted. Browser extensions, OS memory and explicit user screenshots are outside this application's storage guarantee.

### Browser acceptance checks

Only developers need Node/npm for these optional checks. The runtime UI has no npm dependencies. Run the backend suite first to initialize/reset the isolated test database; do not run DB reset tests concurrently with browser tests.

```powershell
docker compose -f compose.test.yaml run --build --rm tests
docker compose -f compose.test.yaml --profile browser up -d --wait --wait-timeout 120 web
npm.cmd ci --prefix tests/browser --ignore-scripts --no-audit --no-fund
Push-Location tests/browser
npx.cmd playwright install chromium
Pop-Location
npm.cmd --prefix tests/browser test
docker compose -f compose.test.yaml --profile browser stop web
```

The browser suite deliberately targets only `http://127.0.0.1:8001/`, the isolated test backend. The Compose web profile receives only test runtime credentials, with no application credentials/volume or provider keys. Playwright is pinned to 1.62.1 in a separate lockfile; `node_modules` is excluded from Git and image context. Tests use fresh browser contexts and synthetic data, with no recordings/traces. Optional synthetic screenshots: set `$env:JARVIS_UI_SCREENSHOTS='1'` for the test command; files go to ignored `.tmp/ui-review/`.

Actual results for this slice are recorded in [the UI evidence record](eval/reports/ui-foundation.json). A first browser run passed six of seven checks; the navigation test exposed a test-harness assumption that service workers exist on `about:blank`. The harness now instruments that API only where available. No application failure was concealed. Review also added bounded network timeouts and processing details, and excluded newly installed browser dependencies from the Docker build context. The original application source/job schema and provider configuration are unchanged.

Final results on 11 September: **112 isolated PostgreSQL checks passed in 10.22 s, zero warnings; all 8 Chromium checks passed in 4.44 s**. Desktop (1440×1100) and mobile (390×844) screenshots were visually reviewed. Ruff lint and formatting passed for all 21 Python files; frontend formatting and `npm ci` passed. The final image contains neither `node_modules` nor `.env`. The documented application start replaced the API container successfully; `/` and `/ready` respond, all eight diagnostic source/job inspection objects match their pre-upgrade state, and the original S03 probe remains unchanged. No application volume was reset and no live model request was made.

## Migrations and schema effects

On an empty named volume, `docker/postgres/init-db.sh` creates the pgvector extension, the `jarvis` schema, a migration login and a separate runtime login. PostgreSQL's administrator handles the extension because it requires elevated database privileges. The migration role owns only the application schema; the runtime role has DML on application records and read-only access to Alembic's revision table, with no DDL, superuser, role-creation or database-creation privileges.

Compose waits for DB health, runs the one-shot `migrate` service, then starts the API. To repeat/check migrations explicitly:

```powershell
docker compose run --rm migrate alembic upgrade head
docker compose run --rm migrate alembic current
docker compose run --rm migrate alembic check
```

Revision `0001_bootstrap` creates `jarvis.policies`, `jarvis.sources` and `jarvis.jobs`, plus Alembic's version table. Policies store the owner and nonnegative revision. Sources pair raw/formatted text, source identity/revision, SHA-256 and actual import time; supplied capture time/metadata remain nullable. The hash covers a UTF-8 JSON pair and does not define observation identity. Jobs have an owner-scoped idempotency key, pending status, attempts, and expected source/policy revisions. A composite foreign key requires the job to match its source's owner and revision. There are no embeddings, vector columns or search indexes yet.

The synthetic service creates the source and pending job in one transaction under the owner's policy-row lock. It cannot process the job. S04 gates every implemented personal-store service operation. The early UI slice adds session clearing above; complete Correct/Forget remains later work. Future schema changes need a new reviewed migration; do not edit an applied migration to change its meaning.

## Verify persistence

The `probe` CLI accepts no personal input: it writes one fixed synthetic observation and returns all saved source/job fields. Repeated writes return that record without duplicating it. S05 import/inspection commands are documented separately below.

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

## S05 import and inspection

The [browser workflow](#browser-workflow) is the primary user path. The contract and commands below remain for optional developer checks; users do not need to enter them.

Only import records you intend to retain in Normal mode. The included [JSONL](data/synthetic/sample-dictations.jsonl) contains eight synthetic observations; [evaluation questions/labels](eval/fixtures/sample-evaluation-cases.json) are separate and must never be supplied as source input. Docker copies only these named curated files, not private imports or evaluator runs.

Each JSONL line is an object with required `record_id` and `raw_transcript`, optional/null `formatted_text`, and optional/null `metadata` object. Namespace and record ID are case-sensitive, 1–96 ASCII letters/digits/`.`/`_`/`-`, starting with a letter or digit. Keep the namespace stable for the same original collection, and retain original record IDs across exports/retries; filenames/text hashes are not identity. A source key is `import:<namespace>:<record_id>`, owned by the backend's local user. No owner, source kind or revision selector is accepted inside records.

Preserve text exactly, including whitespace, combining characters and raw/formatted disagreements. Optional metadata is retained; `{}` and null stay distinct. `metadata.captured_at`, when present/non-null, must be a zoned ISO timestamp such as `2026-09-01T10:00:00+05:30`. The typed capture time represents that instant; original metadata retains the supplied string. No capture/event time is inferred from import time or dates mentioned in text. Only exact supporting passages count as structurally valid references; offsets are zero-based, half-open Unicode code points.

Limits: 1 MiB UTF-8 per batch, up to 1,000 records, up to 65,536 characters per nonblank text variant. Split larger collections into bounded batches using the **same namespace**; each batch is atomic. Optional UTF-8 BOM, CRLF and blank lines are accepted. Duplicate JSON keys/record IDs, unknown top-level fields, non-finite numbers, invalid UTF-8, NUL and naive/numeric capture timestamps are rejected. This importer accepts supplied dictations; it does not extract facts, execute embedded instructions or certify provenance/semantic truth.

Inspect the current policy revision before import (zero for an untouched owner). A stale revision is rejected even for an exact retry. The CLI reads UTF-8 bytes from stdin; redirect inside the Linux container for the bundled fixture so legacy PowerShell piping cannot alter its encoding:

```powershell
docker compose run --rm --no-deps cli sources list --namespace diagnostic-v1 --mode normal
docker compose run --rm --no-deps --entrypoint sh cli -c 'jarvis sources import --namespace diagnostic-v1 --expected-policy-revision 0 --mode normal < data/synthetic/sample-dictations.jsonl'
$page = docker compose run --rm --no-deps cli sources list --namespace diagnostic-v1 --mode normal | ConvertFrom-Json
$sourceId = $page.observations[0].id
docker compose run --rm --no-deps cli sources inspect $sourceId --mode normal
```

For an unfamiliar host JSONL file, the API accepts its bytes without a bind mount or shell text conversion. This example uses the same synthetic fixture; replace only the filename/namespace and use the returned current policy revision for another collection:

```powershell
$headers = @{'X-Jarvis-Mode'='normal'}
$bytes = [System.IO.File]::ReadAllBytes((Join-Path (Get-Location) 'data/synthetic/sample-dictations.jsonl'))
Invoke-RestMethod 'http://127.0.0.1:8000/sources/import?namespace=diagnostic-v1&expected_policy_revision=0' -Method Post -Headers $headers -ContentType 'application/x-ndjson; charset=utf-8' -Body $bytes
$page = Invoke-RestMethod 'http://127.0.0.1:8000/sources?namespace=diagnostic-v1&limit=50' -Headers $headers
$sourceId = $page.observations[0].id
Invoke-RestMethod "http://127.0.0.1:8000/sources/$sourceId" -Headers $headers
```

Listing returns summaries, current policy revision and `next_after`; use it as CLI `--after` or API `after` for the next page. Limit defaults to 50 and cannot exceed 100. Inspection returns the complete observation, latest revision and ingestion job state. A pending job means saved but **not processed**. API/CLI requests require explicit mode; an owner header never overrides backend identity.

The first import reports `created: 8, unchanged: 0`; exact retries report `created: 0, unchanged: 8` with the same source/job IDs, timestamps, revisions, attempts and status. JSON object order/numeric notation does not change metadata meaning; booleans remain distinct from numbers. Changed text or metadata under the same identity returns HTTP 409 / CLI exit 1 with `import_conflict`; the entire batch is rolled back. Reimport never silently updates a source or requeues a failed job. Corrected exports need a later explicit revision/control workflow; do not work around a conflict by renaming an existing observation.

Private import/list/inspect return `private_operation_denied` (HTTP 403 / CLI exit 1) before reading import bodies/stdin or accessing the personal store. Missing/invalid mode and input return bounded errors without content/tracebacks. The API sets `Cache-Control: no-store`; API/CLI container logging remains disabled. The early UI slice adds browser context clearing above; complete conversation/control behavior and provider retention remain later work.

To repeat the complete source/job persistence comparison for the listed diagnostic page (the separate S03 probe comparison is above):

```powershell
$savedSources = @{}
foreach ($item in $page.observations) {
    $savedSources[$item.id] = docker compose run --rm --no-deps cli sources inspect $item.id --mode normal
    if ($LASTEXITCODE -ne 0) { throw 'Source inspection failed' }
}
$apiBefore = docker compose ps -q api
$dbBefore = docker compose ps -q db
docker compose down
if ($LASTEXITCODE -ne 0) { throw 'Container removal failed' }
docker compose up -d --wait --wait-timeout 120 api
if ($LASTEXITCODE -ne 0) { throw 'Container replacement failed' }
if ($apiBefore -eq (docker compose ps -q api) -or $dbBefore -eq (docker compose ps -q db)) { throw 'Containers were not replaced' }
foreach ($item in $page.observations) {
    $after = docker compose run --rm --no-deps cli sources inspect $item.id --mode normal
    if ($LASTEXITCODE -ne 0 -or $savedSources[$item.id] -cne $after) { throw 'Source/job state changed' }
}
'Source/job persistence passed'
```

### Actual S05 results

The final isolated run passed **111 tests with zero warnings**, including all S03/S04 checks. The suite imports all eight observations, verifies every raw/formatted pair and the 11 evaluator excerpts, and keeps questions/labels out of stored sources. It checks Unicode and missing metadata, distinct equal-text identities, complete-state reimport stability, malformed/oversized input before DB access, metadata conflicts, owner isolation, pagination, late job-failure rollback, policy revisions, concurrent idempotent imports and the policy lock using separate PostgreSQL connections/barriers. Private adapters refuse even a body/stdin stream that would throw if read; DB/SQL/file-write instrumentation stays at zero and durable snapshots remain identical.

The actual application run used the startup/migration commands above, CLI import/list/inspect, API byte import and source inspection, then `docker compose down` and `docker compose up -d --wait --wait-timeout 120 api`. All eight complete source/job inspections and the original S03 probe were compared before/after replacing both API and DB containers. Exact reimport remains unchanged after restart. The `jarvis_database` volume is retained; no S03/S04 schema/data migration was needed. Alembic upgrade/check and Ruff lint/format pass.

The first Windows application comparison exposed a real encoding issue: PowerShell 5 decoded a JSON response without a charset as single-byte text, corrupting the displayed rupee symbol while the stored text and UTF-8 client were correct. Explicit UTF-8 JSON response headers fixed it; the documented PowerShell commands were rerun. Self-review also fixed numeric-notation reimport comparisons and selected the original ingestion job explicitly. An initial unused-import lint finding was removed. No failed check remains hidden behind the final result. [Reproducible evidence record](eval/reports/s05-infrastructure.json)

Scope limits: eight synthetic observations, no measured live-model/semantic answer quality, no extraction worker, embeddings/retrieval, UI, automatic source correction or complete Correct/Forget/no-resurrection behavior. A repeated import under a **different** namespace is a different declared collection; cross-import duplicate/exclusion controls remain S09. The next milestone is S06 source-history answering through Kimi K3 after bounded approval and provider/settings/budget readiness.

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

Assistant implementation commits/pushes use `dev`; `main` stays the reviewed default branch. The user controls merging and explicitly authorized merging/pushing the completed S05 work. Use `git log -1 --oneline` and compare `git rev-parse dev` / `git rev-parse main` with `git ls-remote origin refs/heads/dev refs/heads/main` to verify the published tips.

## S06 readiness audit

Actual audit on 11 September 2026, before S06 implementation. Audited application commit: `a599414b431783661f54aff2c542a11ebeb0e78a` (completed S05). The existing checkout was clean on `dev`; a fetch and remote-tip check showed both `origin/dev` and `origin/main` at that exact commit. The user explicitly authorized this audit checkpoint's publication to `main`; subsequent implementation stays on `dev`.

Read AGENTS, tracker and all seven planning/run documents; extracted the full text of the 18-page [visual guide](output/pdf/jarvis-memory-visual-guide.pdf), rendered every page with PyMuPDF, reviewed all three contact sheets and inspected the evaluation page at full size. Read-only PDF inspection leaves the original snapshot unchanged.

| Guide reference | Implementation/evidence and remaining boundary |
| --- | --- |
| 03.B–03.F, 03.H–03.K | Shared API/CLI services, PostgreSQL, ordered migration startup and isolated test DB are implemented. UI, workers and model adapters remain later work. |
| 04.A–04.H, page 5 | Paired variants, exact owned/versioned passages, typed scope/uncertainty/time and unknown metadata are preserved. These checks do not establish semantic entailment. |
| 06.A–06.E, 06.G, 06.I; 07.G | Import/policy validation, atomic source/job writes and idempotent reimport are implemented. Live extraction, reconciliation and searchable derived views are pending. |
| Page 12; 14.A–14.G and 14.I | Existing Private routes gate input/store access and durable activity. Real PostgreSQL barriers check guarded writes. Provider privacy and buffered reply publication are not yet implemented. |
| Pages 8–11; 16.B and 16.D | Source-history answers, real model calls and the all-history baseline are S06 work; retrieval improvements are S08. PDF DeepSeek labels on pages 9–11 and 16 are superseded by Kimi K3. |
| Pages 13 and 15–18 | Complete Correct/Forget/repair, UI, expanded corpus and repeated live evaluation remain later gates. Page 18's pending bootstrap status and implementation-pending footers are historical, not current status. |

Fresh commands/results against the audited source:

```powershell
docker compose -f compose.test.yaml run --build --rm tests
docker run --rm jarvis:local ruff check --no-cache src migrations tests
docker run --rm jarvis:local ruff format --check --no-cache src migrations tests
docker compose run --rm migrate alembic check
git ls-remote origin refs/heads/dev refs/heads/main
```

Results: **111 tests passed in 12.56 s, zero warnings**; lint passed; all 20 Python files passed formatting; application migration check returned `No new upgrade operations detected.` Docker server is Linux 28.4.0, application API/database are healthy, and migration exited successfully. The isolated suite rechecks empty/repeated migrations and existing S03–S05 contracts. Earlier actual container replacement/persistence evidence remains in the S03–S05 sections; it was not repeated or relabeled as a new persistence experiment in this documentation-only audit.

Local configuration inspection reported `KIMI_K3_API_KEY`, `NEMOTRON_30B_API_KEY` and `NEMOTRON_550B_API_KEY` present with NVIDIA key prefixes, and no malformed environment projects. Only names/presence were emitted; no key values were displayed, staged or sent to a provider. This is not credential authentication or evidence of account quota. The API/CLI currently do not consume these keys. Live inference remains blocked by the provider-terms/budget decision in [DECISIONS.md](DECISIONS.md#s06-readiness-decisions); no S06 live result is claimed.

Review conclusion: continue with the existing architecture and [bounded S06 proposal](PLAN.md#s06-bounded-bootstrap-proposal). The no-training conflict is a real open gate, not an infrastructure failure. Phase One final files are still held separately by the author and have not been mechanically verified here. Full product acceptance remains S12.

## Input-to-memory research checkpoint

On 12 September 2026, reviewed the current Markdown, parent planning/brief and relevant pages of the existing visual PDF against primary research and PostgreSQL/pgvector documentation. Updated DECISIONS, ARCHITECTURE, EVALUATION, PLAN and todo with the rationale and pending S07 proposal. No application, dependency, migration, PDF or provider configuration changed; no model calls or new runtime tests ran. The last completed runtime evidence remains 112 backend and 8 browser checks in the UI milestone.

Actual documentation checks from the existing checkout:

```powershell
python .tmp/s03_check_docs.py
git diff --check
```

The existing local audit helper passed: 10 UTF-8 Markdown files, 141 local links/anchors, unchanged Phase One notes/drafts, and no local credentials/runtime artifacts staged. Whitespace checks passed. The helper is an ignored local audit tool, not a fresh-checkout runtime dependency. Review the staged Markdown diff, rerun the staged checks and commit/push this documentation checkpoint to `dev`; verify the remote hash. S07 and live-provider approval remain open.

## Later review contract

S06 is next: produce a source-history answer through Kimi K3 using the S05 stored evidence and S04 policy boundary. Connect source-history Ask to the existing browser UI as part of S06. Subsequent milestones provide processing, selective memory, retrieval and full controls in that same surface; keep CLI commands optional for developers. Provider access, retention/no-training settings and a spend ceiling must be agreed before live inference. The final acceptance still needs a clean-checkout import/UI/evaluation/reset walkthrough and exact tested release commit; S05 is not that final product gate.

Implementation references: [uv Docker integration](https://docs.astral.sh/uv/guides/integration/docker/), [pgvector installation](https://github.com/pgvector/pgvector#docker), [Compose startup ordering](https://docs.docker.com/compose/how-tos/startup-order/), [FastAPI containers](https://fastapi.tiangolo.com/deployment/docker/).
