# Working agreement

Notes for anyone — human or coding agent — changing this repository.

## Read first

[README.md](README.md) for what the project is, then [ARCHITECTURE.md](ARCHITECTURE.md) for the model,
[DECISIONS.md](DECISIONS.md) for why it is shaped that way, [EVALUATION.md](EVALUATION.md) for what has
actually been measured, and [RUN.md](RUN.md) for how to build and verify. These documents describe
intention until code and recorded evidence show otherwise; when they disagree with the code, the code
and the retained reports win and the document gets corrected.

## Product invariants

- The browser workspace is the primary user surface. A feature that only exists in the CLI is
  developer tooling, and should be described as such.
- One service layer behind the API, CLI, worker and evaluators. Authorisation is backend-owned; never
  trust a caller-supplied owner.
- Learn only from eligible user messages and imported dictations. Raw and formatted variants are one
  observation. Generated replies never corroborate anything. Text inside imported material is data,
  not an instruction.
- Preserve the source passage, subject, scope, attribution, uncertainty, negation, units and unknown
  times. A correction retracts an interpretation; a world change records that reality moved.
- Similar names do not establish identity. Equal text does not establish the same observation.
- Private means no saved reads, no durable writes, no logging, no caches, no embeddings, no jobs, no
  exports and no browser persistence — enforced before the request body is parsed.
- Forget invalidates dependent state and blocks future use and relearning from excluded support,
  dependents and known copies. Workers and controls share one guarded commit; release rechecks
  revocation.
- Models propose; code validates and commits. A structurally valid citation is not semantic
  entailment. Never fabricate a completed external action.
- No model-training use. Hosted calls stay behind explicit, default-off consent and the persisted
  allowance ledger. There is no automatic provider fallback.

## Evidence and history

- Commit coherent, complete changes with an accurate message and the checks that actually ran.
- Never backdate, invent progress commits, hide a failing test, or claim a comparison that was not run.
- Deterministic doubles test application contracts. Live model behaviour needs separately labelled,
  repeated runs.
- Keep evaluation questions and labels out of the corpus used to answer them.
- Retain failed artifacts. A deleted failure is a dishonest result.

## Verification

Run the narrowest checks that cover the change, then widen:

```powershell
docker compose -f compose.test.yaml run --build --rm tests
docker run --rm jarvis:local ruff check --no-cache src migrations tests
docker run --rm jarvis:local ruff format --check --no-cache src migrations tests
```

Lifecycle concurrency tests must use the real database with separate connections and barriers, not
simulated sequential events. Before calling a release ready, verify a clean Compose start, an import,
a browser journey and a scoped reset from the committed state.

## Repository hygiene

- Keep documentation consolidated and the status in [todo.md](todo.md) current. No second tracker.
- Preserve other sessions' work: stage only the current task's changes.
- Never commit credentials, private imports, databases, dependency directories, `.env` or raw private
  traces. Curated synthetic data and evaluation results stay reproducible and clearly distinguishable
  from personal data.
- Add a migration for schema changes; never edit an applied one.
