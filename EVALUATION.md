# Evaluation

## What is measured, and what is not

Three questions get confused in memory projects, so this repository keeps them apart:

| Question | Answered by | Never inferred from |
| --- | --- | --- |
| Does the application enforce its own contracts? | Deterministic suites against a real PostgreSQL instance with model doubles | Live model output |
| Did a real model behave acceptably on a recorded input? | Live runs retained as raw artifacts, including failures | Schema validity, token counts, citation presence |
| Is the memory semantically right? | Manual review of retrieved passages, conditions and duplicates — labelled as such | Any automatic screen |

Everything below is a recorded result. Where a run failed, was rate-limited or was stopped, that is
what it says. Raw artifacts are in `eval/reports/`.

## Layer 1 — Deterministic contracts

Run with `docker compose -f compose.test.yaml run --build --rm tests`. Real PostgreSQL, real
transactions, separate connections where concurrency matters, deterministic model doubles.

Latest full run: **369 passed in 136.13 s** (0 failed).

| Area | Representative checks |
| --- | --- |
| Capture and idempotency | Immutable observations, raw/formatted pairing, late-response retries, concurrent capture on two connections, cross-user rejection. |
| Import | Bounded batches, exact retry, changed-field conflict, invalid UTF-8/NUL/naive timestamps, atomic rollback, capture-versus-import time. |
| Assessment | Exact unique excerpts, independent retention/route fields, request/owner/policy binding, concurrent leases, bounded retries and repair, over-budget output, Private zero access. |
| Extraction | Passage strictness (no invented offsets), allowed transitions, duplicate and support handling, world change versus correction, conflict retention. |
| Retrieval | Ownership and revision filters, exclusion rechecks, byte budgets, no-clipping errors, partial coverage reporting, deterministic tie-breaking. |
| Controls | Preview/apply, policy increments, dependent-state invalidation, replication across stored history and copies, receipts and replay, cross-user denial. |
| Lifecycle concurrency | Two real connections with barriers: worker-then-control, control-then-release, Forget during publication, plus the reverse orderings. |
| Failure handling | Provider errors as operational failures, unknown usage preserved as unknown, pending jobs resumable, retry bounds enforced. |

**Limit:** these prove the plumbing, not the semantics. A model double cannot be wrong in the way a
real model is wrong, which is precisely why the next layer exists.

## Layer 2 — Browser journeys

Run with the isolated `browser` profile against `http://127.0.0.1:8001/`; the suite refuses the
application database and provider keys.

- **26 journeys in 48.49 s** at the 12 September checkpoint.
- The later aggregate rerun completed 18 journeys and then stalled at the delayed *Private cancels
  pending learning* case. It was stopped manually; the remaining cases are unverified at that
  checkpoint. This is recorded as an unfinished acceptance run, not as a passing or failing verdict.

The journeys assert things a contract test cannot: that Import and Open do not read saved data on their
own, that a search is not learned, that a citation expands to a real source, that a general answer is
visibly separate from cited text, that correcting changes the displayed history, that Private writes
nothing and that the page attempted no external request or browser-storage write.

**Limit:** Chromium only. No cross-browser, mobile-emulation or accessibility-conformance suite.

## Layer 3 — Live corpus run

540 synthetic records imported as one namespace, 30 held-out questions kept out of the corpus.

| Outcome | Count |
| --- | --- |
| Sources imported (read-only database audit) | 540 |
| Jobs succeeded | 365 |
| — of which extracted | 328 |
| — of which produced **no memory** on purpose | 37 |
| Jobs failed | 78 |
| Still pending at cutoff | 97 |
| Stop reason | `rate_limited` at attempt 175 |
| Last batch | 233 requests in 993.5 s (≈4.3 s/request) |

This is the most important number in the document, and it is not 540. The application was still
importing sources and queuing learning when the provider cut it off; the run is reported as partial.

**Limit:** the corpus is synthetic and author-written. It exercises mechanisms — dates, negation,
scoped preferences, duplicates, reimports, corrections — and says nothing about recall on real,
messy dictation.

## Layer 4 — Live showcase

