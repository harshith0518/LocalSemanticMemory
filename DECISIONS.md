# Decisions and hypotheses

Updated 12 September 2026. This distinguishes agreed product behavior from an implementation recommendation. "Promising" is not a measured result or blanket approval to implement every feature.

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
- The user replaced DeepSeek with **Kimi K3** as the S06 reasoning/response candidate. Compare smaller models for typed memory-operation proposals; the backend retains control of SQL, authorization and commits. Exact endpoint/model selection remains an experiment.
- Ask before important implementation edits outside an already approved bounded scope. The user requested starting with Phase One preservation and then progressing through the delivery steps.
- Maintain [todo.md](todo.md) with completed, ongoing and pending work. After every meaningful completed milestone, run relevant checks, update the tracker, commit and push to `dev`; this recurring workflow is authorized. Keep `main` as the default reviewed branch. The user reviews and merges, or explicitly instructs the assistant to merge and push. Implementation commits belong on `dev`; the user explicitly authorized the S05 merge/push into `main`.
- Use the visual PDF and Markdown files in a fresh discussion chat to understand the design and resolve doubts; use Codex CLI for subsequent approved implementation. Keep one canonical checkout and record decisions before handing work to the coding session. Windows CLI authentication and Docker Linux access were checked in the [follow-up readiness check](RUN.md#dev-branch-readiness-check); the restricted CLI subprocess has separate access limits. The author subsequently reported Phase One complete in their possession and explicitly approved S03. Proceeding with that scope is authorized; repository preservation/mechanical checks of those finals remain pending.

## Proposed implementation choices

| Choice | Reason | How to reconsider |
| --- | --- | --- |
| Python/FastAPI + thin CLI sharing services | One language and one policy path for application/evaluation work. | Reconsider only for a concrete blocker, not familiarity with another framework alone. |
| PostgreSQL + pgvector and full-text search | Transactions, typed state and exact dense retrieval in one DB. | SQLite remains technically possible, but do not add a second backend under the deadline. PostgreSQL with pgvector is explicitly approved for S03. |
| Docker Desktop Linux containers with Ubuntu-24.04 integration; keep one Windows checkout for the initial image build | Existing engine and WSL integration passed readiness checks. Copy source into images and use named DB volumes, avoiding a source migration before bootstrap. | Consider a Linux-filesystem checkout if live bind mounts become useful; do not create two competing checkouts or reinstall the host. |
| One DB-backed worker; no Redis | Durable work with fewer services. | Add infrastructure only after observed throughput/reliability need. |
| Source-history baseline, then claims and hybrid retrieval | Lets evaluation isolate whether memory and search actually help. | Keep the simpler baseline if an addition has no demonstrated value. |
| Bounded smaller model for extraction | Potentially reduce repeated interpretation cost. | Compare against stronger extraction with other settings fixed; retain better quality when repair cost erases savings. |
| Buffer replies; no response cache/streaming initially | Smaller correction/revocation surface. | Add after lifecycle tests, with explicit dependency invalidation. |
| Plain minimal UI | Meet the normal-user requirement without another large application framework. | Polish after the complete path is verified. |

## S03 implementation decisions and evidence

The approved bootstrap uses synchronous SQLAlchemy/psycopg sessions in one shared service layer, with thin FastAPI/Typer adapters. Python 3.12, uv and PostgreSQL/pgvector images are pinned by digest; application, test and build dependencies are locked. One image includes developer checks, trading some image size for a single reproducible local environment. No production deployment is implied.

Use a standalone `compose.test.yaml` project instead of a test profile sharing application configuration: this keeps application credentials, networks and volumes out of test services. A fail-closed target guard protects migration/fixture cleanup. Runtime logins have DML only; separate migration logins own the schema. The administrator enables pgvector once during empty-volume initialization because extension installation needs elevated DB privileges. Alembic creates only the three approved logical records; no vector data/search is implemented.

`/health` / `jarvis health` are liveness; `/ready` / `jarvis ready` check DB/schema/extension readiness. The synthetic probe's fixed paired text, hash, source identity, unknown capture metadata, policy revision and pending job establish a small durable transaction without exposing a general importer before S04. Source revisions are separate records; equal text does not establish identity. Model/provider behavior and privacy/lifecycle meanings are unchanged.

Keep these choices based on 23 passing isolated PostgreSQL tests, repeated migration/no-drift checks, runtime privilege checks, real outage recovery and exact state after container replacement. The first lint/format issues and test-client deprecations were resolved; actual commands and limits are in [RUN.md](RUN.md). No comparison against SQLite, another architecture or live models was run.

## S04 implementation decisions and review

The user explicitly approved typed observations/passages/claim revisions, ownership/version/exact-support validation, backend request identity, Normal/Private gates, guarded writes and an additive migration. Implemented within that scope, with no dependency changes, model calls, general importer, retrieval or UI.

Keep Pydantic contracts with strict text/boolean/revision fields and explicit-precision time. Store owned claim revision metadata and evidence links relationally, with typed claim content in JSONB. This avoids prematurely flattening every subject/value/time alternative into a broad schema while preserving exact source links and inspectable payloads. A later query requirement can justify a reviewed indexing/schema change. Do not infer resolved entity IDs or semantic entailment from labels or valid passage IDs.

Require request contexts for all new service operations; adapters resolve the local owner and accept only a validated mode. The old fixed synthetic probe remains compatible, and its CLI now passes mode explicitly. Private rejects personal-store operations before parsing or SQL. Pure input validation has no saved context or side effects. Disable persistent API/CLI container logs in addition to suppressing input/error logging; otherwise even a sanitized CLI receipt could leave durable Private activity. This sacrifices stored operational logs in the supported local setup; it does not certify third-party clients or future providers.

Use the same policy-row lock for source writes and supported claim writes, with policy/source/claim revisions rechecked within the transaction. Read-only validation is advisory and cannot authorize a later unchecked write. Two real connections and barriers verify both lock orderings; concurrent claim appends cannot both consume the same expected revision. Source evidence reads are batched. Automatic reconciliation and Correct/Forget semantics remain outside S04.

Self-review against AGENTS/ARCHITECTURE/EVALUATION: this establishes evidence and policy boundaries before S05 ingestion; preserves paired observations, unknown times, attribution and uncertainty; keeps authorization in one service layer; and distinguishes contract tests from semantic/model evidence. Keep the current direction based on 75 passing checks, preserved S03 state and live adapter checks, not a claimed comparison with another architecture. Next review must address import namespace/idempotency and eligibility, then real extraction entailment and full lifecycle revocation. [Commands/results](RUN.md#actual-s04-results)

## S05 implementation decisions and review

The user approved the next diagnostic import/inspection step and explicitly requested merging the tested work into `main` and pushing. Retain the existing owner-scoped source key, reserving `import:<namespace>:<record_id>` for immutable imports. This avoids a second identity table or migration while giving each original observation stable, reversible identity. Content hashes alone would wrongly collapse separately authored observations; filename-based namespaces would make renamed reimports duplicate evidence. The caller must keep the collection namespace and original IDs stable.

Accept bounded UTF-8 JSONL matching the supplied fixture: `record_id`, `raw_transcript`, optional `formatted_text` and metadata. Store only the eligible imported-dictation kind; reject unknown top-level role/owner/schema fields. Keep raw/formatted discrepancies and missing metadata intact. Schema checks cannot determine whether a caller's purported dictation was actually authored by that person; imported instructions remain inert source text. Copied source/evaluator files are byte-identical to the parent originals and stored separately. API import accepts bytes; CLI stdin keeps input out of shell arguments.

Keep the existing owner policy lock and atomic source/job transaction. Batch source/job inserts use two flushes rather than separate per-record commits. Exact reimport returns original state and never requeues; changed content/metadata under the same identity fails the whole batch. A permissive upsert was rejected because it would silently revise source evidence outside a defined correction workflow. Full Correct/Forget and cross-namespace duplicate exclusions remain later work. Number comparison respects JSONB's numeric representation while distinguishing booleans; an explicit UTF-8 HTTP charset fixes the observed Windows PowerShell response decoding failure.

Self-review against AGENTS/PLAN/ARCHITECTURE/EVALUATION: one service owns all import/list/inspect policy and writes; API/CLI have no SQL or model calls; Private gates precede input/store reads; original variants/unknown times are preserved; source identity does not claim corroboration, truth or entailment. Keep the approach based on the 111 passing isolated checks and actual application persistence/adapter evidence in [RUN.md](RUN.md#actual-s05-results). No alternate architecture or model comparison was run. Next: S06 source-history answers, with provider and budget approval before live calls.

## Browser-first UI decision

The user explicitly requested moving the minimal frontend forward so ordinary users do not need CLI commands. Keep the tested backend and optional developer CLI; serve plain HTML/CSS/JavaScript directly from FastAPI. No framework, frontend server, Python dependency change or migration is needed. This makes real import/inspection usable immediately while S06's provider decision remains open. This is the early source-workspace part of S10, not completion of Ask/Correct/Forget.

The UI uses the same owner/policy-aware API. It fetches a current policy revision before import, preserves stable collection/record IDs, distinguishes commit success from refresh failure and shows exact paired text, unknown capture time and processing status. A fixed collection name is only a starting input; no data is loaded automatically and unfamiliar valid collections work. Sensitive text is rendered as text, with no browser persistence or third-party assets. Mode changes discard the current page context and reject late responses. A previously accepted Normal import can still finish; switching mode is neither a transaction rollback nor Forget.

Alternatives: a separate SPA toolchain adds packaging/runtime surface without improving this bounded flow; removing the existing CLI would discard useful automation without helping browser users. Keep both adapters around the shared service. Validate the user journey with real Chromium against the isolated PostgreSQL backend, plus existing backend regressions and public-asset privacy checks. [Actual results and commands](RUN.md#browser-workflow)

## S06 readiness decisions

The user requested an audit against the visual guide, commit/push to `main`, and starting S06. The audited S05 commit is `a599414b431783661f54aff2c542a11ebeb0e78a`; both remote branches matched it before this documentation checkpoint. A fresh image rebuild passed all 111 isolated PostgreSQL tests (12.56 s), Ruff lint/format passed, and the application database has no migration drift. Retain the current shared-service/evidence/policy architecture; these results do not establish model quality or later lifecycle/UI behavior. [Detailed audit](RUN.md#s06-readiness-audit)

**Updated model choice:** use `moonshotai/kimi-k3` as the first response candidate. Keep `nvidia/nemotron-3.5-lightning-30b-a3b` for S07 extraction experiments. `nvidia/nemotron-3-ultra-550b-a55b` is only an optional later comparison/backup candidate; a locally configured key does not approve automatic fallback or additional model comparisons. The reported 13 September DeepSeek free-access cutoff was not independently verified and is not recorded as provider fact.

**Provider policy remains open:** the linked NVIDIA trial terms permit activity/error logging and use of content to improve models; the trial also restricts confidential/personal inputs. A free prototype endpoint is not proof of zero retention or no training. Kimi and Ultra model cards link these terms. This conflicts with the existing no-training requirement unless the user explicitly approves a narrower exception. [NVIDIA API Trial Terms, sections 2.3, 2.6 and 3.3](https://assets.ngc.nvidia.com/products/api-catalog/legal/NVIDIA%20API%20Trial%20Terms%20of%20Service.pdf)

An explicit **synthetic-only** trial exception has been proposed, not approved: only the checked-in diagnostic sources/questions; $0 paid spend; at most 32 total requests and 500,000 total input/output tokens including retries. Personal inputs and Private provider calls stay blocked. Alternative: keep all live calls disabled until a provider agreement/settings satisfy no training. Unknown usage after a timeout must consume its conservative reservation rather than disappearing from accounting. No provider request has been made and no response quality, free quota or credential validity is claimed.

The PDF remains the original planning snapshot. Its DeepSeek labels and pre-bootstrap status are superseded by this decision and the tracker; the evidence, policy, staged delivery and evaluation diagrams remain applicable. Do not rewrite the historical PDF simply to imply that every depicted capability is implemented.

## Input-to-memory research review

On 12 September the user requested confidence in the input/storage design before S07 implementation. Reviewed the current Markdown, parent brief/research notes and the visual guide, especially pages 4–7 and 17. These agree on selective learning, original evidence, revision history and one PostgreSQL store. The following external evidence supports testing that direction; it does not establish our models' accuracy or authorize new implementation.

| Primary source | Finding and implication for this project |
| --- | --- |
| [LongMemEval, sections 5.2–5.3](https://arxiv.org/html/2410.10813v1) | Replacing source text with summaries/facts often reduced answer quality; adding extracted facts to original-text search keys helped in the tested settings. Preserve source access and test claims as an addition. Results varied by reader and task, so this does not prove that our proposed retrieval design is optimal. |
| [Mem0, section 2.1](https://arxiv.org/html/2504.19413v1) | Separates extraction from memory updates. Borrow that separation, with backend validation and revision history. Its user/assistant input handling and model-selected deletion are not our eligibility or Forget contract. Its reported evaluation excludes adversarial questions; it cannot establish our abstention/privacy guarantees. |
| [PostgreSQL JSON types](https://www.postgresql.org/docs/17/datatype-json.html) and [W3C provenance](https://www.w3.org/TR/prov-dm/) | JSONB supports structured content; provenance distinguishes sources, derivations and revisions. Our recommendation is exact source strings in TEXT, validated claim content in JSONB, and relational IDs, ownership, revisions and evidence links. JSONB preserves string values but not original JSON serialization, key order or duplicate keys; do not claim byte-identical import-file archival. |
| [pgvector](https://github.com/pgvector/pgvector) | Exact and approximate vector search can share PostgreSQL with existing state. An embedding is a derived search aid, not authoritative memory or proof of meaning. Start with the planned lexical baseline, then test exact dense search; add ANN only for a measured need. |

**Recommended design:** preserve eligible Normal source history; extract only reusable facts, scoped preferences and useful reported events; retain exact supporting passages and context-complete qualifiers; reconcile under the existing policy/revision guard. One-off response instructions, questions, quotes and hypothetical examples do not automatically become lasting personal facts. A real conditional plan may be useful but must stay conditional. Save permission and memory usefulness are separate decisions: a stored observation can yield zero claims. This is a refinement of the existing product invariants, not a new retention policy.

Keep canonical source, passage and claim-revision records in PostgreSQL. Use explicit lifecycle/relationship history rather than overwriting a profile summary. Raw/formatted text remains one observation, and equal text is not an identity key. Model calls propose outside DB locks; the shared service rechecks ownership and revisions, then commits the whole accepted operation and its receipt. Source fallback must obey the same exclusions as claims, including later Forget controls. These controls are required engineering properties, not findings established by the cited model benchmarks.

**Alternatives and confidence:** do not introduce a separate vector/graph database, summary-only memory, unbounded automatic extraction, or a model's confidence score as a truth probability without evidence that justifies them. The implemented schema already supports the core representation. Extraction usefulness, reconciliation quality and embedding benefit remain unmeasured here. LongMemEval also tests assistant-side information, whereas our memory eligibility is user-only; external scores cannot be imported as product results. Run the [controlled comparisons](EVALUATION.md#4-compare-mechanisms-without-confounding) and retain the simpler baseline if added memory does not help. S06 remains the answer baseline; S07 may share its proposed provider/accounting foundation but cannot establish an answer-quality improvement before that baseline exists.

No live calls, application changes or new runtime tests were performed for this research checkpoint. S07 files/data effects and acceptance are now collected in [the pending proposal](PLAN.md#s07-bounded-proposal-after-research-review). Provider approval remains separate.

## Open before later implementation or live calls

1. Start S06 from the [bounded proposal](PLAN.md#s06-bounded-bootstrap-proposal). Review the proposed inference/accounting changes before important code edits under AGENTS.md; the user has requested starting the milestone.
2. Confirm access, retention/no-training settings and a spend ceiling for the [model shortlist](ARCHITECTURE.md#models-and-repair). The user selected Kimi K3 for S06 and Nemotron Lightning for S07; Ultra is optional, with no automatic fallback. The endpoints and locally configured keys have not been authenticated or compared. No credentials belong in Git or chat.
3. Preserve and mechanically check the final Phase One documents when supplied. The author reports them complete and held separately; the assistant has not inspected them. [Earlier source notes/drafts](docs/part-one/README.md) retain their own provenance and do not establish independent authorship.

## Decision evidence format

For each substantive change, record: observed failure → proposed mechanism → alternatives → experiment/settings → results including failures → keep/reject decision. Link the actual commit and evaluation report. Do not turn planned gates into achieved metrics, invent discussions, or manufacture intermediate commits.
