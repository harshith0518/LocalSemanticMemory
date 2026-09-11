# Delivery tracker

Updated: 11 September 2026. Target: **12 September afternoon IST**.

This is the single current-status checklist. [PLAN.md](PLAN.md) defines scope and milestone gates; [DECISIONS.md](DECISIONS.md) records decisions; [EVALUATION.md](EVALUATION.md) defines evidence. Check an item only after its acceptance condition is demonstrated.

**Current work:** Source-note preservation and S02 environment readiness are complete. S01's two final author-authored submissions remain open; S03 bootstrap is the next implementation scope to review. The application is not implemented and no live model evaluation has run.

## Completed

- [x] Establish the focused implementation plan, architecture, evaluation strategy, review contract and contribution rules.
- [x] Replace the previous repository contents and push the planning baseline to `main`, preserving earlier Git history. Commit: [`596b034`](https://github.com/harshith0518/ProjectSemanticMemoryJarvis/commit/596b034940ea3a6adabeb3940dd6d793bc2c8b1e).
- [x] Verify that baseline's nine-file remote tree, clean local/remote agreement, Markdown links and staged whitespace. These are documentation checks, not application tests.
- [x] **S02 — Prepare the existing environment.** Started Docker Desktop; verified Linux Docker client/server `28.4.0`, Compose `2.39.2-desktop.1` and Ubuntu-24.04 integration. Pulled the official probe image, verified a named-volume marker survived replacement of a disposable container, and removed the uniquely named probe volume. Keep one Windows checkout and run the planned backend in Linux images. [Actual checks and limits](RUN.md#environment-recommendation); no project DB or application tests yet.
- [x] Record DeepSeek's main-model role and shortlist smaller memory-operation proposers. Public provider documentation was checked; account access, quality and cost remain untested.
- [x] Create this tracker and record the user-requested test → update tracker → commit → push workflow.
- [x] Preserve the latest user-supplied notes and inspect the relevant earlier discussion in **Explain Jarvis products** and **Document product features and plan**. Record [provenance and mechanical counts](docs/part-one/README.md): 813 whitespace-delimited tokens overall; 317 in the Phase One subsection including questions. These are source notes, not certified independent submissions.
- [x] Commit and push source-note preservation/tracking as [`559f3aa`](https://github.com/harshith0518/ProjectSemanticMemoryJarvis/commit/559f3aadd8fbb57bdf25760097671dc5da195759). Remote `main` was independently checked at that full commit after the push; staged whitespace passed.

## Ongoing

- [ ] **S01 — Final Phase One submissions.** Owner: author writes/finalizes; assistant preserves and checks mechanics. Supplied notes are now saved. The earlier five-question recap was assistant-authored; it is attributed accordingly without inferring the origin of every sentence in the latest notes.
  - Next action: author supplies the final independently written positioning statement (at most 100 words) and vision document (at most 600 words); preserve and mechanically check them. Readiness checks can continue while this remains open.
  - Acceptance: both final documents are present with source/author attribution and checked counts. Do not generate the author's argument, silently rewrite it or backdate completion.
  - Remaining gap: two final acceptances have not been identified. A 317-token subsection does not itself satisfy both deliverables or prove independent authorship.

## Pending

| Step | Work | Evidence required before completion |
| --- | --- | --- |
| S03 | Bootstrap API, database, CLI and test environment. | Locked dependencies, reproducible migrations, API health, shared service path and isolated DB tests; restart preserves intended state. |
| S04 | Implement source/claim contracts and policy boundaries. | Source references, ownership, scope, uncertainty, time and revision checks; Private gates exist before processing personal inputs. |
| S05 | Import and inspect the eight diagnostic observations. | Paired raw/formatted text, exact source spans, missing metadata and reimports handled without invented or duplicate evidence. |
| S06 | Produce a real source-history answer through DeepSeek. | A cited answer/draft from actual stored sources; honest unknown/failure behavior; actual provider and usage recorded where permitted. |
| S07 | Extract selective memory and reconcile changes. | Compare smaller proposers; distinguish new fact, genuine change, extraction error, tentative claim and unresolved conflict. |
| S08 | Improve retrieval only when evidence supports it. | Controlled lexical/dense/hybrid and history/claim comparisons, with response model and evidence budgets held fixed. |
| S09 | Complete controls and feedback repair. | Private/Correct/Forget success and failure paths, actual DB concurrency tests, no resurrection on retries/reimport; repair the demonstrated failing layer. |
| S10 | Connect the minimal ordinary-user interface. | Import/status, Ask, Sources, Private, Correct and Forget work through the same backend. UI is required; polish is optional. |
| S11 | Expand to approximately 500 observations and evaluate. | Separate labels, repeated live-model runs, deterministic checks, failures retained, supported task success/latency/cost/growth reported. |
| S12 | Package and verify submission. | Clean checkout → Compose start → import → process → UI → tests/evaluation → scoped reset; README/RUN, results and exact tested commit ready. |

The S01–S12 IDs match the delivery sequence discussed with the user. PLAN.md groups implementation work into commit-sized milestones; one delivery step may span more than one honest commit. Tests are incremental throughout, not postponed to S11.

## Milestone completion procedure

1. Explain important implementation scope and its gate. Follow existing approval; ask only when a material change is outside that approved scope.
2. Implement the bounded milestone and run relevant checks. Use documentation checks for documentation, actual DB tests for persistence/concurrency and explicitly labeled live runs for model behavior.
3. Inspect the diff and results. Fix failures or record the limitation without marking the milestone passed. No credentials, private data or unrelated edits enter the commit.
4. Update this tracker, relevant decisions and run instructions with what changed, what was tested, the result and the next step.
5. Create a focused commit and push it to the remote repository after every meaningful completed milestone. The user has authorized this recurring commit/push workflow; do not ask again merely to push an approved milestone.
6. Verify remote/local commit agreement and report the commit. If push fails, record that it remains local and resolve it without force-pushing over concurrent changes.

Preservation/tracker milestone checks on 11 September: UTF-8 decoding passed for nine Markdown files; all 26 then-present local links/anchors resolved; source-note counts matched 813/317; completed/ongoing/pending headings and S01–S12 coverage passed; staged whitespace passed. Environment checks are recorded in RUN.md; recheck documentation links and staged whitespace for that milestone. No application or model tests apply yet. The latest tracker commit is available through `git log --oneline -- todo.md`; avoid inventing a self-referential commit hash inside its own content.

## Open before dependent work

- Two final independently authored Phase One submissions; source-note preservation is already complete.
- Important implementation scopes remain subject to the user's review rule; do not treat approval of a step as approval for every later architecture change.
- Before live calls: provider credentials stored locally, account access, retention/no-training settings and an agreed spend/token ceiling. No secrets in chat or Git.
- Azure, graph services, response caching, streaming, autonomous procedural learning and rich UI polish remain optional after required gates pass.
