import { useState } from "react";
import { ArrowRight, Database, GitBranch } from "lucide-react";
import { Button } from "./ui/button";
import { Heading } from "./common";
import type { Workspace } from "@/lib/use-workspace";

const stages = [
  [
    "Observe",
    "Give Jarvis a note",
    "Type, paste or import notes. Normal Ask assesses what is worth remembering and preserves useful personal or project assertions. Pure questions, greetings and temporary instructions stay in the current chat, with no source or learning job. Questions do not assert their answers; generated replies never become learned evidence.",
    "Conversation / Sources",
  ],
  [
    "Authorize",
    "Check mode and identity",
    "The backend owns identity and permissions. Normal allows saved operations. Private direct is a separate context-free route: no database reads, writes or jobs; when explicitly enabled, only the current question goes to the hosted provider.",
    "src/jarvis/policy.py; POST /private/ask",
  ],
  [
    "Validate",
    "Preserve observation identity",
    "Validate the complete bounded UTF-8 batch. Owner + collection + record ID identifies an observation. Exact retries are idempotent; changed originals reject the batch.",
    "src/jarvis/imports.py; services.py",
  ],
  [
    "Store",
    "Keep the original first",
    "One transaction saves the Source and pending Job. Raw/formatted variants remain one observation. Preserve metadata, actual import time and unknown capture times.",
    "PostgreSQL: sources, jobs",
  ],
  [
    "Request",
    "Learn as you talk",
    "Normal Ask learns from its saved message before answering, with a visible receipt for new facts, repeats, ambiguity or failures. Imports still use Process sources. Leaving Normal stops browser follow-up requests; accepted Normal work may finish.",
    "POST /conversation/messages; POST /conversation/messages/{id}/learn",
  ],
  [
    "Lease",
    "Build permitted context",
    "An owner-serialized lease captures source, policy and revision state. Relevant active memories are selected within bounded context; every original remains stored. Oversized provider packets fail visibly.",
    "src/jarvis/processing.py: lease_next, _packet",
  ],
  [
    "Propose",
    "Call a bounded model",
    "Reserve the shared persisted allowance before inference. The model proposes typed operations and exact excerpts, not database commands. Retries and unknown usage count. No automatic provider fallback.",
    "src/jarvis/providers.py; extraction.py",
  ],
  [
    "Check",
    "Validate structure and evidence",
    "Resolve unique exact excerpts into source offsets. Check ownership, qualifiers, exclusions and packet membership. This validates references and structure, not the truth of an interpretation.",
    "src/jarvis/contracts.py; processing.py",
  ],
  [
    "Reconcile",
    "Connect, do not overwrite",
    "Validate add, support, supersede, correct or conflict against matching targets and scope. no_memory, duplicate and needs_clarification remain separate decisions, never aliases for provider failure.",
    "Claim revisions and relationships",
  ],
  [
    "Commit",
    "Recheck before saving",
    "Under the same policy guard used by controls, recheck evidence, lease and revisions. Atomically commit claims, support, relationships, receipt and successful job. Accounting survives failures separately.",
    "PostgreSQL guarded transaction",
  ],
  [
    "Protect",
    "Respect changes and Forget",
    "Correct fixes an interpretation; world change records a later state. Forget blocks future use and relearning from excluded passages and known duplicates. Retained original history is not physical erasure.",
    "src/jarvis/controls.py; lifecycle guards",
  ],
  [
    "Inspect",
    "Read the complete memory",
    "A memory is a qualified claim plus exact owned evidence, revision history and lifecycle, not just a sentence or vector. Inspect its original passages and recorded decisions in Memory and the trace below.",
    "Memory / Sources / collection trace",
  ],
];
const tables = [
  [
    "sources",
    "Original raw/formatted strings, source identity, metadata, import time and revisions.",
  ],
  [
    "jobs",
    "Requested work, attempts, lease, outcome and fixed failure category.",
  ],
  [
    "claim_revisions",
    "Subject, property, value/unit, scope, attribution, uncertainty, negation, condition, known/unknown time and lifecycle.",
  ],
  [
    "passages + claim_evidence",
    "Exact source variant and character interval linked to a claim. One observation is not two confirmations.",
  ],
  [
    "relationships + receipts",
    "Validated history transitions and idempotent processing outcomes. See migrations for exact relation names.",
  ],
  [
    "policy / exclusions",
    "Owner guard, policy revision and excluded supporting evidence used by worker, retrieval and controls.",
  ],
  [
    "model_calls + model_budgets",
    "Shared reservations, actual returned model, known tokens, timings, status and failures. No provider keys or raw private prompts.",
  ],
];

