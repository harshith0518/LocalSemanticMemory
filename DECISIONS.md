# Decisions and hypotheses

Updated 11 September 2026. This distinguishes agreed product behavior from an implementation recommendation. "Promising" is not a measured result or blanket approval to implement every feature.

## Agreed requirements

- Hey Jarvis learns selective, useful, supported understanding from eligible user messages and imported dictations. History, derived memory and original Sources are distinct.
- Preserve whose claim it is, scope, attribution, uncertainty, conditions, negation, time and units. Questions/quotes/hypotheticals are not unconditional user facts. A one-off edit is not a universal preference.
- Raw and formatted dictation are one observation. Preserve material disagreement. Generated replies/drafts do not independently confirm facts or completed actions.
- Dictation writes the intended text; semantic memory must not silently insert facts. Ask Jarvis interprets a request and may retrieve permitted history. Native integration and detailed conversation organization remain open.
- Normal saves eligible history and learns/reuses permitted memory. Private uses only current input and explicitly supplied temporary context, with no saved personal reads or durable activity/content writes in any app-owned sink, including failures.
- Private starts fresh, clears temporary context on exit/page close, and never backfills Normal. Its switch preference may persist; private content may not. There is no separate pause-learning switch in v1.
- Correct distinguishes extraction mistakes from changes in the world; preserves original evidence and changes later use. Forget stops future use and relearning from supporting passages and known duplicates, including delayed work; source history may remain separately visible.
- The v1 service policy prohibits model-training use of activity. Hosted inference is possible, but provider retention must be separately checked and disclosed.
- Use supplied/replayed text; no ASR or production Jarvis integration is required. Historical instructions are source data, not execution authority.
- The project requires an ordinary-user UI, actual backend/model behavior, approximately 500 development observations, import of unfamiliar unfamiliar data, source-inspectable evaluation, reproducible run/reset instructions and an exact release commit.
- Delivery target: 12 September afternoon IST. Prefer Docker Compose; Azure is optional only after completing the local result.
- DeepSeek owns the main reasoning/response role. Compare smaller models for typed memory-operation proposals; the backend retains control of SQL, authorization and commits. Exact endpoint/model selection remains an experiment.
- Ask before important implementation edits outside an already approved bounded scope. The user requested starting with Phase One preservation and then progressing through the delivery steps.
- Maintain [todo.md](todo.md) with completed, ongoing and pending work. After every meaningful completed milestone, run relevant checks, update the tracker, commit and push; this recurring commit/push workflow is authorized.

## Proposed implementation choices

| Choice | Reason | How to reconsider |
| --- | --- | --- |
| Python/FastAPI + thin CLI sharing services | One language and one policy path for application/evaluation work. | Reconsider only for a concrete blocker, not familiarity with another framework alone. |
| PostgreSQL + pgvector and full-text search | Transactions, typed state and exact dense retrieval in one DB. | SQLite remains technically possible, but do not add a second backend under the deadline. Approve final DB choice before schema code. |
| Ubuntu 24.04 in WSL2 + Linux containers | Already installed; consistent Linux tools and portable review. | Use an existing native Ubuntu machine if already convenient; do not reinstall the host for this task. |
| One DB-backed worker; no Redis | Durable work with fewer services. | Add infrastructure only after observed throughput/reliability need. |
| Source-history baseline, then claims and hybrid retrieval | Lets evaluation isolate whether memory and search actually help. | Keep the simpler baseline if an addition has no demonstrated value. |
| Bounded smaller model for extraction | Potentially reduce repeated interpretation cost. | Compare against stronger extraction with other settings fixed; retain better quality when repair cost erases savings. |
| Buffer replies; no response cache/streaming initially | Smaller correction/revocation surface. | Add after lifecycle tests, with explicit dependency invalidation. |
| Plain minimal UI | Meet the normal-user requirement without another large application framework. | Polish after the complete path is verified. |

## Open before implementation or live calls

1. Approve the bounded bootstrap in [PLAN.md](PLAN.md), including final stack and initial schema scope.
2. Confirm access, retention/no-training settings and a spend ceiling for the [model shortlist](ARCHITECTURE.md#models-and-repair). The user selected DeepSeek main plus a smaller proposer; the proposed NVIDIA/SiliconFlow exact endpoints have not been called or compared. No credentials belong in Git or chat.
3. Finalize and preserve the author's independently authored Phase One documents. [User-supplied source notes](docs/part-one/README.md) and earlier-chat provenance are preserved; two final acceptances have not been identified. The notes do not establish independent authorship or completion.
4. Choose actual dependency/image versions during the first approved build and record them in lockfiles/configuration.

## Decision evidence format

For each substantive change, record: observed failure → proposed mechanism → alternatives → experiment/settings → results including failures → keep/reject decision. Link the actual commit and evaluation report. Do not turn planned gates into achieved metrics, invent discussions, or manufacture intermediate commits.
