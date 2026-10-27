# Decisions

Each entry states the choice, the reason, and the tradeoff I accepted. Where a decision was later
revised, the revision is recorded rather than silently replaced.

## Sources are canonical, memory is derived

Originals live in `TEXT`, claim bodies in validated `JSONB`, and ownership/revision/evidence links as
relational constraints. Indexes are rebuildable; the observation is not.

**Tradeoff:** claims can drift from the wording that produced them, so every claim carries explicit
passage spans and every repair path is a new revision. Storage is larger than a "just embed the text"
design and querying is more work.

## Retention and answering are independent decisions

An assessment returns two separate fields: whether to retain (`skip` / `candidate`) and how to answer
(`general` / `contextual` / `mixed` / `live` / `clock` / `clarification`). Earlier versions inferred
retention from pronouns and keywords; that conflated "this is about you" with "this states a fact".

**Tradeoff:** one extra model call per turn and a new failure surface (assessment can fail while saving
succeeds). Assessment failures are visible and retryable, and a failed assessment never blocks an
answer from already-saved evidence.

## Learned excerpts must come from selected assertions

The extractor may cite only the exact excerpts the assessment selected from the current input, and the
code derives offsets rather than accepting model-supplied ones. An observed live failure — the model
guessing character offsets — is what forced this.

**Tradeoff:** an assertion the assessment missed cannot be recovered during extraction. That is the
intended direction: under-learning is visible, over-learning is not.

## Conflict is preserved; correction is not a change in the world

Two sources disagreeing on the same subject/property/scope produce a disputed state with both variants
retained. `corrected` retracts a wrong interpretation; `superseded` records that reality changed. Both
keep history.

**Tradeoff:** "newest wins" is simpler and produces cleaner answers. It also destroys the ability to
answer historical questions and to explain why a value changed. I chose explainability.

## Forget is conservative and relational

Forget excludes the claim family's supporting observations, dependent claims, known full-variant copies
and literal supporting-passage reimports — whole observations, not spans.

**Tradeoff:** forgetting one budget figure can also block an unrelated detail that shared the note.
Unseen paraphrases are not detected either. I preferred an over-broad exclusion that can be explained
over a fuzzy matcher whose misses are invisible. Original inspection stays available because
overlapping evidence is not the private content itself.

## One policy revision guards every write

Cargo, worker, control and answer paths all take the per-owner policy row lock, verify expected
source/claim/policy revisions inside the transaction, and commit atomically. Workers hold a lease and
fence themselves with a receipt. Answers are serialised at a release point that recomputes eligibility.

**Tradeoff:** throughput is bounded by one serialisation point per owner, and the code carries more
revision plumbing than a single-user app seems to need. The alternative — pre-checks followed by
unguarded writes — is exactly the race this design exists to prevent. Lifecycle races are tested with
two real PostgreSQL connections and barriers, not with sleeps.

## No vector search yet

pgvector is installed but no embedding is stored and no dense retrieval is claimed. Recall is lexical
(GIN full-text with cover-density ranking) plus structured claim matching, with the shortest query path
staying in the database.

**Why:** a vector index without an embedding lifecycle, backfill strategy and held-out dense evaluation
would be decoration. The honest version is to say "lexical" and measure it.

**What would change it:** a versioned embedding model, a migration with backfill, revocation-aware
re-indexing, and a frozen A/B against the lexical baseline. None of those exist, so the claim stays
absent.

## Memory-first retrieval instead of a context dump

Automatic retrieval selects active learned claims first, attaches *just* their supporting originals,
then adds a bounded lexical original for unextracted detail. Complete small-collection review is
reserved for explicit inventory requests and capped at 50 sources / 80 memories / 24,000 bytes.

**Tradeoff:** a paraphrase with no lexical overlap can miss. The mitigation is an explicit
structured-diversity fallback labelled as partial coverage — not a quiet claim of semantic similarity.
Earlier versions serialised the entire small collection into the prompt; that scaled the wrong way and
made the citation surface meaningless.

## Validate in code, propose with models

Models return typed proposals; Python checks schema, ownership, real spans, exclusions and allowed
transitions. A valid quote is treated as a structurally valid reference, never as proof of entailment.

**Tradeoff:** the validator can be stricter than the model and reject good proposals (it does; repair
attempts are recorded). Structural validity is still not meaning, so semantic review stays a separate,
explicitly labelled step rather than something the schema appears to certify.

## Answers are buffered, not streamed

