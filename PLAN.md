# Implementation plan

Status: implementation sequence with dated historical scopes below. Updated deadline, confirmed by the user: **Saturday, 12 September 2026, 11:30 pm IST**. See [todo.md](todo.md) for completed, ongoing and pending work. The user requested beginning with Phase One preservation and then progressing step by step. **Ask before substantial implementation changes outside already approved scope.** After each meaningful completed milestone, test, update the tracker, commit and push.

## Delivery strategy

Build a narrow complete journey: import dictations → ask a supported history question → produce a contextual draft → inspect Sources → resolve uncertainty → Correct/Forget → prove subsequent behavior changed. Use the same backend from CLI, API, UI and evaluator.

The brief's broad use of "semantic memory" includes factual, episodic and preference-level understanding. Our scope includes useful reported episodes as well as facts and scoped preferences; only automatic procedural learning is deferred. See the [verified brief locators](docs/visual-guide-references.md#project-brief) and visual guide page 2 for the terminology mapping.

The user brought the minimal frontend forward after S05. **Browser first for user workflows:** import/status, source inspection and Normal/Private switching now use the web interface; connect Ask and full controls as their backend milestones pass. The existing CLI remains optional for developer checks and automation, with no user-flow dependency. Keep one shared backend and no separate frontend deployment. No ASR implementation, native insertion, external message sending or Azure deployment is needed for this slice.

The author reports Phase One complete and held separately, and explicitly approved proceeding with S03. Repository inclusion and mechanical checks remain pending; the assistant has not inspected those final documents. Their content must come from the author.

## Milestones and honest commits

The times below are work budgets, not guarantees. Cut optional features when a budget is exceeded. Each row becomes a commit only after its evidence exists; related work may be split when that makes review easier. Controls start in the first service boundary even though adversarial validation has its own milestone.

| Order | Scope and proposed commit | Acceptance evidence | Budget |
| --- | --- | --- | --- |
| 0 | `docs: establish minimal memory implementation plan` | Consistent documentation, explicit proposals and no fabricated implementation/results. | Complete: `596b034` |
| 1 | `chore: bootstrap compose and shared backend` | Locked Python environment; DB health; one migration path; API/CLI share services; isolated test DB; import job persistence survives restart. | ~2 h |
| 2 | `feat: import and inspect source evidence` | Raw/formatted pairing, missing metadata, exact spans and safe idempotent reimport; general importer accepts unfamiliar projects/names. | ~2 h |
| 3 | `feat: extract and reconcile supported claims` | Real model proposals; schema/span validation; explicit change, tentative owner and amount conflict stay distinct; rejected proposals visible. | ~3 h |
| 4 | `feat: retrieve evidence and answer with sources` | Source-only baseline; optional dense branch; query/time/scope handling; evidence-linked response/draft and honest abstention; usage measured. | ~3 h |
| 5 | `feat: enforce memory controls and repair` | Private/Correct/Forget behavior and real DB race tests; bounded feedback repair; no resurrection through retries. | ~3 h |
| 6 | `feat: complete the minimal unfamiliar interface` | Source-workspace UI brought forward after S05. Complete Ask, Sources and controls through shared services without requiring a console. | ~2 h remaining integration |
| 7 | `test: publish evaluation and reproducible review` | Approximately 500 records; separated labels; measured baseline/candidate results including failures; clean start/reset/import/UI/evaluate walkthrough. | Remaining time; reserve ≥3 h |

Corpus generation and test-case design can proceed alongside approved implementation once the input contract is stable. Run small live checks during milestones 3–5; discovering provider or schema failure in the final evaluation is too late.

## First implementation approval scope

**S03 approved and implemented, 11 September 2026.** The user confirmed Phase One complete in their possession and explicitly approved this bootstrap, including pgvector. The implementation and acceptance results are recorded in RUN.md. This approval supersedes the earlier pending handoff; it does not certify or mechanically check the separately held documents. Commit/push to `dev`; the user controls merging into `main`.

