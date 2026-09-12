# Run and verify Hey Jarvis

S03-S10 local infrastructure, source import, memory contracts, Search, Ask/controls and usage inspection are implemented in the Windows checkout with Docker Linux containers. The browser is the primary workflow. Tonight's recheck passed **232 backend tests and 22 browser journeys**. **Live quality is not passed:** Nemotron's recorded outputs lose meaning; seven Kimi attempts have completed no answer. Unattended inference remains off. The tonight section below supersedes historical status/usage notes. The user confirmed the submission deadline as **Saturday, 12 September 2026, 23:30 IST**.

## Tonight readiness check

The user requested restoring the whole project and assessing readiness before tonight's deadline. Baseline checkout: `7a6b03683575e86b5950a529538d1ac4513274a0` on clean dev. Docker Desktop Linux was stopped; after starting it under the host account, Docker 28.4.0 became available. Rebuilt the pinned image, retained the existing application volume and restored API/database readiness on `0005_user_controls`, pgvector 0.8.6. The application was opened at [http://127.0.0.1:8000/](http://127.0.0.1:8000/). Initial aggregate state: 33 source/job rows and three claim revisions; this was not a fresh complete-field persistence comparison.

Actual checks: 232 isolated PostgreSQL tests passed in 127.65 s; 22 Chromium journeys passed in 42.603 s; Python lint/format passed for 45 files; frontend formatting, TypeScript and Vite production build passed (13.92 s Vite build); application migration drift returned no new operations and API/CLI readiness agreed. The full backend/browser suites preceded the evaluator-only fix below; application code did not change. Updated evaluator lint/format passed separately.

```powershell
docker compose build api
$env:JARVIS_S07_SYNTHETIC_TRIAL_APPROVED = 'false'
docker compose up -d --wait --wait-timeout 120 api
docker compose -f compose.test.yaml stop web
docker compose -f compose.test.yaml run --rm tests
docker compose -f compose.test.yaml run --rm --no-deps tests ruff check --no-cache src migrations tests eval
docker compose -f compose.test.yaml run --rm --no-deps tests ruff format --check --no-cache src migrations tests eval
npm.cmd --prefix frontend run format:check
npm.cmd --prefix frontend run build
docker compose run --rm --no-deps migrate alembic check
docker compose run --rm --no-deps cli ready
docker compose -f compose.test.yaml --profile browser up -d --wait --wait-timeout 120 web
npm.cmd --prefix tests/browser test
```

The first post-browser retrieval diagnostic failed during deterministic preparation. It reused the default synthetic owner while the browser worker was active; that owner also retained 30 source exclusions, four passage exclusions, three controls and policy revision 3. A collection namespace does not isolate owner-wide Forget or worker leases. `eval/retrieval.py` now uses a fresh backend-issued synthetic owner per run, matching `eval/efficiency.py`. It still refuses the application DB, uses the same fixtures/questions/budgets and changes no runtime authorization or exclusions. The report clarifies that global isolated-DB totals include other test owners and removes a stale pre-S09 limitation.

Both corrected 500-record diagnostics found all required evidence in 45/45 answerable attempts per representation, with 100% exact required-passage coverage. The first ran with the browser worker stopped; the second ran with it active and the old owner's exclusions retained. Source-only stayed smaller and faster in these samples. The first had p50 125.577 ms versus 243.481 ms; the active-worker run had 136.582 ms versus 286.972 ms. These are authored retrieval diagnostics with deterministic claims and warm/shared test allocation, not the varied S11 corpus or a live semantic score. The source patch was mounted read-only into the existing image for those two runs, then packaged by rebuilding the image.

```powershell
docker compose -f compose.test.yaml run --rm --no-deps tests python eval/retrieval.py
```

