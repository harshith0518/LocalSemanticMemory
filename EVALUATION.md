# Minimal evaluation plan for Hey Jarvis

Prepared 11 September 2026. The product/model gates below remain proposed. S03–S05 now have 111 passing isolated bootstrap/evidence/policy/import checks, including real PostgreSQL races, instrumented Private failures and preserved state across container replacement; [RUN.md](RUN.md#actual-s05-results) and the [S05 evidence record](eval/reports/s05-infrastructure.json) record commands and limits. No live-model runs exist. Target: 12 September afternoon IST. Grounding: [DECISIONS.md](DECISIONS.md), [ARCHITECTURE.md](ARCHITECTURE.md), and the supplied early notes project brief.

## 1. Prove one complete journey first

S05 copied and hash-verified the [eight synthetic observations](data/synthetic/sample-dictations.jsonl) and [separate cases](eval/fixtures/sample-evaluation-cases.json): current date, historical change/reason, personalized draft, hypothetical owner, reported action, conflicting amounts, missing metadata and unknown surname. Tests import only the JSONL and mechanically validate all 11 labeled excerpts against saved sources. These are structural checks, not answers to the evaluation questions or semantic/model grades. S04's deterministic proposal fixture also remains separate from source input. Never ingest answer keys.

The project requires an ordinary-user interface connected to real persistence, retrieval, and model decisions. Frontend polish can wait; a tiny working surface cannot: import/status, Ask Jarvis, reply with Sources, Private, Correct, and Forget. Verify the same backend through both UI and evaluation; a prepared transcript or mock response does not satisfy the demonstration.

## 2. Deterministic contract tests

These run without paid model calls. Inject controlled extraction proposals to exercise backend rules, including malicious or malformed proposals. They prove behavior under those inputs, not extraction quality.

| Fixture group | Required invariant |
| --- | --- |
| Attribution and source spans | Reject nonexistent source IDs/spans, wrong tenant, and invalid schema; generated replies cannot independently corroborate claims. Semantic support still needs model-live review. |
| Observation identity | Raw/formatted variants share one observation; exact reimport is idempotent; separately authored identical text remains distinguishable. |
| Time and uncertainty | Preserve tentative/conditional status and unknown dates; distinguish correction from world change; late import cannot automatically overwrite current state. |
| Private | Instrument every personal-store read and durable-write sink. No personal-memory reads, durable private content/activity, backfill, or Normal context carryover; test success, exception, timeout, reload, and mode exit. |
| Forget | Excluded sources and known duplicates cannot feed recall, summaries, relearning, retries, or cached contexts; original history visibility is tested separately. |
| Tool boundaries | Imported instructions never execute; draft does not become sent; failed retrieval is not labeled absent evidence; retry cannot duplicate an external effect. |

For Private, compare database/browser-storage snapshots and inspect queue/log/cache/export paths with synthetic sentinels plus call instrumentation. Sentinel absence alone misses encoding or undiscovered sinks; inspect wiring too.

Use **two real database connections and explicit test barriers**, not timing sleeps: pause a worker after reading revision 7; commit Forget/correction at revision 8; resume the worker and require rejection or safe recomputation. Test the reverse order, stale cache reads, restart/retry, and revocation between retrieval and publication. A shared policy-row lock or equivalent atomic protocol must cover validation and commit. Exercise the selected database's actual isolation behavior. Already released bytes cannot be recalled.

## 3. Live models and nondeterminism

First verify provider availability, documented credentials, retention/no-training settings, model identifiers, and a configured spend/token ceiling. Run a minimal schema smoke call within that ceiling. If access or budget is unavailable, continue deterministic work, report live evaluation blocked, and never relabel mocked runs as model results.

Use the [documented model shortlist](ARCHITECTURE.md#models-and-repair): DeepSeek remains the fixed response model while comparing Nemotron Lightning and Qwen3-8B as proposers; use DeepSeek extraction as a stronger reference on the diagnostic subset. Probe JSON/schema behavior and record tool support rather than assuming either from a model card. Include Hindi/Hinglish or other expected input languages. If only one provider is available, report the missing comparison and run the complete supported baseline.

Run each original case three times from clean state. Reimport on repeated extraction runs; reuse a frozen index when measuring generation-only variability. Record sampling settings, model/prompt/schema versions and seeds where supported; temperature zero does not guarantee reproducibility.

Grade semantic obligations rather than exact wording: all required facts present, no prohibited assertion, proper uncertainty, task completed, and citations supporting each factual claim. Check exact source references mechanically; review entailment separately. An LLM judge can flag cases but cannot certify its own extractor. Blind the unfamiliar to variant names, randomize output order, and retain failures. Report successes out of attempts, not the best response of three.

## 4. Compare mechanisms without confounding

Keep the response model, query set, eligible corpus, evidence budget, and grading fixed.

1. **History baseline:** all eligible source history if measured tokens fit the model budget, including instructions and reply reserve. Otherwise report “does not fit”; do not silently truncate.
2. **Retrieval ablation:** lexical-only versus lexical+dense union on identical source chunks. This isolates retrieval.
3. **Representation ablation:** add derived claims to the selected retrieval setup. This tests whether memory improves over history search.
4. **Extractor ablation:** small versus stronger extraction on identical inputs, downstream retrieval/settings fixed, isolated databases. Do not simultaneously change the answer model or prompts beyond required provider formatting.

Pilot these comparisons on the eight-record corpus plus a small varied challenge set. Carry only a baseline and the best justified candidate into the full run. Report any comparison skipped for time/cost; avoid claiming small-model superiority without that comparison.

## 5. Corpus, metrics, and proposed gates

Prepare approximately 500 varied observations with raw/formatted pairs, including distributed facts, paraphrases, code-switching, distractors, revisions and ambiguity. Keep 16 tuning questions and at least 16 blind questions across distinct scenario families; these counts are proposed deadline compromises. Labels stay outside ingestion. Run the final two candidates on the same corpus; repeat blind questions three times. The unfamiliars' separate approximately 500 records remain unavailable—support their documented import, not a hardcoded Atlas schema.

Measure supported task success, unsupported claims, extraction precision/recall, evidence-set coverage, appropriate abstention, p50/p95 retrieval/end-to-end latency, tokens, index lag, database growth, and total cost per successful task. Total spend includes ingestion, repair, and failed attempts; success rate divides by all attempts. Report sample counts and cold/warm conditions. Tiny samples provide weak tail-latency and generalization evidence.

Proposed gates: all deterministic invariants pass; all eight core cases pass every live repeat; zero prohibited privacy/Forget behavior or unsupported high-impact writes; at least 90% blind task success, with no regression against the baseline. These are acceptance targets, not statistical guarantees. Abstaining on everything fails answerable tasks.

## 6. Deadline stop rule

Freeze optional mechanisms by 12 September 10:00 IST, a proposed buffer before afternoon delivery. Stop experiments at the spend ceiling or when the baseline already meets gates without measurable improvement. Prioritize invariant fixes and the complete review path over another framework.

Reserve final hours for a clean install/import/reset/evaluate/UI run using documented commands, migrations, results, `.env.example`, README, RUN.md, and the exact release commit. Preserve failures and limitations. Phase One must remain the user's independently authored, previously preserved work; this evaluation plan cannot substitute for it.
