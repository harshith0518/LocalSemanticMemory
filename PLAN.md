# Implementation plan

Status: proposed implementation sequence, 11 September 2026. Deadline: 12 September afternoon IST. See [todo.md](todo.md) for completed, ongoing and pending work. The user requested beginning with Phase One preservation and then progressing step by step. **Ask before substantial implementation changes outside already approved scope.** After each meaningful completed milestone, test, update the tracker, commit and push.

## Delivery strategy

Build a narrow complete journey: import dictations → ask a supported history question → produce a contextual draft → inspect Sources → resolve uncertainty → Correct/Forget → prove subsequent behavior changed. Use the same backend from CLI, API, UI and evaluator.

The brief's broad use of "semantic memory" includes factual, episodic and preference-level understanding. Our scope includes useful reported episodes as well as facts and scoped preferences; only automatic procedural learning is deferred. See the [verified brief locators](docs/visual-guide-references.md#project-brief) and visual guide page 2 for the terminology mapping.

Backend + database + CLI first is the development sequence. The brief requires a normal-user interface connected to real state and model decisions, so reserve a small UI slice. Defer visual polish rather than the interface itself. No ASR implementation, native insertion, external message sending or Azure deployment is needed for this slice.

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
| 6 | `feat: connect the minimal unfamiliar interface` | User imports, asks, opens sources and uses controls without a console. UI and CLI produce the same backend behavior. | ~2 h |
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

## Workflow cases to implement deliberately

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
