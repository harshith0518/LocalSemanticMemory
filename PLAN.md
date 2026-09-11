# Implementation plan

Status: proposed implementation sequence, 11 September 2026. Deadline: 12 September afternoon IST. See [todo.md](todo.md) for completed, ongoing and pending work. The user requested beginning with Phase One preservation and then progressing step by step. **Ask before substantial implementation changes outside already approved scope.** After each meaningful completed milestone, test, update the tracker, commit and push.

## Delivery strategy

Build a narrow complete journey: import dictations → ask a supported history question → produce a contextual draft → inspect Sources → resolve uncertainty → Correct/Forget → prove subsequent behavior changed. Use the same backend from CLI, API, UI and evaluator.

Backend + database + CLI first is the development sequence. The brief requires a normal-user interface connected to real state and model decisions, so reserve a small UI slice. Defer visual polish rather than the interface itself. No ASR implementation, native insertion, external message sending or Azure deployment is needed for this slice.

Preserve the author's independently authored Phase One documents before starting Part Two. Their content must come from the author. This technical plan does not establish their completion.

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

Propose one bounded bootstrap: `pyproject.toml` and lockfile, Dockerfile, Compose services and health/migration setup, package/service layout, API health endpoint, CLI entry point, minimal source/job/policy schema and isolated DB smoke checks. No memory extraction logic, hosted model calls, UI implementation or deployment in this first scope.

Before starting, explain files, data effects, tradeoffs and the acceptance gate, then obtain approval. Routine fixes inside the approved scope do not need repeated permission. Ask again for schema semantics, model behavior, privacy/lifecycle changes, new significant dependencies or deployment outside that scope.

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