Three new live requests were made within the existing synthetic-only allowance. The first repeated the unchanged Kimi answer smoke against the recorded eight-source collection and failed at 180.344 s model-stage time. The second used the identical service/settings/accounting path with an evaluator-only HTTPX transport observer; it recorded **ReadTimeout while waiting for response headers**, 180.187 s. It recorded exception class/status only, never request headers, keys, prompts or hidden reasoning. No HTTP 202 was observed. NVIDIA documents [202 status polling](https://docs.api.nvidia.com/nim/reference/moonshotai-kimi-k3-statuspolling), but that protocol path is not established as the cause or cure of these observed timeouts.

```powershell
docker compose run --rm --no-deps --entrypoint python -e JARVIS_S07_SYNTHETIC_TRIAL_APPROVED=true cli eval/live.py --stage answer-smoke --namespace live-279608e17b0b435fa46977d3bfe61f79 --repeats 1
```

The third request imported only the exact public `dict_0001` into a new diagnostic collection, explicitly processed one job through the normal service/worker, and disabled the responder in that one-off evaluator. Nemotron returned a structurally accepted claim in **14.546 s**, using 2,290 input and 322 output tokens. Manual semantic review: the planned date, Atlas scope and user attribution survived, but `time.event` was incorrectly set to the planned launch date without separate support. This is another semantic miss, not a passed extraction repeat. The new source/claim remains inspectable in `tonight-extractor-a8694e2fb1754074bd14f2eb48096bf3`; no personal input was used.

Lifetime state after these probes: **22 requests; 27,850 known input + 2,266 known output tokens; 211,424 accounted tokens including unknown reservations**. Kimi has seven failures and no completed answer. The allowance remains 96 requests/1,500,000 tokens/$0 paid, with no reset, fallback or persistent live-enable change. The current synthetic allowlist and 64-active-claim/60,000-byte extraction context caps must be addressed in reviewed S11 work before claiming complete larger-corpus processing.

[Readiness and semantic review](eval/reports/tonight-readiness.json), [raw Kimi smoke](eval/reports/tonight-live-smoke.jsonl), [transport probe](eval/reports/tonight-transport-probe.jsonl), [Nemotron probe](eval/reports/tonight-extractor-probe.jsonl), [retrieval rerun](eval/reports/tonight-retrieval.json), [active-worker rerun](eval/reports/tonight-retrieval-concurrent.json). Setup is complete; live-quality and acceptance gates remain open. The [next repair proposal](PLAN.md#tonight-bounded-repair-proposal) requires approval before changing model/provider behavior. No main merge, application-volume reset or final S12 clean-checkout rehearsal was performed.

## S10 usage and performance

Open [the local application](http://127.0.0.1:8000). Choose a collection and select **Sources > Try the sample**. This explicitly imports the eight original paired records through the same atomic service as file upload; retries preserve identity, and importing does not start model calls. Sources/Search need no provider. Processing, Ask, history and controls use the existing workflow below; live failures remain visible.

Expand **Usage and performance**, then **Refresh usage**. The snapshot covers all the current owner's collections, including retained source/claim history, not just the open collection. It shows source/claim/passage payload bytes, revision/job counts and model attempts grouped by role/model/allowance. Known input/output tokens, unknown usage and conservative reservations are separate. New failed calls retain provider elapsed time; historical missing durations remain null. p50/p95 shows the number of timed attempts, including failures. Successful application checks are not semantic grades. Billed/estimated cost is unmeasured, and totals are not account-wide or per-key billing.

Each Normal action also shows browser duration and fixed-name server stages via `Server-Timing`. These durations include nested work and must not be added as independent phases. Measurements have no new durable activity table or browser storage; switching collection/mode or navigating clears the display and ignores late results. Private forbids usage/source reads. RAM and physical allocation are measured separately in the evaluator report; the application has no Docker socket.

Actual verification commands, from the project root in PowerShell (check native exit codes):

```powershell
docker compose -f compose.test.yaml stop web
docker compose -f compose.test.yaml build tests
docker compose -f compose.test.yaml run --rm tests
docker compose -f compose.test.yaml run --rm --no-deps tests ruff check --no-cache src tests eval migrations
docker compose -f compose.test.yaml run --rm --no-deps tests ruff format --no-cache --check src tests eval migrations
docker compose -f compose.test.yaml run --rm --no-deps -v "${PWD}/eval/reports:/reports" tests python -m eval.efficiency --output /reports/s10-efficiency-final.json
docker compose -f compose.test.yaml --profile browser up -d --wait --wait-timeout 120 web
npm.cmd --prefix tests/browser test
# Targeted display/wait regression, from tests/browser:
# node --test --test-concurrency=1 --test-name-pattern=S10 workspace.test.mjs
```

Results: **232/232 backend tests in 134.08 s; 17/17 Chromium checks in 32.66 s; final S10 2/2 in 3.65 s**. Ruff lint and formatting pass for 45 Python files. The tests exercise owner isolation, actual Unicode UTF-8 bytes, read-only snapshots, API/CLI parity, Private zero store/write access, fixed failures, concurrent/nested timing isolation, failed usage reservations, atomic lifecycle behavior and browser storage/late-response guards. Desktop 1440x1100 and mobile 390x844 usage screenshots were visually inspected after correcting Windows-introduced separators. A targeted test initially read the source list before the post-import refresh completed; it now waits for rows. The initial formatter cache was unwritable; checks explicitly use `--no-cache`. These failures were resolved, not counted as successful runs. Final documentation/staging checks passed for 10 UTF-8 Markdown files, 178 local links/anchors, all S10 JSON/JSONL reports and staged whitespace; Phase One material is unchanged, and no local credentials/runtime artifacts are staged.

The isolated evaluator performs 17 measured actions through the actual shared services using explicit model doubles: import eight records, queue, process eight sources, repeat each retrieval representation three times and produce a cited contract answer. [First measurement](eval/reports/s10-efficiency.json) and [final-source measurement](eval/reports/s10-efficiency-final.json) retain their implementation hashes and actual results. Each fresh owner has 1,277 source-text bytes, 4,760 claim-JSON bytes across 12 revisions, and 720 passage-text bytes. Final-run database allocation grew 32,768 bytes on a preexisting isolated DB; the earlier run grew 73,728 bytes. Do not treat allocation granularity or these fixture sizes as a compression ratio. Final evaluator RSS samples were 87,977,984-91,500,544 bytes; process CPU and cumulative peak RSS are in the report. OS resource counters are sampled separately and are not per-object allocation. Double-provider tokens/latency are fixture constants, not live provider measurements or semantic scores.

One new live answer smoke ran against the existing public synthetic collection; no new extraction or full comparison was launched:

```powershell
docker compose run --rm --no-deps --entrypoint python -e JARVIS_S07_SYNTHETIC_TRIAL_APPROVED=true cli eval/live.py --stage answer-smoke --namespace live-279608e17b0b435fa46977d3bfe61f79 --repeats 1
```

The recorded namespace identifies this existing checkout's S09 collection; it is not present in a fresh clone until imported/processed. During implementation the updated evaluator was mounted read-only while its image rebuilt. The [raw public smoke record](eval/reports/s10-live-smoke.jsonl) retains `provider_failed`, 180,418.8 ms model stage, 147.7 ms context preparation and unknown usage. The failed call reserves 14,513 tokens. Lifetime usage is now **19 requests, 25,560 known input + 1,944 known output tokens, and 179,786 accounted tokens including unknown reservations**. Kimi has five attempts with no completed answer; this run establishes failure-path timing, not model quality. The existing 96-request / 1,500,000-token / $0-paid allowance remains unchanged, with no reset or Ultra fallback. `.env` is unchanged and unattended inference remains off.

Application verification:

```powershell
docker compose build api
docker compose run --rm migrate alembic check
docker compose down # no --volumes
docker compose up -d --wait --wait-timeout 120 api
docker compose run --rm --no-deps cli ready
Invoke-RestMethod http://127.0.0.1:8000/ready
Invoke-RestMethod -Headers @{ 'X-Jarvis-Mode' = 'normal' } http://127.0.0.1:8000/usage
docker stats jarvis-api-1 jarvis-db-1 --no-stream --format json
```

No new migration/dependency. Alembic detects no new operations; repeated startup migrations and API/CLI readiness agree on `0005_user_controls`, pgvector `0.8.6`. All fields in all 14 canonical application tables compare equal before/after replacement, including 33 sources/jobs, three claim/evidence records, six processing receipts, 19 calls and the budget. Before the controlled comparison, the application/test containers were observed stopped with exit 255; one snapshot failed to resolve `db`. Restoring only these project databases recovered state, and the subsequent controlled comparison passed. No application volume was reset.

[Actual application counters and container sample](eval/reports/s10-runtime.json) show API 81.7 MiB and database 25.14 MiB at one post-start sample, including health checks/background activity. Docker's Linux memory value excludes inactive file cache; it is not process RSS, a per-request allocation or NVIDIA GPU memory. Cost remains null without billing/rates. [S10 acceptance record](eval/reports/s10-contracts.json) distinguishes passing local checks from open live gates.

S10's measurement/UI implementation is complete; successful live demonstration remains open. Resolve provider stability and the recorded extraction meaning failures before claiming reliable semantic memory. **S11** owns the varied 500-observation corpus, connected/independent scenario split, held-out labels and repeated semantic/efficiency evaluation described in [PLAN.md](PLAN.md#s11-corpus-and-semantic-evaluation-handoff). The existing eight-record sample and 500-record templated lexical stress set are not that corpus. Expanded live use requires an explicit allowlist/budget review; a 96-call ceiling cannot process 500 records and repeated comparisons. S12 remains the final clean-checkout acceptance rehearsal.


## S09 controls and synthetic Ask

The user approved S09 and a synthetic-only exception to the NVIDIA training/retention restriction on 12 September. Personal and Private inference remain blocked. The live ceiling is **96 requests / 1,500,000 total tokens including failures and retries / $0 paid** under the existing persisted budget key. No budget reset or Ultra fallback was applied. A later proposed increase was not applied.

Ordinary-user workflow:

1. Open the application, import the bundled `data/synthetic/sample-dictations.jsonl`, then inspect Sources or Search. These actions need no model. **Memory > Process sources** requests bounded extraction when an approved worker is running; refresh and inspect failures as well as memories. Source preservation does not depend on extraction succeeding.
2. In **Ask Jarvis**, **Try a sample question** cycles through the eight permitted public questions. **Evidence options** selects original-source search (default), sources plus memories, or all permitted history. The backend validates citations and rechecks current evidence before release. Ask needs Kimi availability; current live attempts failed. Questions, replies and generated drafts do not become memories or jobs. Drafts are never sent.
3. On a memory, select **Correct** for an interpretation error or **Record a world change** for a real-world update. Supply your statement and replacement value; review the expandable scope, subject, attribution, uncertainty, units and time fields. Blank times stay unknown. Preview the exact affected notes, then confirm. Any edit invalidates the preview. History shows `corrected` versus `superseded` predecessors. Later evidence carries the amendment even if the original is reimported under another collection name.
4. **Forget** previews all affected notes. Confirmation excludes the selected memory family's support, dependent claims and known copies/reimports from future retrieval and learning. Originals remain visible in Sources/history. Exclusion conservatively covers whole affected observations; unrelated details in those notes can become unavailable. New paraphrases are not detected. Forget is owner-wide, including copies in other collections; renaming a collection does not undo it.
5. Below an answer, **Review feedback** asks which layer failed. Vague, memory, world-change, style and operational feedback gives targeted guidance without silently changing memory. Generation/retrieval diagnoses permit one persisted rerun. It can fail and consume allowance; repeated feedback cannot create an unlimited retry chain.
6. Switch to **Private** to clear source, search, answer, control editor and feedback state. Saved reads/writes and provider calls are denied before body parsing/store access. Late responses and browser back navigation cannot restore old content. No private context is backfilled on returning to Normal.

For the exact public control demo, use `The Atlas launch plan is 2026-09-23.` and then `The Atlas launch plan is 2026-09-25.` with the full canonical content in [control-observations.json](data/synthetic/control-observations.json). These are public user-confirmed statements, not model accuracy fixtures. Arbitrary local corrections are allowed, but their personal content cannot enter this hosted trial. The full raw statement and confirmed typed interpretation must match the allowlist.

Actual commands run in this checkout (native command failures must be checked):

```powershell
docker compose -f compose.test.yaml --profile browser stop web
docker compose -f compose.test.yaml run --rm --build tests
docker compose -f compose.test.yaml run --rm tests python eval/retrieval.py
docker compose -f compose.test.yaml --profile browser up -d --wait --wait-timeout 120 web
npm.cmd --prefix tests/browser test
```

Tests are isolated from `jarvis_database`; do not reset their DB while browser checks run. The final suite passed **225 tests in 130.25 s** and **15 Chromium checks in 24.89 s**. The browser server uses explicit deterministic extraction/answer doubles with no provider keys. Desktop 1440×1100 and mobile 390×844 screenshots were visually checked; browser storage/external-request instrumentation passed. A fresh isolated database was created during this milestone; empty/repeated migrations and metadata drift pass. New tests cover exact excerpts, typed controls, cross-owner/stale previews, duplicate arrivals, reimports, both real PostgreSQL control/worker and control/reply lock orderings, feedback retry persistence, and all Private failure paths.

The actual 500-record retrieval regression retained all required passages in **45/45 answerable attempts per representation**, three runs of 17 cases, with source-only remaining the default. This is authored diagnostic coverage with deterministic claims, not live answer quality or the project's unfamiliar-corpus evaluation. [Measured retrieval results](eval/reports/s09-retrieval.json)

Application upgrade and persistence commands:

```powershell
docker compose run --rm migrate
docker compose down # no --volumes: keep the application database
docker compose up -d --wait --wait-timeout 120 api
docker compose run --rm migrate alembic check
docker compose run --rm --no-deps cli ready
Invoke-RestMethod http://127.0.0.1:8000/ready
```

Before/after snapshots compared every canonical table field, not just counts. Migration `0005_user_controls` preserved the original 17 sources/jobs and four prior call records. After live attempts, replacement of the actual API/DB containers preserved all 33 sources/jobs, three claim/evidence records, six processing receipts, 18 call records and the budget. API/CLI readiness agrees on `0005_user_controls`, pgvector `0.8.6`; Alembic reports no drift. Isolated DB/web container replacement preserved all 14 tables, including three control receipts, one feedback receipt, 26 claims, four passage exclusions and 26 source exclusions. No application volume was reset.

The explicitly approved live diagnostic used one-off flags (the ignored `.env` flag remains false):

```powershell
docker compose stop worker
docker compose run --rm --no-deps -e JARVIS_S07_SYNTHETIC_TRIAL_APPROVED=true worker python eval/live.py --stage smoke --repeats 1
docker compose run --rm --no-deps -e JARVIS_S07_SYNTHETIC_TRIAL_APPROVED=true worker python eval/live.py --stage extraction --namespace live-279608e17b0b435fa46977d3bfe61f79 --repeats 1
```

The namespace above identifies this recorded diagnostic; do not reuse it to pretend to run an independent repeat. New smoke runs create fresh namespaces. The evaluator supports `--stage answers --namespace <frozen-collection> --repeats 3` for a future approved comparison, but **that full matrix was not run** because the Kimi smoke baseline failed. Trials share the same lifetime allowance across collections and restarts. Explicit public JSON output was retained in evaluator reports; application logs contain neither prompts nor completions.

Actual live result: **18 requests; 25,560 known input tokens + 1,944 known output tokens; 165,273 accounted tokens including full reservations for unknown usage.** Nemotron: six successful contract outcomes, three schema failures and five provider failures across initial and revised attempts. One full eight-source attempt produced three memories, three `no_memory` outcomes and two operational failures. Semantic review found missed information, capture/planned times placed into event time, and a new date added without superseding the old date. Kimi: four attempts, zero completed answers. Transport diagnostics observed ReadTimeout and ConnectError; the last attempt still failed after increasing the responder wait from 90 to 180 seconds. The extractor stays at 90 seconds; both use connect=10 seconds. The UI allows 390 seconds for an answer and its one possible schema repair. This is a bounded engineering choice after observed failures, not a latency guarantee from [NVIDIA's Kimi documentation](https://docs.api.nvidia.com/nim/reference/moonshotai-kimi-k3).

[Raw public attempts](eval/reports/s09-live-attempts.json), [review of every diagnostic observation](eval/reports/s09-live-review.json), and [local acceptance record](eval/reports/s09-contracts.json) distinguish structural success, semantic failure and operational failure. No paid billing API was queried; the approved free-trial endpoint was used, with zero paid spend authorized. Unattended worker inference stays off; the application is ready for source/Search/control inspection, not a reliable live answer demo yet.

Resolved review findings: JSONB control receipts needed copied result dictionaries to persist replacement IDs; amendment ordering now uses policy revisions; exact copies carry amendments; known corrected interpretations cannot be re-added from their prior observation; failed live offset/schema outputs motivated exact unique excerpts with backend offset resolution. An old migration regression incorrectly dropped new head tables while testing index removal; it now checks the actual index migration alone. Browser selectors were narrowed for the added control buttons and cards. One attempted selector edit failed Windows default-codepage decoding and did not change files; it was rerun explicitly as UTF-8. Final review also rejected overlapping excerpt matches and malformed source IDs as validation errors. After that small parser fix, 56 targeted answer/processing checks passed in 22.33 s; the preceding full suite was 225/225 and browser suite 15/15. Ruff lint/format passed for 42 Python files; 10 UTF-8 Markdown files and 167 local links/anchors passed, with unchanged Phase One material, valid JSON evidence, clean staged whitespace and no local credentials in the staged diff. Initial failures remain documented. No dependency upgrade, dense retrieval, arbitrary provider fallback or hidden model-quality claim was introduced.

Next work is to stabilize the hosted response path and improve/re-evaluate extraction meaning before closing S06/S07/S08 live gates or expanding to S11's separate development/unfamiliar corpora. S09 implementation and local lifecycle acceptance are complete; S10 browser wiring is connected, while a successful live end-to-end demonstration remains open.

## Start from a checkout

Prerequisites: Git, Docker Engine in Linux mode, Compose v2, and initial network access to Docker Hub, GHCR, PyPI and the npm registry. Host Python/uv are unnecessary. Run these commands in PowerShell from the repository root on `dev`:

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
docker compose up -d --wait --wait-timeout 120 api worker
docker compose ps -a
Invoke-RestMethod http://127.0.0.1:8000/health
Invoke-RestMethod http://127.0.0.1:8000/ready
```

Check `$LASTEXITCODE` after Docker/CLI commands; nonzero means failure. PowerShell does not automatically stop on native command failures. `/health` and `jarvis health` report process liveness without querying personal data or the database. `/ready` and `jarvis ready` call the same service to verify the DB connection, Alembic revision and pgvector extension. Expected readiness is `{"status":"ready","schema":"0005_user_controls","pgvector":"0.8.6"}`. Readiness failures return HTTP 503 / CLI exit 1 with a short category, without raw database errors or credentials.

The API is published only on `127.0.0.1`; PostgreSQL has no published host port. The server owns the fixed local identity; no endpoint accepts an owner selector. S04 validation endpoints return a receipt without echoing input. S05 import writes eligible dictations only in Normal mode, and inspection returns owned saved evidence. JSON responses explicitly declare UTF-8 so Windows PowerShell 5 decodes multilingual text correctly. Application containers run as UID 10001. Source is copied into the image, so rebuild after code changes. uv and the build backend use the checked-in lock; development checks are included in the same image.

## Browser workflow

After the setup above, open **[http://127.0.0.1:8000/](http://127.0.0.1:8000/)** (use your configured port if different). Importing and inspecting sources require no CLI, Python, Node or API key. The browser is the primary ordinary-user surface; CLI/HTTP examples later in this file are optional developer diagnostics and historical acceptance commands. Initial Compose setup remains an operator step.

1. Check **Workspace connected** in the footer. Leave **Normal** selected for saved work. Choose a stable **Collection name**, then **Open** when you want to read existing state. Screen navigation alone does not read personal data.
2. **Conversation** welcomes you with "hey jarvis." Choose **Save a note** to type/paste a transcript and optionally add its formatted version. **Save note** preserves both exact strings as one observation. Capture time is unknown when absent. It does not automatically run extraction. A retry of unchanged input in the same page is idempotent, including after a lost response.
3. **Sources > Try the sample** imports the eight bundled synthetic dictations; use **Add dictations > Import to collection** for a JSONL file. Inspect originals and capture metadata; **Load more sources** handles pagination. Use **Search saved evidence** and its optional memory/history/date filters without a model call.
4. **Memory > Refresh memories** opens current processing and claim state. **Process sources** queues eligible observations when the provider gate is enabled; **Retry failed processing** is explicit. Select a memory to inspect its revision history and exact passages. **Correct**, **Record a world change** and **Forget** lead to **Review impact**, then explicit confirmation. Editing invalidates the preview. Forget blocks supporting notes/known copies from future use while retaining inspectable original history.
5. **Conversation > Ask with context** inserts one approved sample question; **Ask** submits it using Original sources by default, with Sources + memories or All permitted history available. Answers are buffered and shown only after backend validation, with expandable citations and feedback diagnosis. Source validation does not prove interpretation accuracy. General personal/Private inference remains blocked, and the current live provider failures are documented below.
6. **Usage > Refresh usage** shows source/memory/passage payload sizes, jobs, per-model token accounting and provider latency. Unknown usage remains unknown; reservations are not consumption or billing. Cost and semantic accuracy are unmeasured here. Current action timing is transient and nested stages must not be summed.
7. Switch **Private** to clear Normal drafts, source/answer/search/usage state and pending browser requests. The temporary scratchpad makes no API/model call. Returning to Normal or leaving/restoring the page clears its text and never backfills it. There is no microphone or voice permission.

The supported page keeps no local/session storage, cookies, IndexedDB, service worker or analytics and loads no third-party assets. Saved data loads only after an explicit Normal action. Mode changes abort pending requests and reject late responses; page hide/restoration clears context. A Normal import accepted before the switch may still commit. Cancellation cannot undo that write; safely reopen/reimport the same collection/file if the result was interrupted. Browser extensions, OS memory and explicit user screenshots are outside this application's storage guarantee.

### Browser acceptance checks

Only developers need Node/npm for these optional checks. Docker builds the locked React assets; no Node process runs in the application container. Run the backend suite first to initialize/reset the isolated test database; do not run DB reset tests concurrently with browser tests.

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

The browser suite deliberately targets only `http://127.0.0.1:8001/`, the isolated test backend. The Compose web profile receives only test runtime credentials, with no application credentials/volume or provider keys. Playwright is pinned to 1.62.1 in a separate lockfile; `node_modules` is excluded from Git and image context. Tests use fresh browser contexts and synthetic data, with no recordings/traces. Synthetic acceptance screenshots are written to ignored `.tmp/react-review/`. Source/model doubles are explicitly labeled, and those screenshots are not live-model evidence.

Actual results for this slice are recorded in [the UI evidence record](eval/reports/ui-foundation.json). A first browser run passed six of seven checks; the navigation test exposed a test-harness assumption that service workers exist on `about:blank`. The harness now instruments that API only where available. No application failure was concealed. Review also added bounded network timeouts and processing details, and excluded newly installed browser dependencies from the Docker build context. The original application source/job schema and provider configuration are unchanged.

Final results on 11 September: **112 isolated PostgreSQL checks passed in 10.22 s, zero warnings; all 8 Chromium checks passed in 4.44 s**. Desktop (1440×1100) and mobile (390×844) screenshots were visually reviewed. Ruff lint and formatting passed for all 21 Python files; frontend formatting and `npm ci` passed. The final image contains neither `node_modules` nor `.env`. The documented application start replaced the API container successfully; `/` and `/ready` respond, all eight diagnostic source/job inspection objects match their pre-upgrade state, and the original S03 probe remains unchanged. No application volume was reset and no live model request was made.

## S07 memory processing

The approved pipeline preserves original sources and writes source-linked claim revisions through the shared service. The browser adds **Memory > Process sources**, **Refresh memories**, **Retry failed**, a Memories list and expandable evidence/history. No CLI is required for these user actions. Open a collection before processing; refresh to see completed/failed jobs and zero-memory or clarification outcomes. Conditions, uncertainty and scope are visible on each memory. **View original source** opens the existing source inspector. Switching Private clears sources, memories, history and pending UI responses. Previously accepted Normal imports/jobs may finish; Private input never enters them.

**Unattended inference remains off in the delivered configuration after the S09 live failures.** Synthetic-only one-off evaluations used the approved flag and existing keys. Nemotron returned authenticated completions, some contract-valid but semantically incomplete; Kimi returned no completed answer. Imports, inspection, Search and local controls work without provider access. The isolated browser backend injects labeled deterministic providers and cannot start against the application database.

The user approved the synthetic-only trial. An operator can set `JARVIS_S07_SYNTHETIC_TRIAL_APPROVED=true` in ignored `.env` and recreate API/worker services to enable it, accepting the documented current failures. Nemotron uses `NEMOTRON_30B_API_KEY` in the worker; Kimi uses `KIMI_K3_API_KEY` in API/CLI and the evaluator worker. DB/migration/test services receive no provider keys. Exact public source/question/control fields are checked in code. The shared persisted cap is 96 requests and 1,500,000 total tokens including repairs/retries and unknown-usage reservations, $0 paid; do not reset it. General personal inference needs a new provider/settings decision.

Optional developer commands through the same service:

```powershell
docker compose run --rm --no-deps cli process --namespace diagnostic-v1 --expected-policy-revision 0 --mode normal
docker compose run --rm --no-deps cli memories --namespace diagnostic-v1 --mode normal
docker compose run --rm --no-deps worker jarvis worker --once
```

Use the current policy revision from source listing, not an assumed zero after controls change it. The first/third commands require the live gate; a failure returns a fixed category. Ordinary use is **Memory > Process sources** in the browser, with the long-running Compose worker. Failed jobs can be explicitly retried at most three lease attempts; stale/expired workers are fenced. There is at most one schema-repair call per attempt. Unknown provider usage retains its conservative token reservation. Empty/invalid model output, database failures and stale packets never silently become successful zero-memory decisions.

The older extraction-only command below remains available. S09 actually used `python eval/live.py` for the diagnostic; the [live attempts](eval/reports/s09-live-attempts.json) and [semantic review](eval/reports/s09-live-review.json) retain every call. The full three-repeat extraction/answer matrix has not passed and was not continued after the smoke failures.

```powershell
# Only after the S07 provider/allowance decision; keep unrelated workers idle for the pilot.
docker compose stop worker
docker compose run --rm --no-deps worker jarvis evaluate-extraction --repeats 3
```

It imports only the eight bundled synthetic observations into a distinct collection per repeat and processes only that collection. It emits JSON with all call outcomes, actual usage when known, saved revisions and exact support. It labels the result `ungraded` and semantic review `pending`; retain failures and review all repeats before reporting quality. No Kimi/Ultra comparison or source-history answer is produced. The existing application allowance persists across evaluator restarts and collections.

Actual acceptance results on 12 September: **156 backend tests passed in 25.87 s with zero warnings; 10 Chromium checks passed in 12.08 s.** A clean test volume initialized successfully; empty/repeated migrations and metadata drift checks passed. All ten isolated application tables matched after container replacement, including 12 claim revisions, eight receipts and eight deterministic call records. The final application restart preserved all eight original source/job inspections and every original S03 probe field. Readiness reports `0003_memory_processing`, live inference is disabled, and the application has zero model-call records. Ruff lint/format passed for 31 Python files; final desktop/mobile and memory screenshots were visually reviewed.

Resolved findings: an initial fixture-helper bracket typo prevented test collection; two older assertions expected the previous schema/service shape and now verify original fields plus safe new defaults. UI review moved uncertainty/conditions into the list, and validation review added typed duplicate checks, duplicate-JSON rejection and evaluator collection isolation. The real adapter's synthetic allowlist also passes with a simulated HTTP transport; no data was sent to NVIDIA. No runtime test failure remains; no live-model result or stronger-model comparison is claimed. Documentation checks passed for 10 UTF-8 Markdown files and 147 local links/anchors; staged whitespace/credential checks run before the `dev` commit.

Migration `0003_memory_processing` adds `requested`, lease token/expiry, finish time and fixed error category to jobs; creates `processing_receipts`, `claim_relations`, `model_budgets` and `model_calls`; and grants only runtime DML. Existing source/claim content stays unchanged, and old jobs default to unrequested with null processing fields. No vector columns/indexes or dependency versions changed. Source/claim/policy snapshots and lease identity are rechecked before the atomic claim/evidence/relationship/receipt/job commit. Model calls hold no DB locks. Raw responses, prompts and reasoning are not saved in accounting.

Actual checks and remaining limits are recorded in [the S07 evidence report](eval/reports/s07-contracts.json). Browser acceptance uses `tests/browser/server.py` with a synthetic fixture double under the isolated test-DB guard. Run the backend suite before browser checks because it resets only test state. The clean test-volume command, backend checks and browser commands are the same as the sections above/below. Private instrumentation now covers processing, worker, accounting, memory/history and report paths, including refusal before reading an HTTP body. Full Correct/Forget/exclusions and answer-quality comparisons are still later gates.

## S08 evidence search

Open the browser, import or open a collection, and use **Search saved evidence**. Try `spending limit`, `Ravi`, or `Orion`. Search works before processing and without provider keys. Results retain both original variants and link **Inspect original** to the source inspector. **Search options** enables related memories, historical memory revisions and capture-date filters in UTC; undated notes remain included by default. Original observations retain their historical wording. Private/page/collection changes clear the query, filters and results and discard late responses. No query or answer is learned, queued or persisted by search.

Source-only is the default. Related memories are optional and show attribution, scope, uncertainty, conditions and time separately from lifecycle. A memory's supporting sources travel together. No matches means the search found no lexical match; it does not prove a fact is unknown. Failures are shown separately. Large records are kept whole, with an explicit evidence-limit result instead of silently clipped conditions. Default limits are five primary matches and 24,000 serialized evidence bytes; API requests permit at most 20/64,000. These are byte limits, not model-token counts.

The optional developer command reads a JSON request from stdin; ordinary users need only the browser:

```powershell
'{"namespace":"diagnostic-v1","query":"spending limit"}' | docker compose run --rm -T --no-deps cli search --mode normal
$s08Body = [System.Text.Encoding]::UTF8.GetBytes('{"namespace":"diagnostic-v1","query":"Ravi","representation":"sources_and_memories"}')
Invoke-RestMethod http://127.0.0.1:8000/search -Method Post -ContentType 'application/json; charset=utf-8' -Headers @{'X-Jarvis-Mode'='normal'} -Body $s08Body
```

`representation` is `sources` or `sources_and_memories`; `history` defaults false. Optional `captured_from`/`captured_to` require explicit zoned timestamps; `include_undated` defaults true. Capture filters never substitute an event or import date. API queries use POST bodies, not URLs. The CLI's Normal output is explicit developer output; avoid saving private/personal terminal transcripts.

Run regressions before the isolated evaluator/browser because the backend suite resets test state:

```powershell
docker compose -f compose.test.yaml --profile browser stop web
docker compose -f compose.test.yaml run --build --rm tests
docker compose -f compose.test.yaml run --rm tests python eval/retrieval.py
docker compose -f compose.test.yaml --profile browser up -d --wait web
npm.cmd --prefix tests/browser test
```

The evaluator refuses non-test database settings. It generates a unique collection of 500 synthetic observations (15 varied originals plus 485 templated distractors), uses explicit deterministic proposals, and evaluates 17 separate labeled questions three times per representation. It prints JSON; retain output only as labeled synthetic evaluation evidence. All failed/missing evidence selections remain visible. It does not authenticate NVIDIA, generate answers, measure model tokens or run dense search. The 500-record diagnostic is not the S11 blind corpus gate.

Migration `0004_lexical_retrieval` adds only the `sources_search_idx` and `claims_search_idx` GIN expression indexes. It leaves source/job/claim/policy/accounting rows unchanged and introduces no dependency or container. These indexes rebuild automatically from canonical data on creation and track committed changes transactionally. Search filters owned eligible latest sources and valid claims before candidate limits. An excluded claim's support blocks the whole affected original observation from fallback; complete passage/known-duplicate/reimport controls remain S09.

The requested S07 merge was independently verified on remote `main` at `8eec7b9e0edc16c3e6b35cb152818c3776cd0c27` after 156 backend tests (26.17 s) and 10 browser tests (11.97 s) passed. S08 changes are made on `dev`.

**Actual S08 acceptance on 12 September:** 186 backend tests passed in 47.14 s, zero warnings, after a fresh isolated volume initialization; all 12 final browser checks passed in 12.91 s. Empty/repeated migrations and drift checks pass. Ruff passed for 35 Python files; frontend formatting passed. Desktop search and expanded mobile filters/results were visually reviewed. Actual application HTTP/CLI search returned both conflicting spending-limit variants as one observation without a model call.

Documentation checks passed for 10 UTF-8 Markdown files and 158 local links/anchors; Phase One notes/drafts remain unchanged. Staged whitespace and local-credential exclusion are checked before the `dev` commit. No `.env`, local audit probes, database snapshots or UI screenshots are committed.

Every row in all ten application tables matched after migration and database/API/worker container replacement: nine original sources, nine jobs, one policy and zero model calls. A separate isolated DB-container replacement retained all rows, including 756 sources and 37 claim revisions accumulated by the evaluator/browser runs, and the exact indexed source-plus-memory search response. These are synthetic records; the 24 isolated call rows are deterministic doubles, not provider requests. Snapshot comparisons used ignored local audit probes; canonical row preservation and indexed/unindexed result equality also have reproducible regression tests. Application volumes were never reset; only `jarvis-tests_test-database` was reset for the clean test start.

| Final diagnostic | Source-only default | Sources plus memories |
| --- | --- | --- |
| Required passages found | 60/60 | 60/60 |
| Answerable attempts with all required evidence | 45/45 | 45/45 |
| Mean serialized evidence bytes | 2,368.94 | 5,492.88 |
| Local retrieval p50 / p95 | 60.75 / 114.36 ms | 98.05 / 207.90 ms |

The [initial comparison](eval/reports/s08-retrieval-initial.json) retains the memory-fusion miss (42/45 complete evidence attempts, 95% passage coverage). The [final comparison](eval/reports/s08-retrieval-final.json) reserves the strongest original match and reruns unchanged cases/budgets. Keep source-only as the simpler default; these authored diagnostics do not establish universal optimality or model accuracy. Latencies are small local samples, potentially with warm indexes. [Full checks and limitations](eval/reports/s08-contracts.json). No test failure remains. S08's live answer-comparison gate remains open because S06 and the separately requested provider decision are incomplete.

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

Complete the missing S06 source-history answer baseline through Kimi K3 after the provider decision, connecting Ask to the browser. S07 processing and S08 evidence search already use the shared backend; full S09 controls remain next. Keep CLI commands optional. Provider access, retention/no-training settings and a spend ceiling must be explicit before live inference. Final submission still requires the complete clean-checkout import/UI/live-evaluation/reset walkthrough and exact tested release commit; local contract/retrieval checks do not close that product gate.

Implementation references: [uv Docker integration](https://docs.astral.sh/uv/guides/integration/docker/), [pgvector installation](https://github.com/pgvector/pgvector#docker), [Compose startup ordering](https://docs.docker.com/compose/how-tos/startup-order/), [FastAPI containers](https://fastapi.tiangolo.com/deployment/docker/).


## React workspace refinement

The approved React redesign replaces the legacy plain client. Its source is `frontend/`; `src/jarvis/web/` is ignored build output. The Docker build runs locked npm installation, TypeScript checking and Vite in a pinned Node 24 stage, then includes generated assets and font notices in the Python wheel. End users need Docker only. FastAPI remains the sole runtime server; existing databases, provider selection, allowance and migration head are unchanged.

Frontend-only developer checks from the repository root (Node 24, npm; Windows uses `npm.cmd`):

```powershell
npm.cmd ci --prefix frontend --no-fund
npm.cmd --prefix frontend run format:check
npm.cmd --prefix frontend run build
```

The supported integrated preview is the Compose application, not a second development server. Rebuild after frontend edits:

```powershell
docker compose build api
docker compose up -d --wait --wait-timeout 120 api
Invoke-RestMethod http://127.0.0.1:8000/ready
```

For deterministic browser verification, follow [Browser acceptance checks](#browser-acceptance-checks). Do not run database-reset tests while the isolated browser backend is serving. The full application regression suite and the browser suite use separate test credentials/volume from the application; no live provider call is needed to validate this interface. Hosted inference failures from S09/S10 remain open.


Actual results on 12 September 2026:

| Check | Result |
| --- | --- |
| Existing backend regression | 232 passed in 129.23 s, isolated PostgreSQL. |
| Final shell/nonce policy check | 1 passed in 1.49 s after the additional per-response nonce/font assertions. |
| Full Chromium suite | 22/22 passed in 37.71 s; no page errors, CSP violations, external requests, browser storage writes or cookies. Includes real PostgreSQL and deterministic providers. |
| Locked frontend install | `npm.cmd ci --no-fund`: 96 packages audited, zero reported vulnerabilities. |
| Formatting/build | `npm.cmd run format:check`, TypeScript and Vite production builds pass. Ruff lint and formatting pass for 45 Python files. |
| Bundle | JS 471.66 kB, CSS 42.08 kB; Vite gzip estimates 151.17/10.03 kB. These are build statistics, not a measured HTTP latency/compression benchmark. |
| Actual application restart | `docker compose down` without volumes, then `docker compose up -d --wait --wait-timeout 120 api` succeeded. All fields in all 14 application tables match the ignored before/after snapshots. |
| Database/runtime | Alembic check reports no new upgrade operations. API/CLI ready on `0005_user_controls`, pgvector 0.8.6. Application image contains no Node executable, node_modules or .env file. |
| Deployed browser | Actual port 8000 shell, local assets/font notices, zero personal startup reads and a 320-pixel viewport pass. Desktop/mobile synthetic screenshots were visually reviewed. |
| Live models | Zero new calls. Existing 19 requests/179,786 accounted tokens and provider/extraction failures are unchanged. |

Exact additional Python verification commands:

```powershell
docker compose -f compose.test.yaml run --rm tests ruff check --no-cache src migrations tests eval
docker compose -f compose.test.yaml run --rm tests ruff format --check --no-cache src migrations tests eval
docker compose -f compose.test.yaml run --rm tests pytest -q -p no:cacheprovider tests/integration/test_web.py
```

Stop the isolated web service before any database test. Initial frontend checks found the TypeScript 7 removal of `baseUrl` and missing Vite CSS declarations; both were fixed. An initial 517.83-kB JS bundle was reduced with Motion's smaller feature set. Two browser attempts failed only a case-sensitive assertion against CSS-uppercase history text (20/21, then 21/22); the actual assertion was corrected and the final full suite passed. Review added clearing for already-Private history restoration and revoked content after a successful control whose refresh fails; those failure paths pass. A package formatting check was corrected. Ruff initially attempted to create a cache in the unprivileged image; `--no-cache` is the supported check, and the API handler's formatting was fixed. These resolved checks are not hidden live-model successes.

[Machine-readable acceptance](eval/reports/react-workspace.json). The connected in-app browser was unavailable after its documented recovery check, so visual/interactive validation used the existing Playwright Chromium setup. No provider setting, key, budget, schema or Phase One original changed. This is a tested React interface, not a successful live-model demonstration or completion of S11/S12.

Final documentation/staging review passed for 11 UTF-8 Markdown files and 180 local links/anchors. Phase One notes/drafts are unchanged; no local credentials or runtime artifacts are staged. Frontend/test formatting and staged whitespace checks pass.

Final visual refinement brings selected memory history into view with keyboard focus and resets screen navigation scroll. After that change, the two affected memory/history/mobile-control journeys passed in 15.89 s, in addition to the preceding 22/22 full browser run. TypeScript/Vite and formatting passed again; the final local application image was recreated.

## HTML progress and walkthrough guide

On 12 September, the user requested a simple HTML progress view and a complete input-to-semantic-memory explanation for walkthrough preparation. Open [docs/project-progress.html](docs/project-progress.html) directly in a browser. No local server, Docker startup, installation, application data access or model call is required. It is a dated snapshot of todo.md at application baseline `1756069ba8c7f155060492dc008aaeea735af537`, with evidence links; todo.md remains the single maintained status checklist.

The guide covers 12 milestones, a clickable 12-stage learning diagram, actual table names, four exact-source teaching examples, retrieval and answer release, Correct/world change/Forget/Private, remaining work and 12 expandable walkthrough questions. Intended example interpretations are explicitly separate from actual failed live results. Stored embeddings, reliable Kimi answers, the varied 500-record corpus and final acceptance acceptance are not claimed. The older PDF and independently authored Phase One originals are unchanged.

Actual targeted checks used Python's standard HTMLParser and filesystem/Markdown-anchor resolution, plus the extracted inline script passed to `node --check`: UTF-8 decoding, balanced HTML/SVG tags, 33 unique IDs, all 81 static/dynamic local links and anchors, sequential diagram stages, milestone categories, four example selectors and 12 questions passed. The page has zero remote assets; a static scan found no network or browser-persistence APIs in its script. `git diff --check` passed before the documentation update. [Machine-readable results and HTML hash](eval/reports/project-progress-guide.json)

These are static documentation checks. Browser visual/interaction/print testing, application regressions, Compose/container replacement, database operations and live model evaluation were not run for this change. The guide cites the earlier 232 backend/22 browser results and recorded provider failures rather than relabeling them as new results. Documentation and staged whitespace checks accompany the dev commit/push; no application deployment or main merge is part of this scope.

## Evening evaluation preparation and LLM check

This section supersedes the earlier current-status/model/allowance descriptions, without replacing historical failures. On 12 September, the approved implementation checkpoint passed **244 PostgreSQL tests in 129.87 s**, TypeScript/Vite, Ruff and migration-drift checks. The browser suite initially passed 23/24: the new setup assertion also matched a hidden Sources panel. After the explicitly approved Conversation-only locator fix, the full suite passed **24/24 in 41.7098508 s**, without changing the assertion's requirement or application behavior. The twelve submission regressions separately passed in 4.63 s. Browser providers are deterministic doubles, not live NVIDIA. [Acceptance details and resolved failures](eval/reports/s11-implementation.json).

The full synthetic corpus contains 540 paired records and 84 separate cases: 30 showcases selected before live outcomes, 30 held-out and 24 development questions. The source hash is `6d3e35c314d55873247ffa86766320c187b1f81e822dd865a36f2dfae852c4e9`; the cases hash is `2ae99b0e2de8e6997dea32f82adb8cd2b62e1d20dbe7ae94bff6f2e6eb9bd2aa`. Counts, pairing, question separation and frozen hashes passed. This is reproducible AI-assisted fiction with a same-author/template holdout, not independently collected recordings or a blind benchmark. The **full 540-record live run has not yet happened**.

### Actual model results and why the browser was disabled

- Lightning completed three cited answers; the first latest-date response took 3.297 s. Two fulfilled their reviewed obligations, while the personalized draft missed the requested three bullets. Extraction still has date-reconciliation, conditional-schema and structured-detail weaknesses. [Smoke](eval/reports/s11-lightning-answer-smoke.jsonl), [repair checkpoint](eval/reports/s11-repair-checkpoint.jsonl).
- Ultra's explicitly approved ten-call comparison returned six completions, including one rejected proposal; four calls failed at the provider. One answer and four source jobs succeeded, storing five claims. The spending-conflict note was not assessed at the cap. Successful completions took 63.853-86.920 s. Do not select Ultra for the bulk run from these results. [Raw evidence](eval/reports/s11-ultra-probe.jsonl), [manual review](eval/reports/s11-ultra-review.json).
- Lifetime accounting is now **44 requests / 334,052 accounted tokens**. The Ultra increment is 19,801 known tokens plus 61,910 retained unknown-usage reservations. No allowance or prior evidence was reset. Paid authorization remains $0; account billing was not independently queried.
- Read-only inspection of the actual running API found both inference flags false, the responder still Kimi and the extractor key absent. That old container was not redeployed by the probes. Its disabled-inference banner is an application configuration state, not proof that the separately tested keys cannot reach NVIDIA.

### Operator setup for the prepared configuration

Keep keys in the local untracked `.env`, never in a submitted report. For the approved public synthetic path, set `JARVIS_S07_SYNTHETIC_TRIAL_APPROVED=true` and supply `NEMOTRON_30B_API_KEY`. `JARVIS_RESPONSE_MODEL=nvidia/nemotron-3.5-lightning-30b-a3b` is explicit in the current Compose configuration; there is no automatic Kimi/Ultra fallback. Set lower `JARVIS_MAX_REQUESTS` and `JARVIS_MAX_TOTAL_TOKENS` if desired, within the hard 750 / 10,000,000 lifetime ceilings. These are cumulative ceilings, not fresh allowances after restart.

Rebuild/recreate API and worker only when ready to enable the approved processing path. A worker may consume previously requested eligible jobs in a retained database, so inspect pending work first; do not reset the application database or budget to obtain more allowance.

```powershell
docker compose up -d --build --wait --wait-timeout 120 api worker
```

For an unfamiliar unfamiliar corpus, leave unfamiliar inference off unless the operator explicitly accepts NVIDIA's data-sharing/retention/training terms. To opt in, supply their own `NVIDIA_API_KEY`, set **both** `JARVIS_UNFAMILIAR_INFERENCE_APPROVED=true` and `JARVIS_UNFAMILIAR_DATA_POLICY_ACK=I_ACCEPT_NVIDIA_DATA_TERMS`, choose cumulative spend/token limits, then recreate the services. This permits their Normal-mode imports/questions only. Private still has no provider requests, saved-memory reads or durable private state. The synthetic exception alone does not authorize arbitrary personal input. The Conversation setup panel displays model/key-presence/configuration status without making a live call or revealing the key.

Ordinary users use Sources to import, request processing and inspect progress; Conversation offers 30 showcase questions and collapsed, explained evidence choices. The local greeting is explicitly interface help, not an LLM answer. The bird icon is the official asset from `https://heyjarvis.ai/assets/brand/jarvis-app-icon-64.png`, served locally under the existing CSP.

`eval/corpus.py --stage validate` checks the frozen corpus without live calls. Its explicit `extract`, `answers` and `all` stages use the real shared pipeline, retain failures, cap new requests, keep questions out of memory and report known tokens separately from unknown reservations. `eval/ultra_probe.py --approved-ultra-comparison --max-new-calls 10` is an evaluation-only diagnostic requiring explicit approval and `NEMOTRON_550B_API_KEY`; bind-mount the repository's `eval` directory at `/app/eval:ro` when invoking it in the existing image. It is not an application selector or an automatically repeated fallback.

Still required: full live corpus/representation evaluation, semantic failure repair, deployed live UI demonstration, final clean Compose/import/process/UI/restart/scoped-reset rehearsal, independently authored Phase One finals and the exact tested release commit. The earlier test reset left the browser-profile container running when `down` omitted that profile; do not label it a clean final rehearsal. For the final isolated reset, explicitly include `--profile browser` and target only the intended test project/volume.

## Lightning manual backup checkpoint

A fresh user-requested smoke on 12 September at approximately 21:30 IST confirmed access to `nvidia/nemotron-3.5-lightning-30b-a3b` through the real guarded pipeline. Three requests completed at the provider: the initial extraction failed validation, its one existing repair committed a source-backed memory, and retrieval plus Ask correctly cited the revised 21 September launch date. Answer latency was 2,995 ms at the model and 3,364 ms end to end; the full smoke took 20,333 ms. The first extraction attempt, all timings and accounting remain in [the raw report](eval/reports/s12-lightning-backup-smoke.jsonl) and [the review](eval/reports/s12-lightning-backup-review.json). This is not a full-corpus or general semantic-quality pass. The other seven sample sources were imported for retrieval but not requested for processing.

Retain Lightning as an explicit manual backup using the already supported selector. Keep the existing key only in the ignored local `.env`; it was neither duplicated nor committed. For the approved synthetic-only mode, the non-secret operator settings are:

```dotenv
JARVIS_INFERENCE_PROVIDER=nvidia
JARVIS_RESPONSE_MODEL=nvidia/nemotron-3.5-lightning-30b-a3b
JARVIS_S07_SYNTHETIC_TRIAL_APPROVED=true
JARVIS_UNFAMILIAR_INFERENCE_APPROVED=false
JARVIS_FREE_SYNTHETIC_TRIAL_APPROVED=false
JARVIS_MAX_REQUESTS=750
JARVIS_MAX_TOTAL_TOKENS=10000000
```

The key variable is `NEMOTRON_30B_API_KEY`. Preserve all existing database credentials when changing these non-secret settings. After an explicit operator switch, rebuild/recreate the API with `docker compose up -d --build api`; changing a local file alone does not change a running container. Do not start an unscoped worker against the retained database's older pending probe jobs. Scope evaluation processing to its selected collection and reserve at least 30 requests outside its run ceiling for demo use.

**These instructions were documented, not applied to the running browser in this checkpoint.** A read-only check found an older API image: Lightning extractor disabled with no key forwarded, Kimi responder disabled with its key present. That explains why browser inference can remain unavailable even though this fresh isolated CLI/service probe used the valid Lightning key successfully. The initial configuration inspection encountered a legacy missing-field error; a version-compatible inspection completed without printing credentials.

There is no automatic provider/model fallback, no budget reset and no paid fallback. The existing one validation-repair attempt is not a provider switch and counts toward the same allowance. Private provider calls remain blocked; unfamiliar Normal-mode data still requires the separately documented NVIDIA unfamiliar consent. Previous failures of other models are historical diagnostics, not fresh retests in this checkpoint.

## Free-provider comparison and current blocker

Current evidence is in `eval/reports/s12-free-provider-review.json`. The approved 20-call comparison has finished. Google Flash-Lite can generate, but its conflict-handling quality gate failed; no free provider has been activated for the ordinary browser demo. OpenRouter returned a generation rate limit, and Google Flash returned a service-availability error. Catalog/key authentication is not a generation or quota guarantee.

The adapters are explicitly default-off. `JARVIS_INFERENCE_PROVIDER` selects `nvidia`, `google` or `openrouter`; free synthetic use additionally requires `JARVIS_FREE_SYNTHETIC_TRIAL_APPROVED=true` and `JARVIS_FREE_DATA_POLICY_ACK=I_ACCEPT_FREE_SYNTHETIC_DATA_TERMS`. The existing local key names are `GOOGLE_API_KEY_FREE_TIER` and `OPEN_ROUTER_API_KEY`; never commit their values. NVIDIA unfamiliar consent does not authorize personal data on these adapters. Private remains blocked.

The adapter recognizes `JARVIS_FREE_EXTRACTOR_MODEL` and `JARVIS_FREE_RESPONDER_MODEL`, but this checkpoint's Compose file does not yet forward them. The completed Flash-Lite diagnostic passed both explicitly with `docker compose run -e ...` as `gemini-3.5-flash-lite`; do not assume adding them to `.env` alone changes the container. This omission and demonstrated prompt failures are the proposed next bounded repair. The legacy `eval/ultra_probe.py` filename now accepts `--approved-comparison --provider google|openrouter|ultra --max-new-calls N`; it retains failures and enforces the shared persisted ceiling. Do not rerun live calls without the next approved allowance.

The browser tests ran against `jarvis-tests` only, with the test web stopped before the full backend suite, then recreated for all 24 browser journeys. The main database was not reset and its prior probe evidence/budget remains intact. The running ordinary application still needs deployment of a quality-checked selected configuration. Full live corpus processing, final exact-commit clean Compose/import/UI/persistence/scoped-reset rehearsal and Phase One final-file verification remain open.
