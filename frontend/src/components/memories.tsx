import { useEffect, useRef, useState } from "react";
import {
  Brain,
  GitBranch,
  History as HistoryIcon,
  RefreshCw,
  Sparkles,
} from "lucide-react";
import { Button } from "./ui/button";
import { Input } from "./ui/input";
import { Textarea } from "./ui/textarea";
import { Badge } from "./ui/badge";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "./ui/dialog";
import {
  Empty,
  Heading,
  memoryLabel,
  OriginalButton,
  Qualifiers,
} from "./common";
import type {
  Claim,
  ClaimContent,
  ControlAction,
  ControlCommand,
  ControlPreview,
  TimeValue,
} from "@/lib/types";
import type { Workspace } from "@/lib/use-workspace";

const actionNames = {
  correct: "Correct",
  world_change: "Record a world change",
  forget: "Forget",
};
function Field({
  label,
  name,
  value,
  options,
}: {
  label: string;
  name: string;
  value: string | null | undefined;
  options?: string[];
}) {
  return (
    <label>
      {label}
      {options ? (
        <select name={name} defaultValue={value ?? ""}>
          {options.map((option) => (
            <option key={option} value={option}>
              {option.replaceAll("_", " ")}
            </option>
          ))}
        </select>
      ) : (
        <Input name={name} defaultValue={value ?? ""} />
      )}
    </label>
  );
}
function Control({
  w,
  claim,
  action,
  close,
}: {
  w: Workspace;
  claim: Claim;
  action: ControlAction;
  close: () => void;
}) {
  const [id] = useState(() => crypto.randomUUID());
  const [preview, setPreview] = useState<ControlPreview>();
  const [command, setCommand] = useState<ControlCommand>();
  const c = claim.content;
  async function review(form: HTMLFormElement) {
    if (!w.sources) return;
    const payload: ControlCommand = {
      operation_id: id,
      namespace: w.namespace,
      target_revision_id: claim.id,
      expected_policy_revision: w.sources.policy_revision,
      action,
    };
    if (action !== "forget") {
      const f = Object.fromEntries(new FormData(form)) as Record<
        string,
        string
      >;
      if (f.kind === "boolean" && !["true", "false"].includes(f.value)) {
        w.setNotice({
          text: "A yes/no value must be true or false.",
          error: true,
        });
        return;
      }
      const time = (key: string): TimeValue =>
        f[key]
          ? {
              precision: f[key].includes("T") ? "instant" : "date",
              value: f[key],
            }
          : null;
      payload.statement = f.statement;
      payload.replacement = {
        subject: { label: f.subject, entity_id: null },
        predicate: f.predicate,
        value: {
          kind: f.kind,
          value: f.kind === "boolean" ? f.value === "true" : f.value,
          ...(f.kind === "quantity" ? { unit: f.unit || null } : {}),
        },
        scope: {
          kind: f.scope_kind,
          key: ["project", "task"].includes(f.scope_kind) ? f.scope_key : null,
        },
        attribution: { label: f.attribution, entity_id: null },
        evidence_status: f.evidence_status,
        modality: f.modality,
        negated: f.negated === "true",
        condition: f.condition || null,
        time: {
          event: time("event"),
          valid_from: time("valid_from"),
          valid_to: time("valid_to"),
        },
      } as ClaimContent;
    }
    const result = await w.preview(payload);
    if (result) {
      setPreview(result);
      setCommand({ ...payload, preview_token: result.preview_token });
    }
  }
  return (
    <Dialog
      open
      onOpenChange={(open) => {
        if (!open && !w.busy) close();
      }}
    >
      <DialogContent
        className="control-dialog"
        onEscapeKeyDown={(event) => {
          if (w.busy) event.preventDefault();
        }}
        onPointerDownOutside={(event) => {
          if (w.busy) event.preventDefault();
        }}
      >
        <DialogHeader>
          <DialogTitle>{actionNames[action]} memory</DialogTitle>
          <DialogDescription>
            {action === "forget"
              ? "Blocks future use and relearning from the supporting notes and known copies across your collections. Original history remains inspectable; this is not physical erasure."
              : action === "correct"
                ? "Fix an interpretation that was wrong. This does not describe a change in the world."
                : "Record what changed in the world. The earlier state remains historical."}
          </DialogDescription>
        </DialogHeader>
        <p className="control-target">{memoryLabel(claim)}</p>
        <form
          id="control-form"
          onSubmit={(e) => {
            e.preventDefault();
            void review(e.currentTarget);
          }}
          onChange={() => {
            setPreview(undefined);
            setCommand(undefined);
          }}
          autoComplete="off"
        >
          <fieldset disabled={!!w.busy}>
            {action !== "forget" && (
              <>
                <label>
                  Your exact statement
                  <Textarea name="statement" required maxLength={65536} />
                </label>
                <label>
                  New value
                  <Input
                    name="value"
                    defaultValue={String(c.value.value)}
                    required
                  />
                </label>
                <details open>
                  <summary>Review meaning and qualifiers</summary>
                  <div className="form-grid">
                    <Field
                      label="Who or what"
                      name="subject"
                      value={c.subject.label}
                    />
                    <Field
                      label="Property"
                      name="predicate"
                      value={c.predicate}
                    />
                    <Field
                      label="Value type"
                      name="kind"
                      value={c.value.kind}
                      options={["text", "date", "quantity", "boolean"]}
                    />
                    <Field
                      label="Units, if any"
                      name="unit"
                      value={c.value.unit}
                    />
                    <Field
                      label="Applies to"
                      name="scope_kind"
                      value={c.scope.kind}
                      options={["unspecified", "global", "project", "task"]}
                    />
                    <Field
                      label="Project or task name"
                      name="scope_key"
                      value={c.scope.key}
                    />
                    <Field
                      label="Reported by"
                      name="attribution"
                      value={c.attribution.label}
                    />
                    <Field
                      label="Evidence"
                      name="evidence_status"
                      value={c.evidence_status}
                      options={["reported", "tentative", "disputed"]}
                    />
                    <Field
                      label="Meaning"
                      name="modality"
                      value={c.modality}
                      options={[
                        "asserted",
                        "conditional",
                        "hypothetical",
                        "question",
                        "quoted",
                      ]}
                    />
                    <Field
                      label="Is this negated?"
                      name="negated"
                      value={String(c.negated)}
                      options={["false", "true"]}
                    />
                    <Field
                      label="Condition, if any"
                      name="condition"
                      value={c.condition}
                    />
                    <Field
                      label="Event date/time (blank = unknown)"
                      name="event"
                      value={c.time.event?.value}
                    />
                    <Field
                      label="Applies from (blank = unknown)"
                      name="valid_from"
                      value={c.time.valid_from?.value}
                    />
                    <Field
                      label="Applies until (blank = unknown)"
                      name="valid_to"
                      value={c.time.valid_to?.value}
                    />
                  </div>
                </details>
              </>
            )}
            <Button type="submit" variant="outline">
              Review impact
            </Button>
          </fieldset>
        </form>
        {preview && command && (
          <section className="control-preview" id="control-preview">
            <h3>Review this exact change</h3>
            {preview.replacement && (
              <>
                <p>{memoryLabel({ content: preview.replacement })}</p>
                <p className="passage">{preview.statement}</p>
              </>
            )}
            <p>
              {preview.sources.length} supporting note(s) ·{" "}
              {preview.affected_revision_ids.length} linked revision(s).
            </p>
            <details>
              <summary>Review affected notes</summary>
              {preview.sources.map((source) => (
                <div key={source.id}>
                  <h4>{source.source_key.split(":").at(-1)}</h4>
                  <p className="passage">{source.raw_text}</p>
                </div>
              ))}
            </details>
            <Button
              variant={action === "forget" ? "destructive" : "default"}
              disabled={!!w.busy}
              onClick={() =>
                void w.apply(command).then((result) => {
                  if (result) close();
                })
              }
            >
              Confirm {action === "forget" ? "Forget" : "change"}
            </Button>
          </section>
        )}
        {w.notice.error && (
          <p className="error-card" role="alert">
            {w.notice.text}
          </p>
        )}
        <Button variant="ghost" disabled={!!w.busy} onClick={close}>
          Cancel
        </Button>
      </DialogContent>
    </Dialog>
  );
}

