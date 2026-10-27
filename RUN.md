# Run and verify

## Prerequisites

- Git, Docker Engine in **Linux container mode**, Compose v2.
- First build needs network access to Docker Hub, GHCR, PyPI and the npm registry.
- Host Python, uv and Node are **not** required to run the application. Node is only needed if you
  want to run the optional Playwright browser suite.

## Quickstart

From the repository root:

```powershell
git status --short --branch
docker compose version
Copy-Item .env.example .env
```

Set the three database passwords in `.env` before the first start. The example values are
development placeholders, not shared credentials. `.env` is ignored by Git and excluded from the image
build context. Changing it later does **not** rotate passwords already stored in the volume.

```powershell
docker compose config --quiet
docker compose build api
docker compose up -d --wait --wait-timeout 120 api worker
docker compose ps -a
Invoke-RestMethod http://127.0.0.1:8000/health
Invoke-RestMethod http://127.0.0.1:8000/ready
```

Check `$LASTEXITCODE` after Docker commands: PowerShell does not stop on native command failures.

- `/health` reports process liveness only. It queries no personal data and no database.
- `/ready` verifies the database connection, the Alembic revision and the pgvector extension, and
  returns a short failure category (HTTP 503) without raw errors or credentials.

Expected readiness on this revision:

```json
{"status":"ready","schema":"0006_turn_assessment","pgvector":"0.8.6"}
```

The API publishes only on `127.0.0.1`; PostgreSQL has no host port. If 8000 is occupied, set
`JARVIS_API_PORT` before starting and use that port in every command below.

## Browser workflow

Open **http://127.0.0.1:8000/**.

1. **Workspace connected** appears in the footer. Leave **Normal** selected for saved work, enter a
   collection name, then **Open** to read existing state. Screen navigation alone never reads saved
   data.
2. **Conversation** — type a message and press Enter, or use **Save a note** to keep an exact
   transcript (optionally with a formatted variant). A saved note does not automatically run
   extraction; **Ask** performs assessment, selective learning and then the answer.
3. **Sources** — **Try the sample** imports the eight bundled synthetic observations. **Import to
   collection** accepts your own JSONL. Browse, paginate, and inspect the exact original text and
   capture metadata.
4. **Memory** — **Refresh memories**, **Process sources**, **Retry failed**, then open a memory to see
   its revision history, uncertainty and exact supporting passages. **Correct**, **Record a world
   change** and **Forget** each show an impact preview before an explicit confirmation.
5. **Search** — lexical search over saved evidence with optional memory/history/date filters. It works
   before processing and without a provider key, and no query or result is ever learned.
6. **Usage** — source/memory/passage payload sizes, job counts, per-model token accounting and provider
   latency. Unknown usage stays unknown; reservations are not consumption and not billing.
7. **Private** — clears the Normal workspace and makes the configured model request directly, with no
   saved context and no stored transcript. Leaving Private or unloading the page clears the exchange.

The client stores nothing: no cookies, no local/session storage, no IndexedDB, no service worker, no
analytics and no third-party assets. A Normal import accepted just before switching to Private may
still commit — cancellation cannot un-write it, and the UI says so.

## Configuration

`.env.example` documents every variable. The ones that change behaviour:

| Variable | Default | Effect |
| --- | --- | --- |
| `JARVIS_API_PORT` | `8000` | Published host port for the API. |
| `JARVIS_POSTGRES_PASSWORD`, `JARVIS_MIGRATION_PASSWORD`, `JARVIS_APP_PASSWORD` | placeholders | Separate admin, migration and runtime logins. Set real values before first start. |
| `JARVIS_INFERENCE_PROVIDER` | `google` | The configured route. There is no automatic fallback. |
| `JARVIS_FREE_EXTRACTOR_MODEL`, `JARVIS_FREE_RESPONDER_MODEL` | `gemini-3.5-flash-lite` | Role defaults restored on restart. |
| `JARVIS_FREE_SYNTHETIC_TRIAL_APPROVED` | `false` | Master opt-in for the hosted provider route. |
| `JARVIS_FREE_DATA_POLICY_ACK` | empty | Must equal `I_ACCEPT_FREE_SYNTHETIC_DATA_TERMS`. |
| `JARVIS_FREE_SYNTHETIC_SOURCES_APPROVED` | `false` | Allows notes you type locally to reach that provider. |
| `JARVIS_FREE_SYNTHETIC_QUESTIONS_APPROVED` | `false` | Allows new question wording; retrieved sources are still validated. |
| `JARVIS_PRIVATE_DIRECT_APPROVED` | `false` | Enables the context-free Private request. |
| `JARVIS_MAX_REQUESTS`, `JARVIS_MAX_TOTAL_TOKENS` | `1500`, `10000000` | Ceiling of the persisted shared ledger. |

