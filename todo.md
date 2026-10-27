# Status and open work

## Where the project stands

Working end to end on a local machine: import or type notes, selective learning, source-linked
memories, bounded retrieval, cited and labelled answering, correction, world change, Forget, Private,
and per-turn usage/timing inspection.

| Area | State |
| --- | --- |
| Backend contracts (369 tests, real PostgreSQL) | Passing |
| Browser journeys | 26 passed at the last complete run; the latest aggregate rerun stalled at one delayed Private-cancellation case after 18 journeys |
| Live extraction on the 540-record synthetic corpus | Partial: 365 succeeded, 78 failed, 97 pending when the provider rate-limited |
| Live 30-case showcase | Two runs retained (13 and 16 mechanical screens); semantic review still manual |
| Dense retrieval | Not implemented — no embeddings, no vector index, no claim |
| Cross-browser / mobile | Not tested; Chromium only |

## Next useful work, in order

1. **Finish the browser acceptance run.** Isolate the delayed *Private cancels pending learning* case,
   determine whether it is a product defect or a harness stall, then rerun the aggregate suite before
   describing the workspace as fully verified.
2. **Complete a corpus pass.** Resume the existing namespace rather than re-importing; keep the
   persisted allowance for demo prompts and record the stop reason if the provider refuses again.
3. **Label the semantic review.** Turn the pending manual review in the showcase reports into explicit
   per-case verdicts, including the known arithmetic and blocker-label defects.
4. **Decide the embedding question.** Either build a versioned embedding model with backfill,
   revocation-aware re-indexing and a frozen A/B against the lexical baseline — or keep the current
   lexical claim and stop revisiting it.
5. **Cost measurement.** Connect provider billing or record exact per-call prices, so cost per answered
   question stops being "unknown".
6. **Portfolio surface.** A short screen-capture of the seven-step walkthrough in the README would do
   more for a reader than another thousand words of documentation.

## Known gaps worth naming before anyone else finds them

- Assessment can succeed while extraction fails; the retry path is explicit, not automatic.
- Paraphrased questions with no lexical overlap can miss retrieval; the fallback is labelled partial.
- Forget is deliberately over-broad and does not catch unseen paraphrases of an excluded note.
- Only the migration and runtime logins exist; a public deployment needs its own authentication pass.
- The application has no background daemon: closing the browser can leave a pending learning job.
- `tokens` are provider-reported and `bytes` are serialised payloads; neither is disk or memory use.

## Housekeeping

- Keep documentation consolidated: [README.md](README.md), [ARCHITECTURE.md](ARCHITECTURE.md),
  [DECISIONS.md](DECISIONS.md), [EVALUATION.md](EVALUATION.md), [RUN.md](RUN.md) and this file.
  Do not add competing status lists.
- Add a migration rather than editing an applied one.
- Keep synthetic corpora and evaluation labels out of the memory corpus used for answering.
- Never commit `.env`, provider keys, databases, dependency directories or private imports.