| Implemented files | Bounded behavior |
| --- | --- |
| `pyproject.toml`, `uv.lock`, `.python-version` | Python 3.12; FastAPI, Uvicorn, Pydantic, SQLAlchemy, psycopg, Alembic and Typer. pytest, HTTPX and Ruff for development checks. Resolve compatible exact versions during the approved build and install from the frozen lock. |
| `Dockerfile`, `compose.yaml`, `compose.test.yaml`, `.dockerignore`, `.env.example`, `docker/postgres/init-db.sh` | One Python image; PostgreSQL `db`, one-shot `migrate`, loopback `api`, developer CLI profile and a standalone isolated test Compose project. Initialize separate runtime/migration database roles. Pin tool/image versions and image digests. Keep secrets, private inputs, local caches and parent-workspace artifacts out of the build context. |
| `alembic.ini`, `migrations/env.py`, `migrations/versions/0001_bootstrap.py` | One migration path for the minimal source/job/policy records below. Application startup waits for database health and successful migration. |
| `src/jarvis/` | Configuration, per-operation DB sessions/transactions, backend-owned local identity and policy boundary, shared services, thin FastAPI and Typer adapters. `GET /health` and `jarvis health` share liveness; `GET /ready` and `jarvis ready` share DB/schema/pgvector readiness. |
| `tests/integration/` and existing run/status documents | Synthetic persistence, migration, API/CLI parity, rollback, constraint and isolation checks on actual PostgreSQL. Record commands and observed results after they work. |

Implemented schema effects are limited to three logical records plus Alembic's revision table:

- **Policy:** owner ID and a nonnegative policy revision, providing the row for later guarded transactions. The server supplies the local owner identity; request fields cannot select another owner.
- **Sources:** owner-scoped source identity, source revision, paired raw/formatted text, content hash, actual import time and nullable supplied capture/app metadata. Keep raw/formatted variants together; text equality is not observation identity, and missing capture times remain unknown.
- **Jobs:** owner/source references, idempotency key, pending status, attempt count and expected source/policy revisions. Enforce matching source ownership with database constraints. A shared internal service atomically saves a synthetic source and pending job for the checks; this does not expose a general import endpoint or execute processing jobs.

This migration introduces durable tables in the selected application database; the acceptance run writes only synthetic records to the new application volume and isolated test storage. Tests use a separate PostgreSQL service, credentials and volume with no application-volume mount or application DB credentials. Test configuration must reject the application database target. Routine startup preserves volumes; reset removes only the explicitly selected test resources.

Use synchronous SQLAlchemy/psycopg transactions initially to keep the API and CLI path small and explicit. PostgreSQL adds a service but tests the actual selected persistence backend; a SQLite test substitute would not prove its constraints or transaction behavior. Copy source into images and retain the existing Windows checkout. pgvector is enabled during privileged empty-volume initialization; vector columns/search indexes, worker processing, extraction, hosted model calls, user-content import, full Private/Correct/Forget behavior, UI and deployment belong to later scopes. A source/policy table is not evidence that those controls already work.

Acceptance requires all of the following:

1. Build with pinned images and a frozen dependency lock; start the documented Compose services from empty isolated storage, with DB health before migration and migration completion before API readiness.
2. Apply migrations to an empty database; repeat without duplicate objects or schema drift. Use a non-superuser application role and restrict schema-changing privileges to the migration path.
3. API and CLI report the same DB/schema readiness. Database unavailability or a stale schema produces a bounded failure and a nonzero CLI exit / HTTP 503 without leaking credentials or raw error payloads.
4. Commit a synthetic source and pending job, replace both application and database containers while retaining the designated test volume, and verify the exact saved state. Container restart alone is insufficient evidence of volume persistence.
5. Pass real PostgreSQL tests for atomic source/job writes and rollback, uniqueness, owner consistency and test-target isolation, plus Ruff and relevant API/CLI checks. If a concurrency guarantee is claimed, use separate connections and explicit barriers. These checks make no claim about live models or complete lifecycle controls.

After these gates pass, update the existing tracker/run instructions, commit and push the coherent S03 implementation to `dev`, and verify the remote commit. The user reviews and merges. Routine fixes within the approved scope need no repeated permission; material changes to schema meaning, model behavior, privacy/lifecycle semantics, significant dependencies or deployment still require review.

## S04 approved scope and acceptance

Approved and implemented on 11 September 2026 after S03. `contracts.py`, `policy.py` and `errors.py` define typed evidence, backend context and safe failure categories. `services.py`, API and CLI share validation/policy/transaction behavior. `models.py` and migration `0002_evidence_contracts` add source provenance, passages, claim revisions and owned evidence links without rewriting S03 data. Compose disables persistent API/CLI logs. Isolated tests and synthetic fixtures establish the bounded behavior; no new dependencies were needed.