### Turning on live inference

Without any of the above, everything except hosted inference works: import, inspection, lexical
search, controls, usage, the full backend suite and the browser journey checks.

To enable hosted inference:

1. Put a supported key in `.env` (`GOOGLE_API_KEY_FREE_TIER` for the Google route).
2. Set `JARVIS_FREE_SYNTHETIC_TRIAL_APPROVED=true` **and** the exact `JARVIS_FREE_DATA_POLICY_ACK` value.
3. Enable the specific surface you actually need — sources, questions or Private — each is separate.
4. `docker compose up -d --wait api worker` to recreate the services.

Read the provider's data terms first. The free Google route may use submitted content for product
improvement and human review, so use non-sensitive data. The GitHub repository contains no keys, and
neither a repository link nor a commit SHA supplies credentials.

Verify configuration without spending a call:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/inference -Headers @{'X-Jarvis-Mode'='normal'}
```

`provider_contacted: false` means the request only reported configuration.

### Model selection in the browser

The Normal and Private composers share one explicit model list. Choosing a model calls
`POST /inference/model`, which updates both roles in the running process, performs **no** provider call
and touches no workspace data. The next submitted prompt is the first request to use it; a restart
returns to the environment defaults. The selector is not a health check — a provider can still reject
a request for account, quota or endpoint reasons, and that is surfaced as an operational failure.

## Developer CLI (optional)

Every command goes through the same service layer and requires an explicit mode.

```powershell
docker compose run --rm --no-deps cli health
docker compose run --rm --no-deps cli ready
docker compose run --rm --no-deps cli sources list --namespace diagnostic-v1 --mode normal
docker compose run --rm --no-deps --entrypoint sh cli -c 'jarvis sources import --namespace diagnostic-v1 --expected-policy-revision 0 --mode normal < data/synthetic/sample-dictations.jsonl'
docker compose run --rm --no-deps cli sources inspect <source-id> --mode normal
docker compose run --rm --no-deps cli memories --namespace diagnostic-v1 --mode normal
docker compose run --rm --no-deps cli usage --mode normal
```

Search takes a JSON body on stdin, so the query never appears in a URL or shell history:

```powershell
'{"namespace":"diagnostic-v1","query":"spending limit"}' | docker compose run --rm -T --no-deps cli search --mode normal
```

Processing requires the provider consent flags. The long-running worker service is started by Compose;
for a single bounded pass use `docker compose run --rm --no-deps cli worker --once`. A failed job keeps
its fixed error category and can be retried explicitly.

## Import contract

One JSON object per line:

```json
{"record_id":"dict_0001","raw_transcript":"…","formatted_text":"…","metadata":{"captured_at":"2026-09-01T10:00:00+05:30"}}
```

- Required: `record_id`, `raw_transcript`. Optional/null: `formatted_text`, `metadata`.
- Namespace and record ID are case-sensitive, 1–96 ASCII letters/digits/`.`/`_`/`-`. The source key is
  `import:<namespace>:<record_id>`; filenames and text hashes are not identity.
- `captured_at` must be a zoned ISO timestamp. Capture time is never inferred from import time or from
  dates mentioned in the text.
- Limits: 1 MiB UTF-8 per batch, 1,000 records, 65,536 characters per non-blank variant. Larger
  collections are split into bounded batches sharing the same namespace; each batch is atomic.
- Exact retries return the same source/job IDs. A changed field under an existing identity returns
  `import_conflict` and the whole batch rolls back.
- Rejected: unknown top-level fields, duplicate keys/record IDs, non-finite numbers, invalid UTF-8,
  NUL, naive or numeric timestamps.

## Migrations

Compose waits for database health, runs the one-shot `migrate` service, then starts the API.

```powershell
docker compose run --rm migrate alembic upgrade head
docker compose run --rm migrate alembic current
docker compose run --rm migrate alembic check
```

The first startup creates the pgvector extension, the application schema and the two logins. The
migration role owns the schema; the runtime role has DML on application tables and read-only access to
the revision table, with no DDL, superuser or role-creation rights.

## Persistence check

`docker compose down` removes containers and the network but keeps the `jarvis_database` volume.
`stop`/`start` also preserve state. Never add `--volumes` unless you intend to destroy saved data.

```powershell
$before = docker compose run --rm --no-deps cli probe write
$apiBefore = docker compose ps -q api
docker compose down
docker compose up -d --wait --wait-timeout 120 api
$after = docker compose run --rm --no-deps cli probe read
if ($before -cne $after) { throw 'Persisted state changed' }
if ($apiBefore -eq (docker compose ps -q api)) { throw 'API was not replaced' }
'Persistence check passed'
```

## Tests

The suite runs against a real, isolated PostgreSQL instance — never SQLite and never simulated
persistence. `compose.test.yaml` is a standalone project (`jarvis-tests`) with its own network, volume and
credentials, and it supplies no application credentials or provider keys. A fail-closed target guard
rejects anything that looks like the application database before any migration or fixture cleanup.

```powershell
docker compose -f compose.test.yaml config --quiet
docker compose -f compose.test.yaml run --build --rm tests
```

Lint and formatting:

```powershell
docker run --rm jarvis:local ruff check --no-cache src migrations tests
docker run --rm jarvis:local ruff format --check --no-cache src migrations tests
```

Discard only the test database and prove a fresh start:

```powershell
docker compose -f compose.test.yaml down --volumes
docker compose -f compose.test.yaml run --build --rm tests
```

### Browser journeys (optional, needs Node)

Run the backend suite first: it resets the isolated test database, and the two must not run
concurrently.

```powershell
docker compose -f compose.test.yaml stop web
docker compose -f compose.test.yaml run --build --rm tests
docker compose -f compose.test.yaml --profile browser up -d --wait --wait-timeout 120 web
npm.cmd ci --prefix tests/browser --ignore-scripts --no-audit --no-fund
Push-Location tests/browser
npx.cmd playwright install chromium
Pop-Location
npm.cmd --prefix tests/browser test
docker compose -f compose.test.yaml --profile browser stop web
```

The browser suite targets only `http://127.0.0.1:8001/`, the isolated backend. It uses synthetic data,
deterministic model doubles and fresh browser contexts, and it instruments attempted browser-storage
writes and external requests. Screenshots go to the ignored `.tmp/react-review/`.