Responses are serialised at a guarded release point after validation. There is no token streaming and
no response cache in this version.

**Tradeoff:** slower perceived latency. In exchange, revocation has a defined boundary, a superseded
value cannot appear mid-stream, and a failed validation never reaches the browser as a partial answer.
The UI states clearly that already-released bytes cannot be recalled; that is a limitation, not a
guarantee.

## Postgres, no Redis, one worker

One database holds policies, sources, passages, claims, jobs, budgets and call accounting. One worker
process consumes leases. No Redis, no separate vector service, no queue broker, no orchestrator.

**Tradeoff:** less throughput headroom. At single-operator scale the operational simplicity is worth
more, and adding infrastructure before observing a bottleneck would be speculation.

## The browser is the product; the CLI is a developer tool

The React workspace is the ordinary-user surface. The CLI exists for diagnostics and evaluation and
shares the same service layer.

**Tradeoff:** two adapters to keep in sync. The alternative — a CLI-first tool with a demo UI — would
misrepresent what the thing is for.

## The client stores nothing

No cookies, no localStorage/sessionStorage, no IndexedDB, no service worker, no analytics, no
third-party assets, no client cache. Saved reads happen only after an explicit action. Private state
is memory-only and cleared on exit.

**Tradeoff:** every navigation re-fetches, and a page reload loses the current conversation view. That
is preferable to a "private" mode whose text is recoverable from browser storage.

## Private is a code path, not a UI toggle

Private gates run before request bodies are parsed. Service-layer checks are duplicated at the adapter
boundary, so a new endpoint cannot accidentally inherit access. The optional direct-chat route opens no
database session and stores nothing.

**Tradeoff:** more duplicated guards and an awkward product edge — the direct-chat question still
leaves the machine, so the mode is "private to my database", not "private to the network". The UI says
exactly that instead of implying more.

## Consent, cost and allowance are explicit and persisted

Hosted inference needs a default-off flag plus an exact data-policy acknowledgement, per surface. The
shared ledger records requests and accounted tokens, counts failures and repairs, and survives
restarts. Unknown usage reserves conservatively rather than counting as zero.

**Tradeoff:** bookkeeping code that has nothing to do with memory quality, and a demo can be blocked by
its own ledger. It was: a configured key worked while the application refused to call, which is the
correct behaviour and had to be explained rather than bypassed.

## No automatic provider fallback

A provider failure is reported as an operational failure. There is no silent switch to another model.

**Tradeoff:** a single provider outage degrades the demo. A fallback would make results unattributable —
you would not know which model produced an answer, or which terms applied to the data.

## Readable citations, identifiers behind a disclosure

Answers cite a meaningful source label and a short excerpt; UUIDs and source keys live in a closed
*Technical reference* section. The metrics panel says **sent to the answer model**, not "understood".

**Tradeoff:** slightly less traceability on the main surface. The source inspector and the technical
disclosure keep it available, and the wording keeps the measurement claim honest.

## Contracts and semantics are reported separately

Deterministic doubles prove application contracts. Live runs prove only what the recorded calls
actually returned. Screening assertions are lexical; semantic review is a human step with its own
label. Failed runs, rate limits and abandoned comparisons are kept.

**Tradeoff:** the results table looks unimpressive compared with a curated highlight reel, and the docs
are longer. The alternative is a showcase that cannot survive one follow-up question.

## React and a component system

React 19 + TypeScript + Vite, shadcn/Radix primitives, Motion, locally bundled fonts. Node is a build
dependency only; FastAPI remains the only runtime server.

**Tradeoff:** a frontend toolchain and a build stage in the image. In exchange the workspace can show
evidence, history and per-turn metrics without becoming a server-rendered form.

## Open questions I have not resolved

- **Semantic identity.** Similar names do not establish the same person, and the current system says so
  by refusing to merge. A principled entity registry with reviewable merges is unfinished work.
- **Paraphrase recall without embeddings.** The lexical fallback is honest but narrow; a small,
  locally-run embedding model with a proper backfill lifecycle is the obvious next experiment.
- **Corpus scale.** 540 synthetic records exercise mechanisms, not generalization. A real,
  independently authored collection with held-out questions is the only way to say anything about
  quality.
- **Multi-user authorisation.** Ownership checks and cross-user fixtures exist, but the shipped
  identity is a single local operator; a public deployment needs its own authentication pass.
- **Cost.** Provider billing is not connected, so cost per successful task is undefined rather than
  zero. That is the most obvious missing measurement.
