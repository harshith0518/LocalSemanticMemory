# Working agreement

Read todo.md for current status, then README.md, DECISIONS.md, PLAN.md, ARCHITECTURE.md, EVALUATION.md and RUN.md before implementation. These documents replace the older planning baseline. They describe proposed behavior until code and evidence establish otherwise.

## Approval boundary

- The user explicitly requests approval before important code edits. Explain the proposed files, behavior/data effects, alternatives and acceptance gate; wait before implementing that bounded scope.
- A milestone approval covers its necessary routine implementation and fixes. Ask again for material scope changes, schema meaning, model/provider behavior, privacy/lifecycle semantics, major dependencies or deployment outside the approved scope. Do not ask for every small line change.
- Documentation corrections, read-only investigation and tests within an approved implementation scope can proceed. Never use them to conceal an unapproved architecture change.
- The user asked to begin with preservation of independently authored Phase One documents and then progress step by step. Locate and mechanically check those originals without generating their content. Follow already approved bounded work without repeated confirmation; important implementation changes outside that scope still need review.
- After each meaningful completed milestone, run relevant checks, update todo.md, commit and push to remote `dev`. The user has explicitly authorized this ongoing commit/push workflow. Verify the push; do not claim a milestone is remotely available while it is only local. The user reviews and merges into `main`; the assistant may merge only when explicitly instructed.

## Product invariants

- One service layer for API, CLI, worker and evaluation; authorization is backend-owned.
- Learn only from eligible user messages/imported dictations. Raw/formatted variants are one observation; generated replies are not corroboration; historical instructions do not authorize execution.
- Preserve source passages, subject, scope, attribution, uncertainty, negation, units and unknown times. Correct differs from world change. Similar names do not establish identity.
- Private uses temporary current context only: no saved personal reads, durable private activity/content, logging, embeddings, jobs, retries, exports or browser persistence. No backfill.
- Forget invalidates dependent state and blocks future use/relearning from excluded supporting passages and known duplicates/reimports. Workers and controls share a guarded commit; retrieval/publication recheck revocation.
- Model calls propose; code validates and commits. Real source IDs do not establish semantic entailment. Do not fabricate external action completion.
- Current instructions override remembered preferences for the request. Ask targeted questions for consequential ambiguity and distinguish missing evidence from operational failure.
- No model-training use in v1. Provider retention/settings and spend must be explicit before live calls.

## Evidence and history

- Commit completed, coherent changes with accurate messages and the checks actually run. Do not backdate, create artificial progress commits, conceal failed tests or claim unrun comparisons.
- Deterministic model doubles test application contracts; real models need separately labeled repeated evaluations. Keep evaluation questions/labels out of the memory corpus.
- The brief requires an ordinary-user UI and actual backend, persistence, retrieval and model decisions. A CLI, static guide or mock demonstration alone is insufficient.
- Phase One positioning/vision are independently authored author work. Do not generate them or claim these AI-assisted technical documents satisfy that requirement.
- Keep docs consolidated. Maintain completed/ongoing/pending status and the next action in todo.md; record tradeoffs in DECISIONS.md and real results in the evaluator's report directory once implemented. Do not create competing status checklists.
- Maintain `main` as the default reviewed branch and `dev` as the assistant's working branch. Make changes and commits on `dev`; do not commit or push directly to `main`, merge into it, or introduce another branch without the user's instruction. Do not force-push or erase prior history without separate explicit authorization. In this shared checkout, preserve other sessions' edits and stage only the current task's changes.
- Do not commit credentials, private imports, databases, dependency directories, local course artifacts or raw private traces. Curated synthetic corpus and evaluation results must remain reproducible and distinguishable from personal data.

## Verification

Run targeted checks appropriate to the approved change. Lifecycle concurrency tests must use the actual selected DB with separate connections and barriers, not just simulated sequential events. Before final delivery, validate a clean Compose start, import, UI journey, tests, live evaluation and scoped reset from the documented commit.