export function Workflow({ workspace: w }: { workspace: Workspace }) {
  const [selected, setSelected] = useState(0);
  const [trace, setTrace] = useState<unknown>();
  const [report, setReport] = useState<unknown>();
  const [reportName, setReportName] = useState("");
  const item = stages[selected];
  async function loadReport(id: string, name: string) {
    const result = await w.run("Reading curated synthetic evidence", () =>
      w.session.request<unknown>(`/evaluation/reports/${id}`),
    );
    if (result) {
      setReport(result);
      setReportName(name);
    }
  }
  return (
    <div className="workflow-page">
      <Heading
        eyebrow="The project, made inspectable"
        title="From a small clue to a supported answer."
      >
        Follow the same 12-stage flow as the project guide, updated for the
        running application. Select a stage to understand what happens and where
        to inspect it.
      </Heading>
      <div className="workflow-legend">
        <span>Local browser + API + PostgreSQL</span>
        <span>External inference only with explicit consent</span>
      </div>
      <section
        className="flow-atlas"
        aria-label="Input to semantic memory flowchart"
      >
        <ol className="flow-nodes">
          {stages.map(([label, title], index) => (
            <li key={label}>
              <button
                aria-pressed={selected === index}
                onClick={() => setSelected(index)}
              >
                <span className="flow-number">
                  {String(index + 1).padStart(2, "0")}
                </span>
                <strong>{label}</strong>
                <small>{title}</small>
                <ArrowRight aria-hidden="true" />
              </button>
            </li>
          ))}
        </ol>
        <article className="flow-detail" aria-live="polite">
          <span className="eyebrow">
            Stage {selected + 1} / {item[0]}
          </span>
          <h2>{item[1]}</h2>
          <p>{item[2]}</p>
          <code>{item[3]}</code>
        </article>
      </section>
      <section className="panel retrieval-flow">
        <span className="eyebrow">The second half</span>
        <h2>Memory to answer, without inventing certainty.</h2>
        <p className="flow-sentence">
          Saved user message <ArrowRight /> selective learning <ArrowRight />{" "}
          original evidence + learned memories <ArrowRight /> bounded response
          proposal <ArrowRight /> citation validation + revocation recheck{" "}
          <ArrowRight /> answer, citations and measured calls.
        </p>
        <p>
          Current instructions override remembered preferences. Unknown
          evidence, ambiguity and operational failure are different outcomes.
          The current retrieval implementation is PostgreSQL lexical search plus
          structured memories; dense embeddings and tool execution are not
          enabled.
        </p>
      </section>
      <section className="panel">
        <div className="section-title">
          <h2>
            <Database /> What is actually stored?
          </h2>
          <span className="meta">Local PostgreSQL volume</span>
        </div>
        <div className="storage-map">
          {tables.map(([name, description]) => (
            <article key={name}>
              <code>{name}</code>
              <p>{description}</p>
            </article>
          ))}
        </div>
        <p className="meta">
          Machine-readable documentation: docs/storage-contract.json. Exact
          schema: src/jarvis/models.py and migrations/. No second database or
          graph service is required.
        </p>
      </section>
      <section className="panel">
        <div className="section-title">
          <h2>
            <GitBranch /> Inspect this collection's learning
          </h2>
          <Button
            variant="outline"
            disabled={!!w.busy || !w.sources}
            onClick={() =>
              void w.run("Reading synthetic collection trace", async () =>
                setTrace(
                  await w.session.request<unknown>(
                    `/processing/report?namespace=${encodeURIComponent(w.namespace)}`,
                  ),
                ),
              )
            }
          >
            Load collection trace
          </Button>
        </div>
        <p>
          Open a collection first. This existing synthetic-only report shows
          processing counts, model calls and active-memory revision histories.
          Use Sources to inspect every original and failed/pending job.
          Unfamiliar-input records remain inspectable through Sources and
          Memory, not this synthetic export.
        </p>
        <p className="meta">
          Recorded operations are shown, not invented hidden reasoning.
          Questions and labels are never imported as memory.
        </p>
        {trace !== undefined && (
          <details open>
            <summary>Collection trace JSON</summary>
            <pre className="evidence-json">
              {JSON.stringify(trace, null, 2)}
            </pre>
          </details>
        )}
      </section>
      <section className="panel">
        <h2>Evaluation evidence, not a demo claim</h2>
        <p>
          The 540-record fictional corpus has 30 preselected showcase cases, 30
          held-out cases and 24 development cases. Passing an automated
          anchor/citation screen does not prove semantic accuracy. Read actual
          answers and failure counts.
        </p>
        <div className="report-actions">
          {[
            ["lightning", "Lightning smoke"],
            ["comparison", "Provider comparison"],
            ["showcase_baseline", "30-case baseline"],
            ["showcase", "30-case retest"],
            ["readiness", "Readiness check"],
          ].map(([id, name]) => (
            <Button
              key={id}
              variant="outline"
              disabled={!!w.busy}
              onClick={() => void loadReport(id, name)}
            >
              {name}
            </Button>
          ))}
        </div>
        {report !== undefined && (
          <details open>
            <summary>{reportName}: recorded JSON</summary>
            <pre className="evidence-json">
              {JSON.stringify(report, null, 2)}
            </pre>
          </details>
        )}
        <p className="meta">
          A missing report is displayed as not recorded. No simulated result is
          substituted. todo.md remains the single current project tracker.
        </p>
      </section>
      <section className="walkthrough-note">
        <span className="eyebrow">Explain it in plain language</span>
        <p>
          "We preserve the observation first. A model proposes qualified,
          source-linked memories; code validates and commits them behind
          lifecycle guards. Retrieval brings permitted evidence into a separate
          answer request. We measure calls and failures, and distinguish working
          infrastructure from semantic quality."
        </p>
      </section>
    </div>
  );
}
