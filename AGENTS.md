# Working agreement

Read todo.md for current status, then README.md, DECISIONS.md, PLAN.md, ARCHITECTURE.md, EVALUATION.md and RUN.md before implementation. These documents replace the older planning baseline. They describe proposed behavior until code and evidence establish otherwise.

## Approval boundary

- The user explicitly requests approval before important code edits. Explain the proposed files, behavior/data effects, alternatives and acceptance gate; wait before implementing that bounded scope.
- A milestone approval covers its necessary routine implementation and fixes. Ask again for material scope changes, schema meaning, model/provider behavior, privacy/lifecycle semantics, major dependencies or deployment outside the approved scope. Do not ask for every small line change.
- Documentation corrections, read-only investigation and tests within an approved implementation scope can proceed. Never use them to conceal an unapproved architecture change.
- The user asked to begin with preservation of independently authored Phase One documents and then progress step by step. Locate and mechanically check those originals without generating their content. Follow already approved bounded work without repeated confirmation; important implementation changes outside that scope still need review.
- After each meaningful completed milestone, run relevant checks, update todo.md, commit and push to remote `dev`. The user has explicitly authorized this ongoing commit/push workflow. Verify the push; do not claim a milestone is remotely available while it is only local. The user reviews and merges into `main`; the assistant may merge only when explicitly instructed.

## Product invariants

- The browser UI is the primary ordinary-user workflow. Users import, inspect and use later Ask/controls without CLI commands; the existing CLI is optional developer/automation tooling.
- One service layer for UI via API, optional CLI, worker and evaluation; authorization is backend-owned.
- Learn only from eligible user messages/imported dictations. Raw/formatted variants are one observation; generated replies are not corroboration; historical instructions do not authorize execution.
- Preserve source passages, subject, scope, attribution, uncertainty, negation, units and unknown times. Correct differs from world change. Similar names do not establish identity.
- Private uses temporary current context only: no saved personal reads, durable private activity/content, logging, embeddings, jobs, retries, exports or browser persistence. No backfill.
- Forget invalidates dependent state and blocks future use/relearning from excluded supporting passages and known duplicates/reimports. Workers and controls share a guarded commit; retrieval/publication recheck revocation.
- Model calls propose; code validates and commits. Real source IDs do not establish semantic entailment. Do not fabricate external action completion.
- Current instructions override remembered preferences for the request. Ask targeted questions for consequential ambiguity and distinguish missing evidence from operational failure.
- No model-training use in v1. Provider retention/settings and spend must be explicit before live calls.
- User-approved prototype exception, reconfirmed 12 September 2026: NVIDIA may receive checked-in synthetic sources/questions despite its training/retention terms. The shared persisted lifetime ceiling is 750 requests and 10,000,000 accounted tokens, including retries and unknown-usage reservations, at $0 paid. Reserve the final 30 requests for the demo by limiting batch evaluation to lifetime request 720. Preserve the existing budget key and all prior consumption. This replaces the earlier 96-request / 1,500,000-token pilot. Private provider requests remain blocked; unfamiliar Normal-mode input requires the separately approved explicit unfamiliar opt-in below. No automatic provider fallback.

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

## Approved evening extension (12 September 2026)

The user also approved the S14 local completion follow-up: responsive/Pause fixes, general retrieval ranking improvements, and paced Google Flash-Lite for the remaining checked-in synthetic evaluation under the SAME persisted 750-request / 10,000,000-token / $0 ceiling, with the final 30 requests reserved for the demo. Google free-tier data-use terms were disclosed; its synthetic approval and acknowledgement must remain explicit. This is not permission for Google/OpenRouter Private requests or an undisclosed personal-data fallback. Normal NVIDIA unfamiliar mode was explicitly enabled locally for unfamiliar dummy inputs after the NVIDIA warning. On completion of final checks the user expressly requested merging the finished dev work into main and pushing main for submission; no force-push or history rewrite is authorized.

The user explicitly approved extending the NVIDIA synthetic exception to the checked-in 540-record corpus and its separate questions, with a combined persisted lifetime ceiling of 750 requests / 10,000,000 accounted tokens including retries/unknown reservations, $0 paid. Preserve the existing budget key and consumption; no automatic model fallback. The user also explicitly approved default-off unfamiliar inference for unfamiliar Normal-mode input using their own NVIDIA key, requiring an affirmative flag AND the exact data-policy acknowledgement. NVIDIA retention/training terms may apply and must be visible in setup. Private remains completely blocked. This supersedes older synthetic-only/pending-review notes only for this explicit operator-controlled mode. Details and acceptance are consolidated in DECISIONS.md, PLAN.md and EVALUATION.md.

## Final evaluation extension approved 12 September 2026, 23:07 IST

The user explicitly approved a combined persisted ceiling of 1,100 requests / 10,000,000 accounted tokens / $0 paid, preserving 30 requests for the demo and all prior consumption under `s07-synthetic-v1`. This supersedes earlier 750-request limits, not the token, retention, lifecycle or no-paid-fallback boundaries. The final batch cutoff is 23:40 IST, followed by the already authorized dev push and main merge/push. Resume the same saved corpus; do not reset counters or re-create history. Current provider quotas remain unverified, so a completed or successful 540-record run cannot be promised.