export function Memories({ workspace: w }: { workspace: Workspace }) {
  const historyPanel = useRef<HTMLElement>(null);
  useEffect(() => {
    const panel = historyPanel.current;
    if (w.history && panel?.getClientRects().length) {
      panel.focus({ preventScroll: true });
      panel.scrollIntoView({ block: "start" });
    }
  }, [w.history]);
  const [editing, setEditing] = useState<{
    claim: Claim;
    action: ControlAction;
  }>();
  return (
    <>
      <Heading
        eyebrow="02 / Connect the evidence"
        title="Context with a paper trail."
        action={
          <Button
            variant="outline"
            disabled={!!w.busy}
            onClick={() => void w.open()}
          >
            <RefreshCw />
            Refresh memories
          </Button>
        }
      >
        Selective, source-linked memories. Keep the nuance. Follow the history.
        Change your mind.
      </Heading>
      <section className="panel processing-panel">
        <div>
          <div className="section-title">
            <h2>From words to useful context</h2>
            <Badge variant="secondary">You choose when</Badge>
          </div>
          <p>Saving a source does not make every sentence a lasting fact.</p>
          <div id="processing-state" className="meta" role="status">
            {w.processing ? (
              <>
                <p>
                  {Object.entries(w.processing.counts)
                    .map(([name, n]) => `${n} ${name}`)
                    .join(" · ") || "No sources"}
                </p>
                <p>
                  Outcomes:{" "}
                  {Object.entries(w.processing.decisions)
                    .filter(([, n]) => n > 0)
                    .map(([name, n]) => `${n} ${name.replaceAll("_", " ")}`)
                    .join(" · ") || "none yet"}
                </p>
                <p>
                  {w.processing.provider_enabled
                    ? "Processing is enabled; select Refresh to check progress."
                    : "Live processing is disabled."}
                </p>
                {w.processing.failures.length > 0 && (
                  <p>
                    Some jobs did not complete learning, including cancelled
                    work. Inspect source status before choosing a retry.
                  </p>
                )}
              </>
            ) : (
              "Open the collection to inspect processing."
            )}
          </div>
        </div>
        <div className="button-stack">
          <Button
            disabled={!!w.busy || !w.sources}
            onClick={() => void w.process()}
          >
            <Sparkles />
            Process sources
          </Button>
          <Button
            variant="ghost"
            disabled={!!w.busy || !w.sources}
            onClick={() => void w.process(true)}
          >
            Retry failed processing
          </Button>
        </div>
      </section>
      <div className="memory-layout">
        <section>
          <div className="section-title">
            <h2>Learned memories</h2>
            <Badge variant="outline">
              {w.memories?.memories.length ?? "—"} in this view
            </Badge>
          </div>
          {!w.memories?.memories.length ? (
            <Empty icon={<Brain />} title="Understanding takes evidence">
              Process eligible sources, then refresh. An empty view is not
              evidence that every source has been understood.
            </Empty>
          ) : (
            <ul className="memory-list" id="memory-list">
              {w.memories.memories.map((claim) => (
                <li key={claim.id}>
                  <button
                    className="memory-title"
                    disabled={!!w.busy}
                    onClick={() => void w.showHistory(claim.claim_id)}
                  >
                    <span>{memoryLabel(claim)}</span>
                    <HistoryIcon />
                  </button>
                  <Qualifiers claim={claim} />
                  <span className="meta">
                    {claim.lifecycle} · revision {claim.revision} ·{" "}
                    {claim.passages.length} supporting passage(s)
                  </span>
                </li>
              ))}
            </ul>
          )}
          {w.memories?.next_after && (
            <Button
              disabled={!!w.busy}
              variant="outline"
              onClick={() =>
                void w.run("Loading more memories", () =>
                  w.loadMemories(w.memories?.next_after ?? undefined),
                )
              }
            >
              More memories
            </Button>
          )}
        </section>
        <aside className="memory-story">
          <GitBranch />
          <h3>Nothing has to become a permanent assumption.</h3>
          <p>
            Correct an interpretation. Record a real change. Or forget the
            evidence for future use.
          </p>
          <span>03 / Stay in control</span>
        </aside>
      </div>
      {w.history && (
        <section
          ref={historyPanel}
          tabIndex={-1}
          aria-labelledby="memory-history-title"
          className="panel memory-history"
          id="memory-history"
        >
          <div className="section-title">
            <h2 id="memory-history-title">Memory history</h2>
            <Button variant="ghost" onClick={() => w.setHistory(undefined)}>
              Close history
            </Button>
          </div>
          {w.history.revisions.map((claim) => (
            <article key={claim.id}>
              <span className="eyebrow">
                Revision {claim.revision} · {claim.lifecycle}
              </span>
              <h3>{memoryLabel(claim)}</h3>
              <Qualifiers claim={claim} />
              {claim.passages.map((passage, index) => (
                <details key={`${passage.source_id}-${index}`}>
                  <summary>
                    Supporting passage · {passage.variant} · source revision{" "}
                    {passage.source_revision}
                  </summary>
                  <blockquote>{passage.exact_text}</blockquote>
                  <p className="meta">
                    Source {passage.source_id} · characters [{passage.start},{" "}
                    {passage.end})
                  </p>
                  <OriginalButton
                    disabled={!!w.busy}
                    onClick={() => void w.inspect(passage.source_id)}
                  >
                    View original source
                  </OriginalButton>
                </details>
              ))}
              {claim.lifecycle === "active" && (
                <div className="control-actions">
                  {(["correct", "world_change", "forget"] as const).map(
                    (action) => (
                      <Button
                        key={action}
                        disabled={!!w.busy}
                        variant="outline"
                        onClick={() => setEditing({ claim, action })}
                      >
                        {actionNames[action]}
                      </Button>
                    ),
                  )}
                </div>
              )}
            </article>
          ))}
          {w.history.relations.length > 0 && (
            <details>
              <summary>Revision relationships</summary>
              {w.history.relations.map((relation, index) => (
                <p className="meta" key={index}>
                  {relation.kind.replaceAll("_", " ")} ·{" "}
                  {relation.from_revision_id} → {relation.to_revision_id}
                </p>
              ))}
            </details>
          )}
        </section>
      )}
      {editing && (
        <Control
          key={`${editing.claim.id}-${editing.action}`}
          w={w}
          {...editing}
          close={() => setEditing(undefined)}
        />
      )}
    </>
  );
}