A focused case:

```powershell
Push-Location tests/browser
node --test --test-concurrency=1 --test-name-pattern "Private cancels pending learning" workspace.test.mjs
Pop-Location
```

## Evaluators

```powershell
# Retrieval diagnostic: lexical vs lexical+claims on a frozen authored corpus
docker compose -f compose.test.yaml run --rm tests python eval/retrieval.py

# Validate the 540-record synthetic corpus and its separate questions
docker compose run --rm --no-deps --entrypoint python cli eval/corpus.py --stage validate

# Live complete-pipeline run (consent + allowance required)
docker compose run --rm --no-deps --entrypoint python cli eval/corpus.py --stage all --namespace corpus-evaluation --repeats 1 --case-limit 60 --representations both
```

`--stage extract` and `--stage answers` allow separate checkpoints; `--retry-failed` is explicit;
`--max-jobs`, `--max-new-calls`, `--case-limit`, `--split`, `--representations` and `--repeats` bound
the work. Reusing a namespace preserves successful processing. Nothing resets the persisted allowance
to buy extra attempts.

## Troubleshooting

| Symptom | Cause and action |
| --- | --- |
| Ask says the allowance is exhausted and metrics show 0 model calls | The persisted ledger is full. It is separate from the provider key: a direct `curl` can succeed while the application refuses. Raise the ceiling deliberately or accept the limit. Do not reset history. |
| `provider_failed` with no usage payload | Provider-side failure (account, quota, endpoint). Not missing evidence, and there is no fallback. Check `GET /inference`, then the provider's status. |
| A saved note never becomes a memory | Look at **Memory** → pending/failed sources. Learning is explicit or request-path, never a background daemon; use **Retry learning** or **Process sources**. |
| `import_conflict` | A field changed under an existing namespace + record ID. Use a new observation ID rather than renaming around the conflict. |
| `/ready` returns 503 | Check migration state and the pgvector extension. The response carries a short category, not a raw error. |
| Port 8000 already in use | Set `JARVIS_API_PORT` before `docker compose up`. |
| Browser suite cannot reach the app | The suite only targets the isolated profile on port 8001; application credentials and provider keys are intentionally absent there. |

## Verified state at this revision

- Full isolated backend suite: **362 passed in 159.01 s**.
- Recovered full browser suite: **26 journeys passed in 48.49 s**.
- Ruff lint/format, Prettier, TypeScript and the Vite production build passed.
- A rebuilt API reported `ready` on schema `0006_turn_assessment`.
- Live provider runs are partial and rate-limited; see [EVALUATION.md](EVALUATION.md) for what was and
  was not completed.