Acceptance is recorded in [RUN.md](RUN.md#actual-s04-results): the S03 regression checks pass; invalid ownership/version/variant/passages and stale revisions fail; scope, tentative meaning and unknown times survive; raw/formatted variants remain one observation; Private has zero personal-store/file-write attempts and unchanged durable snapshots through success/failure paths; guarded revision races use actual PostgreSQL connections/barriers. The complete suite has 75 passing checks.

General corpus import was deferred from S04 to S05 below. Live models, retrieval, UI, entity resolution and complete Correct/Forget remain later scopes. A valid schema/span is not an entailment verdict. An appended claim revision does not classify a correction versus a real-world change.

## S05 approved scope and acceptance

The user approved proceeding with diagnostic import/inspection and then merging the tested work into `main` and pushing. `imports.py` defines the bounded UTF-8 JSONL interchange and typed receipts/inspection; `services.py` owns batch validation, stable namespace identity, source/job transactions and reimport conflict checks. API and Typer adapters expose those shared operations. Docker includes only the named curated source/evaluator files, kept in separate directories. No new dependency or migration is needed; existing S03/S04 records retain their meaning.

Acceptance: import all eight diagnostic observations, inspect exact raw/formatted pairs and all 11 evaluator excerpts, preserve missing metadata, keep equal-text independent observations distinct, and make exact reimport return existing source/job state. Conflicting/invalid batches must leave no partial state; API/CLI must agree; Private must avoid saved access and input reads/writes; separate PostgreSQL connections/barriers must prove import serialization and the policy commit guard. Preserve the original S03 probe and all imported source/job fields across container replacement. [Actual results](RUN.md#actual-s05-results)

Changed exports are rejected rather than silently revised; automatic extraction/job execution, models, retrieval, UI, complete Correct/Forget and the full approximately 500-observation corpus remain later work. S06 requires a separately bounded live-call approval and explicit provider retention/no-training/budget settings.

## Approved early UI foundation

The user's latest instruction explicitly approves a minimal frontend and a browser-first plan instead of requiring CLI user actions. Implement this bounded S10 foundation immediately after the S03–S05 audit, leaving the underlying S06–S09 model/control gates intact.

Historical first UI slice; superseded for frontend technology by [Approved React workspace refinement](#approved-react-workspace-refinement). Its original scope and evidence remain below.

Files: `src/jarvis/web/` for plain HTML/CSS/JavaScript and a local icon; `src/jarvis/api.py` for the shell/static route and security/cache headers; `tests/integration/test_web.py` and `tests/browser/` for regression and browser checks; `compose.test.yaml` for a loopback test web service using only the isolated PostgreSQL environment; `.dockerignore` to exclude test dependencies. Update the consolidated instructions/plan/run/tracker. No migration, Python dependency change, model call, frontend build process or new runtime container.

Behavior: choose a collection, import a bounded JSONL file, inspect paginated original sources and job status, preserve exact text/metadata, and switch between Normal and Private. The browser obtains the policy revision automatically while the shared backend still checks it atomically. Private clears displayed context and selected files, aborts pending requests and suppresses late responses; it does not send imports or browse saved sources. Returning to Normal or restoring a page does not restore old evidence or backfill. Already accepted Normal writes may finish after a mode switch and are not represented as Private writes or rollback.

Acceptance: S03–S05 isolated PostgreSQL checks stay green; browser import/reimport, malformed/conflicting/oversized input, unknown metadata, Unicode/HTML-like text, pagination, mobile/keyboard use, no browser-storage writes, Private switching, late-response rejection and network errors work. API asset routes require no personal-store access and expose no cookies/cache or path traversal. Rebuild/start the application and verify existing synthetic records remain intact. No fake Ask/Correct/Forget controls or claimed model outputs.

The alternative is a separate frontend framework/build/server or deleting the tested developer CLI. Neither is needed to remove CLI dependence from the ordinary-user journey. Keep those optional tools and prove the browser path directly. Complete the full S10 gate only when Ask and S09 controls are connected.

## S06 bounded bootstrap proposal

The user requested the completed S03–S05 audit/publication and starting S06. This section makes the next important implementation changes reviewable under AGENTS.md. The proposal below is historical: S09 implemented it and approved the bounded synthetic exception; current live failures are recorded in RUN.md. Scope: **source-history answering only**, using the existing Windows checkout, Linux containers and shared backend.

| Proposed files | Behavior and data effects |
| --- | --- |
| `src/jarvis/answers.py`, `src/jarvis/providers.py` | Typed question, full-history packet, answer/abstention and exact source citations; small responder interface and buffered Kimi HTTP adapter. Fixed endpoint/model, bounded timeout/output, at most one schema-repair attempt, no automatic provider/model fallback. Treat source text as evidence, never instructions. |
| `src/jarvis/services.py`, `src/jarvis/api.py`, `src/jarvis/cli.py`, `src/jarvis/errors.py` | One source-history operation, exposed through `POST /ask` and the browser's Ask panel; an optional `jarvis ask` developer command can use JSON stdin. Backend identity and Private gates precede saved reads, input logging, accounting and provider calls. Load all eligible latest observations in the selected namespace; keep raw/formatted paired and unknown metadata intact. Return an explicit does-not-fit result rather than silently dropping history. Recheck policy/source revisions before provider use and buffered publication; reject stale work. |
| `src/jarvis/models.py`, any necessary additive migration after `0004_lexical_retrieval` | Reuse S07's existing `model_calls`/`model_budgets`; review necessary responder fields for owner/run/attempt identity, policy revision, model/prompt version, reservation/actual usage, latency and fixed errors. No stored prompts, answers, reasoning or credentials. Reserve budget under the shared guard and retain failed/unknown reservations across retries/restarts. Preserve existing rows. Answering creates no extraction jobs or claims. |
| `src/jarvis/config.py`, `compose.yaml`, `.env.example`, `pyproject.toml`, `uv.lock` | Provider configuration disabled by default. Pass only the Kimi key to API/CLI when enabled; no provider credentials in database/migration/test services. Move already-locked HTTPX into runtime dependencies. Keep secrets out of representations, errors and logs. |
| `tests/integration/test_answers.py`, provider transport tests, existing regression fixtures | Deterministic contract/failure tests, real PostgreSQL revision/budget races, API/CLI parity and zero-access Private checks. Transport doubles are not model-quality evidence. |
| Evaluator command/module, `eval/reports/`, RUN/DECISIONS/EVALUATION/todo | After live-call approval, run the eight existing cases three times with actual configured/returned model, all attempts, tokens, latency and failures. Preserve source/label separation, inspect faithfulness and unknown/conflict behavior, and report failures without changing gold labels to fit output. |

**Provider decision updated in S09:** the user approved exact public synthetic inputs under NVIDIA trial terms, 96 total requests and 1,500,000 input/output tokens including failures/retries, $0 paid. Enforce full source/control fields in code. Personal inputs and Private calls remain blocked; no automatic Ultra fallback. The initial 32-call proposal is historical.

Acceptance before declaring S06 complete:

1. Existing S03–S05 tests pass in the isolated PostgreSQL project; the new empty/repeated migration has no drift and preserves existing source/job state.
2. Browser Ask and API return a cited source-history answer through the shared service, with optional CLI parity checks, with no model-generated learning or external-action claim.
3. Invalid/cross-owner/non-context citations and stale policy/source revisions fail; full-history overflow fails explicitly. Raw/formatted conflicts, tentative owners, scoped preferences, reported actions and unknown times retain their meaning.
4. Private, invalid input, disabled provider, quota, timeout and malformed output paths reveal only bounded errors. Private causes no personal-store reads, durable activity or external provider request.
5. Actual PostgreSQL connections/barriers verify revision and budget ordering; no DB lock is held during network inference. Failed/retried/unknown calls remain accounted for across process/container restart.
6. After the separate live gate is approved, retain three runs of all eight synthetic cases and manually assess semantic support, not just citation validity. Publish limitations and actual results. A blocked or failing live gate leaves S06 incomplete.

Keep selective extraction, worker processing, retrieval/ranking/embeddings, automatic Ultra fallback and complete Correct/Forget in S07–S10. Extend the existing browser UI in each corresponding backend milestone. This first baseline will not claim general Private conversation support with a noncompliant provider. The simpler alternative to a new call table is process-local accounting; reject that alternative because API/CLI concurrency and restarts would bypass the agreed ceiling.

## S07 bounded proposal after research review

Implementation is now present; [RUN.md](RUN.md#s07-memory-processing) records the verified contract/browser behavior and open live-quality gate. The table preserves the reviewed scope; `evaluation.py` implements the synthetic live-evidence command and S04 contracts are reused.

The user requested a reviewable S07 plan, then research on useful memory and storage. The user approved implementing this bounded scope on 12 September 2026 after the research review. Routine implementation and fixes are covered; S09 subsequently approved the bounded synthetic provider exception. Keep the existing Windows checkout, Linux containers, shared service layer and browser-first workflow. S06 remains incomplete; reuse its proposed provider/accounting foundation if brought forward, without marking source-history answering complete or carrying its proposed live-call allowance into S07. [Research and tradeoffs](DECISIONS.md#input-to-memory-research-review)

| Proposed files | Behavior and data effects |
| --- | --- |
| `src/jarvis/extraction.py`, `src/jarvis/providers.py`, `src/jarvis/contracts.py` | Bounded typed proposals for eligible facts/preferences/reported events, exact passages and reconciliation. Zero claims is a valid outcome. Preserve attribution, condition, uncertainty, units and unknown time. Nemotron Lightning remains a candidate; model calls never execute SQL or authorize themselves. |
| `src/jarvis/services.py`, `src/jarvis/processing.py`, `src/jarvis/worker.py`, `src/jarvis/models.py`, `0003_memory_processing` migration | One DB-backed worker; lease/retry/replay handling, revision relationships and operation receipts. Share accounting with future S06 work rather than creating competing budget stores. Preserve existing source/job/claim rows; model calls occur outside locks, then the whole accepted operation commits under the shared guard. Exact retries do not add evidence. Final columns/migration ordering must match the approved combined scope. |
| `src/jarvis/api.py`, `src/jarvis/web/`, optional developer CLI, configuration/Compose | Browser processing controls, job status and source-linked memories/history through shared services. Private blocks personal processing before access or durable activity. Provider configuration stays disabled until its separate terms/budget gate is cleared. |
| Isolated PostgreSQL/provider/browser tests; evaluator fixtures/reports; RUN/todo | Preserve existing regressions; demonstrate invalid/stale proposal rejection, atomic rollback, competing workers, retry/restart and zero-access Private failure paths. Record actual outcomes and semantic limitations. |

Acceptance: retain all existing S03–S05/UI checks; cover no-memory questions/one-off instructions, scoped preferences, conditional owners, unknown times, raw/formatted conflicts, real changes versus extraction errors and duplicate NOOPs. Use separate PostgreSQL connections/barriers for races. Show evidence/history in the browser, preserve existing state through migration/restart, and keep failure receipts honest. Deterministic proposals establish backend behavior; only separately approved repeated live runs establish extraction faithfulness. Compare with stronger extraction only within an explicitly scoped budget. Downstream quality needs the S06 baseline and controlled S08 comparisons.

The simpler alternative is a synchronous extractor without durable processing; it would leave retry/restart behavior and pending imports unresolved. Prefer one bounded worker over another queue service. General corpus expansion, embeddings/retrieval improvements, automatic Ultra fallback, automatic procedural learning and complete user Correct/Forget remain later work. S07 must not claim those later controls are complete. After approval and checks, commit/push to `dev`; a new `main` merge needs the user's instruction.

## S08 approved retrieval implementation

On 12 September the user requested rechecking/publishing S07 to `main` and implementing S08 with measured review and necessary refinements. S07 was rechecked (156 PostgreSQL tests, 10 browser tests) and remote `main` verified at `8eec7b9e0edc16c3e6b35cb152818c3776cd0c27`; subsequent work stays on `dev`.

Bounded files: `retrieval.py` for typed requests/evidence packets and shared retrieval operations; `models.py` plus an additive migration for PostgreSQL GIN expression indexes; API, optional CLI and the existing browser for search; isolated PostgreSQL/browser tests and a retrieval evaluator. Update the consolidated architecture, decisions, run instructions, tracker and evidence report. No replacement database, dependency upgrade or automatic model fallback.

Start with PostgreSQL full-text candidate retrieval over original paired observations. Compare a source-only representation with a source-plus-memory candidate union and reciprocal-rank fusion, preserving original-source fallback. Select whole observations for this bounded corpus, preserving both variants and all supporting sources for selected claims; fail or report an explicit evidence-budget boundary rather than clipping a condition or silently truncating a record. Keep current/historical claim lifecycles distinct and captured-time filters separate from event/effective time. Source scope/identity remain evidence to interpret, not inferred from matching names. Queries do not teach memory or create jobs.

Canonical ownership, eligibility, source/claim revisions and existing exclusions must be checked before results are released. Private refuses input/store access. Search remains available without an extraction provider. The index is a rebuildable derivative; existing records and their meaning remain unchanged. Optional dense search is deferred unless a separately approved embedder and measured benefit justify it; no simulated vectors will be called semantic evidence.

Acceptance: existing regressions, empty/repeated migrations without drift, indexed search and raw/formatted pairing, source fallback, current/history/unknown-time behavior, explicit overflow versus empty/error outcomes, real PostgreSQL publication races, zero-access Private failures, browser search and late-response clearing, original-state/restart persistence, and controlled retrieval evidence with fixed limits. Record misses and skipped comparisons. The NVIDIA synthetic-only exception was later approved in S09. The Kimi baseline still has not passed; local retrieval metrics cannot establish answer quality or close those live gates.

## Workflow cases to implement deliberately

### Approved S09 and completion of the live baseline

On 12 September the user approved the pending synthetic-only NVIDIA exception, completing the outstanding checks and starting S09. Preserve the existing persisted allowance; expand its combined ceiling to 96 calls/1,500,000 tokens including repairs, $0 paid. Complete the bounded S06 Ask baseline and compare history/source retrieval/source-plus-memory answers with fixed model and common evidence allowance. Exact fixture fields and diagnostic questions, not client labels, govern external input eligibility. No automatic fallback or personal/Private inference.

Files: `answers.py`, provider/accounting helpers, `controls.py`, existing API/CLI/browser adapters, `models.py` and an additive lifecycle migration, PostgreSQL/provider/browser tests and evaluator reports. Correct saves an explicit user-confirmed replacement and distinguishes extraction error from world change. Forget previews affected memories/support and commits exclusions, derivative invalidation, job fencing and policy revision atomically. Whole supporting observations remain conservatively unavailable for reuse; originals remain separately inspectable. Match known copies/reimports by source identity, exact variants and excluded supporting text, without treating matching names as entity identity. Idempotent control receipts prevent duplicate retries. Feedback requests a specific diagnosis/replacement before changing memory and permits one bounded answer rerun.

Acceptance: original regressions; typed/owned/revision-checked controls; correction changes subsequent evidence; Forget prevents source fallback and relearning through duplicates/reimports, delayed workers and retries; real PostgreSQL barriers for both control/worker and control/reply orderings; zero-access Private failure paths; browser import/process/Ask/Sources/Correct/Forget and late-response clearing; empty/repeated migrations and preserved existing state; separately labeled live calls with every failure retained. The PDF's pages 12–15 define lifecycle intent; its provider/status labels remain a historical snapshot. Retain the simpler transactional database design rather than introducing a second store or model-authorized deletion.

| Situation | Required response | Owning layer |
| --- | --- | --- |
| General self-contained question | Skip personal retrieval when unnecessary. | Request router |
| Personal recall or draft | Retrieve permitted current facts, useful episodes and scoped preferences. | Retrieval + answer service |
| Follow-up with unclear referent | Resolve from permitted recent context; ask if material ambiguity remains. | Request interpretation |
| Same observation imported again | No duplicate independent evidence; return an idempotent receipt. | Import service |
| Separate observations with identical words | Preserve distinct source identities; do not equate text equality with event identity. | Import/evidence model |
| Real-world update | Add a successor with source and time; retain old state for history. | Reconciliation |
| Extraction error | Retract the interpretation; preserve original evidence. | Correct service |
| Raw/formatted conflict or hypothetical fact | Keep uncertainty; ask a targeted question if needed for the task. | Reconciliation + answer |
| Missing evidence versus search failure | Abstain for the former; report/retry a bounded operational failure for the latter. | Retrieval + answer |
| Negative feedback | Diagnose evidence, retrieval, generation, execution or style; apply the smallest supported repair. | Feedback service |
| Private / Forget / concurrent updates | Enforce at every read, write, job commit and reply publication boundary. | Policy + transaction layer |

## Scope cuts, in order

1. No Azure until the local review path is complete; free credits do not remove deployment work.
2. Defer graph traversal frameworks, hierarchical summaries, automatic procedural learning and broad integrations.
3. Start without response caches, streaming or persisted summaries; each adds invalidation work. Retain short permitted request context and concise Normal traces.
4. Keep a single worker and DB-backed jobs. Avoid distributed orchestration and another queue service.
5. If embeddings or a small model do not improve measured results within the budget, retain the supported baseline and document the failed/skipped experiment.

Do not cut evidence links, real model integration, Private/Correct/Forget, unfamiliar-corpus import, the minimal UI or honest evaluation. Freeze optional experiments by **12 September 10:00 IST** as a planning buffer. Reserve the final hours for reproducibility, actual defects and explaining limits. If required gates fail, report that rather than substituting mock results.

## S10 measurement and unfamiliar workflow

Approved on 12 September: finish the minimal browser surface, expose honest resource/use measurements, verify the brief's corpus requirement, and assign corpus expansion to the correct subsequent milestone. Files: `metrics.py`, the existing service/API/CLI/worker/answer adapters and browser, `eval/efficiency.py`, `eval/live.py`, isolated tests and these consolidated documents. No new dependency, migration, vector store, provider selection or privacy semantics. Preserve S03-S09 records.

The browser can explicitly **Load 8 sample dictations** through the existing atomic import service, then use Sources, processing, Search, Ask, history, controls and feedback. A collapsed **Usage and performance** panel provides an owner-wide snapshot plus transient action/stage timing. Model-call accounting already existed; new failures also retain elapsed time in its existing nullable column. Known input/output tokens, unknown usage, conservative reservations, operation outcomes and sample counts are distinct. Neither a successful job nor a valid citation establishes semantic accuracy. The alternative of a telemetry stack or new persistent activity table is unnecessary for this prototype.

Acceptance: existing PostgreSQL/concurrency/browser checks pass; byte counts handle Unicode and owner isolation; reads do not create records; failures do not become zero token usage; timings stay separate across requests; Private prevents store access and clears/ignores late metrics; the public sample import is explicit/idempotent. Produce an isolated CPU/RAM/storage-growth report with honest measurement scope, and preserve/restart application state. A separate bounded live smoke must remain honestly recorded if it fails. Successful live end-to-end behavior remains an open S10 gate until provider/semantic failures are resolved; a deterministic demonstration cannot close it.

## S11 corpus and semantic evaluation handoff

The original brief, pages 4-6, requires approximately **500 development transcript records** and use of a separate approximately **500-record unfamiliar corpus**. These are observations, each optionally containing raw ASR, formatted text and metadata; they are not a prescribed count of evaluation questions. The eight curated originals and two public control statements are implemented. `eval/retrieval.py` generates 500 diagnostic records including 485 templated distractors; it is not the varied acceptance corpus.

Build the varied corpus in S11 after the live eight-record smoke and semantic gates are reliable. Keep one fictional user's records across several projects and personal contexts. Proposed primary buckets total 500; tags may overlap, primary counts must not:

| Primary bucket | Records | Main coverage |
| --- | ---: | --- |
| Connected chronological histories | 200 | 20 threads of 10 observations; later facts depend on earlier context, updates, late imports and multi-note answers. |
| Independent useful observations | 100 | Distinct domains, entities, reported events, units and same-name people. |
| Scoped preferences and current overrides | 60 | Conditions, project/task scope, enduring versus one-request instructions. |
| Conditional, negated and conflicting statements | 60 | Uncertainty, quotations, explicit nonfacts, unresolved variant/source conflicts. |
| Noisy ASR, multilingual and incomplete metadata | 50 | Hindi/Hinglish, Unicode, dates absent or partial, disagreement between paired variants. |
| Irrelevant/transient/question/instruction-shaped inputs | 30 | No-memory decisions, distractors and historical instructions that must not execute. |

This allocation is an engineering proposal, not a research-proven optimum. Author coherent scenario/event outlines and review their exact passages before producing records. Keep each thread intact when assigning tuning/held-out scenario families; do not tune on the later held-out questions. Start with 16 tuning and at least 32 held-out questions/actions, three repeats each, grading multi-note support, uncertainty/time/scope, changes, contradictions, abstention and task success. Keep all questions, expected claims, labels and operation scripts under `eval/`, never in `data/synthetic/` ingestion. Correct/Forget/reimport/restart and Private are evaluation operation sequences, not saved Private transcript records. Private sequences use only ephemeral current context.

Compare original-source history/search with sources plus memories under fixed model, eligible corpus and evidence allowance. Record input/output usage and the actual serialized evidence bytes; until an exact tokenizer is integrated, the 24,000-byte cap must not be represented as equal measured input tokens. Retain all failures and manually review entailment; report counts/denominators by scenario family, pipeline stage, repetition and cold/warm condition. Include ingestion/repair failures in cost and success denominators. An unfamiliar unfamiliar import must follow the general source contract, not hardcoded Atlas labels.

Before live processing of the expanded corpus, review the exact additional synthetic allowlist, aggregate request/token budget and provider settings: the existing 96-request allowance cannot process 500 records and repeated comparisons. Do not reset it or remove the personal-data gate. No automatic Ultra fallback. S12 is the clean-checkout acceptance rehearsal; it cannot pass while unfamiliar inference or live quality remains unavailable.

The tonight audit also confirmed an implemented scale boundary: S07 fails when its collection has more than 64 active context claims, and the serialized model-input cap is 60,000 bytes. It includes the current source plus sources supporting those active claims, not all unprocessed observations. S11 must review bounded relevant-claim/source selection and its lifecycle checks before claiming the varied corpus can be fully processed. Raising limits or silently dropping required evidence is not an approved workaround.


## Approved React workspace refinement

The user explicitly requested React, shadcn components, a Jarvis-inspired design informed by 21st, typed/pasted transcripts in place of speech, animation tied to actual operations, and browser validation. Interpret "React5" as current stable React 19.3, as stated during implementation; no separate framework version was specified.

Files: `frontend/` owns locked React/TypeScript/Vite source, shadcn/Radix primitives, Lucide icons, Motion, Tailwind styles and local fonts. Docker builds these assets in a pinned Node stage and copies them into the existing Python wheel; FastAPI serves the generated `src/jarvis/web/` directory. Update Docker ignore/build configuration, the shell/CSP handler, browser/asset checks and the consolidated documentation. No new runtime container or database migration.

The four screens are Conversation, Sources, Memory and Usage. Normal input has explicit Ask versus Save a note intent. Saving uses the existing atomic JSONL importer, retaining exact raw/formatted strings as one observation and unknown capture time. Stable in-page note IDs permit retry after a lost response. Questions/replies are transient and never silently saved. Controls retain backend preview/confirmation and all typed qualifiers. A control commit clears cached answers/search/evidence. Private unmounts Normal state, cancels pending requests and has only a temporary local scratchpad, without provider calls or backfill.

Alternatives: retaining the plain client would avoid a frontend build but would not meet the requested React/component direction. A separate Node server, persistent client cache, analytics, fake progress, automatic live calls or voice capture are unnecessary. Prefer a single static production bundle, backend-owned policy and a restrained, accessible visual system. References and tradeoffs are in DECISIONS.md.

Acceptance: locked production build and formatting; unchanged PostgreSQL regression gates; actual Chromium checks for every existing flow plus typed-note exactness/idempotency, asynchronous failure/Private races, reduced motion, keyboard/dialog behavior, mobile overflow, literal source rendering and zero browser persistence or outside asset requests. Visually inspect desktop/mobile, loading, answers and controls. Preserve application state on container replacement, update RUN/todo with actual outcomes, commit and push dev. Live provider reliability and semantic evaluation remain separate open gates.

## Tonight bounded repair proposal

Pending user approval after the readiness checkpoint. The deadline is 23:30 IST; reserve 22:30-23:15 for the final demonstration, reproducibility/packaging checks and 23:15-23:30 for submission buffer. Earlier morning/afternoon stop times in historical planning sections are superseded by this confirmed deadline. These are work timeboxes, not a promise that live-quality gates will pass.

**Proposed next scope:** make Nemotron Lightning an explicitly selectable response candidate while retaining Kimi as an available configured option; never switch automatically after failure. In parallel, revise the extraction prompt around the observed qualifier, time and reconciliation failures. The fresh Lightning probe demonstrates endpoint availability, not that it is a good responder or that its extraction is faithful. The seven Kimi failures make another unchanged retry a poor use of this repair window.

**Files and effects:** `src/jarvis/providers.py` for validated explicit responder selection and model-appropriate request settings; `src/jarvis/extraction.py` for a new generic prompt version; `compose.yaml` and `.env.example` for the operator configuration; corresponding provider/answer/processing tests under `tests/` and existing evaluators/reports. No schema migration, dependency addition, client-owned authorization, source rewriting, expanded live allowlist, personal/Private inference or automatic fallback. Existing observations/claims remain intact; only new approved synthetic attempts may create new evidence-backed revisions and accounting. Do not silently correct old live failures or tune source labels to match outputs.

**Acceptance and bound:** existing relevant backend/browser contracts remain passing. Use at most 12 additional live requests including repairs for this first checkpoint, inside the unchanged lifetime 96-request / 1,500,000-token / $0-paid allowance; stop earlier on a failed smoke or exhausted allocation. Inspect the original eight-source obligations, prioritizing date changes, attribution, conditions and variant conflict, then require at least three supported cited answers across core questions before calling the candidate useful for a demo. Incomplete repeats remain incomplete. A larger corpus, altered context selection or expanded allowance requires its own bounded approval after this small path works.

**Alternatives:** retain Kimi only and investigate its wire transport further, with uncertain deadline benefit; or separately approve a stronger response/extraction comparison. Neither advertised size nor one completion selects a quality winner. Do not implement a provider/model choice until the user approves this proposed scope.

## Approved evening implementation and acceptance

The user approved the preceding bounded repair and, subsequently, the 540-record corpus, 750-request / 10,000,000-accounted-token / $0-paid lifetime extension, bounded relevant-memory context and explicit default-off unfamiliar mode. See DECISIONS.md for the exact data effects and consent fields. The existing budget is not reset.

Implementation files: provider/extraction/processing/answer/API modules; Compose and `.env.example`; Docker packaging; existing React conversation/source/shared components and local bird asset; `eval/build_corpus.py`, `eval/corpus.py`, source JSONL and separate manifests/cases; provider/scale/unfamiliar/backend/browser tests. No migration or new dependency.

Gate order: static/schema/corpus checks; all existing PostgreSQL and race contracts plus new scale/unfamiliar tests; actual Chromium flows including mobile, greeting without saved reads/model calls, local assets and 540-record import; a tightly limited Lightning answer/extraction checkpoint; the full persisted live pipeline and separately labeled answer screens/manual review; clean submitted-commit startup/import/UI/reset rehearsal. Keep initial failures, partial runs and unprocessed counts. Passing a job or matching an answer substring is not proof of semantic correctness.

The 30 showcase questions are preselected coverage. Questions, expected answers and operation scripts remain under eval, not the memory corpus. Do not alter held-out expectations to match generated results. Reserve 22:30-23:15 IST for the final review path and 23:15-23:30 for submission. Phase One preservation remains open until actual final files are supplied.
