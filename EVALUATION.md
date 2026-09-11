# Minimal evaluation plan for Hey Jarvis

Prepared 11 September 2026. The product/model gates below remain proposed. S03–S05 now have 111 passing isolated bootstrap/evidence/policy/import checks, including real PostgreSQL races, instrumented Private failures and preserved state across container replacement; [RUN.md](RUN.md#actual-s05-results) and the [S05 evidence record](eval/reports/s05-infrastructure.json) record commands and limits. No live-model runs exist. Target: 12 September afternoon IST. Grounding: [DECISIONS.md](DECISIONS.md), [ARCHITECTURE.md](ARCHITECTURE.md), and the supplied early notes project brief.

## 1. Prove one complete journey first

S05 copied and hash-verified the [eight synthetic observations](data/synthetic/sample-dictations.jsonl) and [separate cases](eval/fixtures/sample-evaluation-cases.json): current date, historical change/reason, personalized draft, hypothetical owner, reported action, conflicting amounts, missing metadata and unknown surname. Tests import only the JSONL and mechanically validate all 11 labeled excerpts against saved sources. These are structural checks, not answers to the evaluation questions or semantic/model grades. S04's deterministic proposal fixture also remains separate from source input. Never ingest answer keys.

The project requires an ordinary-user interface connected to real persistence, retrieval, and model decisions. Frontend polish can wait; a tiny working surface cannot: import/status, Ask Jarvis, reply with Sources, Private, Correct, and Forget. Verify the same backend through both UI and evaluation; a prepared transcript or mock response does not satisfy the demonstration.

The user brought the minimal source-workspace UI forward after S05. Browser import, listing and inspection now complement developer checks; CLI commands are not required in the unfamiliar's workflow. Full Ask/controls remain later gates. `tests/browser/workspace.test.mjs` uses real Chromium and the isolated PostgreSQL-backed web service to test import/reimport, Unicode/exact pairs, malformed/conflicting/oversized files, 55-record pagination, unknown time, literal HTML-like source text, Private clearing, delayed responses, network failures and mobile keyboard/navigation behavior. Fresh test contexts instrument attempted browser-storage writes and reject external requests; no model double is presented as an answer. **Actual UI milestone evidence: 112 backend checks and 8 browser checks passed**, with application state preserved; [full results and limitations](eval/reports/ui-foundation.json).

## 2. Deterministic contract tests

These run without paid model calls. Inject controlled extraction proposals to exercise backend rules, including malicious or malformed proposals. They prove behavior under those inputs, not extraction quality.

| Fixture group | Required invariant |
| --- | --- |
| Attribution and source spans | Reject nonexistent source IDs/spans, wrong tenant, and invalid schema; generated replies cannot independently corroborate claims. Semantic support still needs model-live review. |
| Observation identity | Raw/formatted variants share one observation; exact reimport is idempotent; separately authored identical text remains distinguishable. |
| Time and uncertainty | Preserve tentative/conditional status and unknown dates; distinguish correction from world change; late import cannot automatically overwrite current state. |
| Learning eligibility | A question does not assert its answer; a one-request formatting instruction does not become a lasting preference. Keep useful conditional plans conditional, quote attribution intact, and zero-claim decisions distinguishable from failed extraction. Model selection of these outcomes also needs live grading. |
| Private | Instrument every personal-store read and durable-write sink. No personal-memory reads, durable private content/activity, backfill, or Normal context carryover; test success, exception, timeout, reload, and mode exit. |
| Forget | Excluded sources and known duplicates cannot feed recall, summaries, relearning, retries, or cached contexts; original history visibility is tested separately. |
| Tool boundaries | Imported instructions never execute; draft does not become sent; failed retrieval is not labeled absent evidence; retry cannot duplicate an external effect. |

For Private, compare database/browser-storage snapshots and inspect queue/log/cache/export paths with synthetic sentinels plus call instrumentation. Sentinel absence alone misses encoding or undiscovered sinks; inspect wiring too.

Use **two real database connections and explicit test barriers**, not timing sleeps: pause a worker after reading revision 7; commit Forget/correction at revision 8; resume the worker and require rejection or safe recomputation. Test the reverse order, stale cache reads, restart/retry, and revocation between retrieval and publication. A shared policy-row lock or equivalent atomic protocol must cover validation and commit. Exercise the selected database's actual isolation behavior. Already released bytes cannot be recalled.

## 3. Live models and nondeterminism

S07 adds deterministic processing/reconciliation, provider transport and browser memory checks; [actual results](RUN.md#s07-memory-processing) and the [contract evidence record](eval/reports/s07-contracts.json) remain separate from live quality. The test server uses an explicitly named fixture extractor only after checking the isolated PostgreSQL target. Its expected proposals never enter source ingestion. The production server has no fixture-extractor setting. Transport doubles cover failure/usage contracts without authenticating a provider.

The new `jarvis evaluate-extraction --repeats 3` command is a **live-only**, synthetic-only pilot behind the provider gate. It creates separate collections, retains all call/job outcomes and source-linked revisions, and returns `status: ungraded` / `semantic_review: pending`. Review each repeat against the obligations before changing those labels in an evaluator report. Eight successful processing jobs do not equal eight semantically correct cases. No live pilot has run for this implementation checkpoint; S07's live gate and S06/S08 answer comparisons remain incomplete.

First verify provider availability, documented credentials, retention/no-training settings, model identifiers, and a configured spend/token ceiling. NVIDIA trial terms currently conflict with the no-training requirement; the [proposed synthetic-only exception](DECISIONS.md#s06-readiness-decisions) is pending. Presence of an API key does not clear this gate. After explicit approval or compliant provider terms, run a minimal schema smoke call within that ceiling. If access or budget is unavailable, continue deterministic work, report live evaluation blocked, and never relabel mocked runs as model results.

Use the [documented model shortlist](ARCHITECTURE.md#models-and-repair): Kimi K3 is the selected S06 response candidate and must remain fixed during later proposer comparisons; Nemotron Lightning and Qwen3-8B are extraction candidates, with stronger-model extraction as a separately scoped reference. Ultra is optional and must not silently replace Kimi on failed calls. Probe JSON/schema behavior and record tool support rather than assuming either from a model card. Include Hindi/Hinglish or other expected input languages. If only one provider is available, report the missing comparison and run the complete supported baseline.

Run each original case three times from clean state. Reimport on repeated extraction runs; reuse a frozen index when measuring generation-only variability. Record sampling settings, model/prompt/schema versions and seeds where supported; temperature zero does not guarantee reproducibility.

Grade semantic obligations rather than exact wording: all required facts present, no prohibited assertion, proper uncertainty, task completed, and citations supporting each factual claim. Check exact source references mechanically; review entailment separately. An LLM judge can flag cases but cannot certify its own extractor. Blind the unfamiliar to variant names, randomize output order, and retain failures. Report successes out of attempts, not the best response of three.

## 4. Compare mechanisms without confounding

Keep the response model, query set, eligible corpus, evidence budget, and grading fixed.

1. **History baseline:** all eligible source history if measured tokens fit the model budget, including instructions and reply reserve. Otherwise report “does not fit”; do not silently truncate.
2. **Retrieval ablation:** lexical-only versus lexical+dense union on identical source chunks. This isolates retrieval.
3. **Representation ablation:** source passages alone versus sources plus derived claims in the selected retrieval setup. Keep the total evidence token budget fixed across both; do not give the combined variant an extra budget. Include a question about a source detail deliberately omitted from the selective claims, to test source fallback. A facts-only variant is optional diagnostic evidence, not a replacement for preserved sources.
4. **Extractor ablation:** small versus stronger extraction on identical inputs, downstream retrieval/settings fixed, isolated databases. Do not simultaneously change the answer model or prompts beyond required provider formatting.

Pilot these comparisons on the eight-record corpus plus a small varied challenge set. Carry only a baseline and the best justified candidate into the full run. Report any comparison skipped for time/cost; avoid claiming small-model superiority without that comparison.

The [research review](DECISIONS.md#input-to-memory-research-review) motivates these experiments without supplying application scores. Grade extraction selection separately from faithfulness: whether the input deserved a memory, whether all required qualifiers survived, and whether each claim is supported. Include eligible information missed by extraction and unnecessary memories created from questions/instructions. S06's source-history answer baseline remains necessary to assess downstream S07 benefit. External benchmarks with assistant-derived memories do not override this project's user-only learning rule.

## 5. Corpus, metrics, and proposed gates

S08 now has an executable isolated retrieval diagnostic: `docker compose -f compose.test.yaml run --rm tests python eval/retrieval.py`. It imports the eight originals, seven additional synthetic records and 485 templated distractors through the real service, constructs explicitly deterministic claims separately, and runs 17 authored questions three times per representation. Labels/proposals remain outside source ingestion. Both variants use the same frozen corpus/claims, five primary matches and a 24,000-byte evidence budget. Two questions with no required evidence are recorded but are not scored as successful semantic abstentions. Fifteen answerable cases have 20 required passages per repeat.

The initial RRF candidate lost a source needed to distinguish same-name people; its [report](eval/reports/s08-retrieval-initial.json) is retained. The revised method reserves the strongest original match and is rerun on the same cases. Report exact passage coverage and selected records separately from answer quality; UTF-8 byte budgets are not token measurements. Templated distractors and tuning questions do not close the planned blind approximately-500-record S11 evaluation. Optional dense retrieval, model-based answers and the S06 all-history answer comparison remain unrun.

Actual final S08 result: 186 backend and 12 browser tests pass. Both retrieval variants recover 60/60 required passages across 45/45 answerable attempts; source-only is the faster, smaller default. The two unanswerable cases are not semantic-abstention grades. [Final diagnostic](eval/reports/s08-retrieval-final.json), [contract/restart evidence and limitations](eval/reports/s08-contracts.json).

Prepare approximately 500 varied observations with raw/formatted pairs, including distributed facts, paraphrases, code-switching, distractors, revisions and ambiguity. Keep 16 tuning questions and at least 16 blind questions across distinct scenario families; these counts are proposed deadline compromises. Labels stay outside ingestion. Run the final two candidates on the same corpus; repeat blind questions three times. The unfamiliars' separate approximately 500 records remain unavailable—support their documented import, not a hardcoded Atlas schema.

Measure supported task success, unsupported claims, extraction precision/recall, evidence-set coverage, appropriate abstention, p50/p95 retrieval/end-to-end latency, tokens, index lag, database growth, and total cost per successful task. Total spend includes ingestion, repair, and failed attempts; success rate divides by all attempts. Report sample counts and cold/warm conditions. Tiny samples provide weak tail-latency and generalization evidence.

Proposed gates: all deterministic invariants pass; all eight core cases pass every live repeat; zero prohibited privacy/Forget behavior or unsupported high-impact writes; at least 90% blind task success, with no regression against the baseline. These are acceptance targets, not statistical guarantees. Abstaining on everything fails answerable tasks.

## 6. Deadline stop rule

Freeze optional mechanisms by 12 September 10:00 IST, a proposed buffer before afternoon delivery. Stop experiments at the spend ceiling or when the baseline already meets gates without measurable improvement. Prioritize invariant fixes and the complete review path over another framework.

Reserve final hours for a clean install/import/reset/evaluate/UI run using documented commands, migrations, results, `.env.example`, README, RUN.md, and the exact release commit. Preserve failures and limitations. Phase One must remain the user's independently authored, previously preserved work; this evaluation plan cannot substitute for it.