Thirty authored cases answered twice against the same synthetic collection.

| Run | Mechanical screens | Operational failures | Provider requests | Known input / output tokens |
| --- | --- | --- | --- | --- |
| Baseline | 13 / 30 | 4 | 31 | 58,057 / 6,520 |
| Retest | 16 / 30 | 3 | 30 | 97,494 / 7,158 |

In the retest, 27 of 30 cases returned an answer (17 answered, 6 drafts, 4 explicit unknowns) and
**26 of those 27 cited every required source**. The three remaining cases failed operationally.

A "mechanical screen" checks that the expected string or source appears at all — it is a screening
assertion, not a grading of meaning. Retained real defects include arithmetic errors, an unsupported
blocker label, response-status errors and one update-retrieval miss.

**Limit:** no frozen-state A/B comparison of mechanisms, and the semantic review step remains
manually labelled rather than scored.

## Layer 5 — Retrieval diagnostic

Frozen 500-record authored corpus, 17 cases × 3 repeats, two representations (originals only;
originals + claims), same questions:

| Representation | Answerable attempts | All required evidence found | p50 / p95 | Mean evidence bytes |
| --- | --- | --- | --- | --- |
| Sources only | 45 / 51 | 45 (passage coverage 1.0) | 125.6 / 186.6 ms | 2,369 |
| Sources + memories | 45 / 51 | 45 (passage coverage 1.0) | 243.5 / 401.1 ms | 5,378 |

Zero live model calls: the claim proposals are explicit deterministic fixtures, so this measures
retrieval and packing, not generation.

**Limit:** the questions were written while the corpus was in view. High agreement here says the
ranking is not broken, not that retrieval generalises.

## Resource and storage measurements

| Measure | Value | Scope |
| --- | --- | --- |
| Database size, before → after the final batch | 11.07 MB → 11.44 MB | Whole database, all owners |
| `claim_revisions` relation | 376 KB → 541 KB | Whole relation |
| Peak RSS, final batch | 105,836 KiB (≈103 MiB) | Evaluator process |
| CPU time, final batch | 161.03 s | Evaluator process |

Storage is reported as owner-scoped TEXT/JSONB/passage payload bytes in the UI, which is smaller and
more meaningful per collection than relation size, and does not pretend to be allocated disk or RAM.

Latency is reported per call from monotonic clocks. Server spans are inclusive and nested, so they must
not be summed; the browser round-trip is measured separately. Provider billing is not connected, so
actual cost is **unknown**, not zero.

## Provider allowance accounting

The shared persisted ledger records every request, retry, repair and unknown-usage reservation.

| At the final audit | Value |
| --- | --- |
| Requests consumed | 720 |
| Accounted tokens | 5,857,878 |
| Request ceiling / token ceiling | 1,500 / 10,000,000 |
| Paid spend authorised | $0 |

Unknown usage reserves conservatively instead of counting as free. Remaining allowance does not imply
remaining provider quota: the run above stopped on a rate limit with allowance left.

## Reproducing

```powershell
# Deterministic contracts (resets the isolated test database)
docker compose -f compose.test.yaml run --build --rm tests

# Retrieval diagnostic
docker compose -f compose.test.yaml run --rm tests python eval/retrieval.py

# Corpus validation (no provider calls)
docker compose run --rm --no-deps --entrypoint python cli eval/corpus.py --stage validate
```

A live run additionally needs a provider key, the consent flags from
[RUN.md](RUN.md#configuration) and available allowance. Re-running live evaluation spends the shared
ledger and is not part of routine verification.

## Retained limitations

1. No complete 540-record successful processing run; the final batch was rate-limited.
2. Semantic correctness is not certified by valid JSON, plausible wording or citations.
3. The browser acceptance run is incomplete at the current checkpoint.
4. The showcase is not a blind benchmark: the cases were authored alongside the mechanisms they
   exercise, and only mechanical screens — not semantic grades — were scored automatically.
5. Provider billing is unavailable, so cost per task is undefined.
6. Only Chromium is exercised; no accessibility conformance claim is made.
7. Retrieval is lexical and structured — there is no dense-retrieval baseline to compare against.
