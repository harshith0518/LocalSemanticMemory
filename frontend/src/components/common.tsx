import type { ReactNode } from "react";
import { ArrowUpRight, FileText, LoaderCircle } from "lucide-react";
import { Button } from "./ui/button";
import { Badge } from "./ui/badge";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "./ui/dialog";
import type { Claim, Inspection } from "@/lib/types";

export function Sprout({ className = "" }: { className?: string }) {
  return (
    <svg
      className={className}
      viewBox="0 0 64 64"
      fill="none"
      aria-hidden="true"
    >
      <path
        d="M31 54V30M31 37C9 38 8 13 8 13s24-1 24 22M32 29C32 8 56 9 56 9s1 23-24 25"
        stroke="currentColor"
        strokeWidth="3"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}
export function Activity({ label }: { label: string }) {
  return (
    <div className="activity" role="status">
      <span className="activity-orbit">
        <LoaderCircle aria-hidden="true" />
      </span>
      <span>
        {label}
        <small>Waiting for the backend · results appear after validation</small>
      </span>
      <span className="activity-dots" aria-hidden="true">
        <i />
        <i />
        <i />
      </span>
    </div>
  );
}
export function Empty({
  icon,
  title,
  children,
}: {
  icon: ReactNode;
  title: string;
  children: ReactNode;
}) {
  return (
    <div className="empty-state">
      <div className="empty-icon">{icon}</div>
      <h3>{title}</h3>
      <p>{children}</p>
    </div>
  );
}
export function Heading({
  eyebrow,
  title,
  children,
  action,
}: {
  eyebrow: string;
  title: string;
  children: ReactNode;
  action?: ReactNode;
}) {
  return (
    <header className="page-heading">
      <div>
        <span className="eyebrow">{eyebrow}</span>
        <h1>{title}</h1>
        <p>{children}</p>
      </div>
      {action}
    </header>
  );
}
export const memoryLabel = (claim: Pick<Claim, "content">) => {
  const c = claim.content;
  return `${c.subject.label} · ${c.negated ? "Not: " : ""}${c.predicate.replaceAll("_", " ")}: ${c.value.value}${c.value.unit ? ` ${c.value.unit}` : ""}`;
};
export function Qualifiers({ claim }: { claim: Claim }) {
  const c = claim.content;
  return (
    <>
      <div className="tags">
        <Badge variant="secondary">{c.evidence_status}</Badge>
        <Badge variant="outline">{c.scope.key ?? c.scope.kind}</Badge>
        <Badge variant="outline">{c.modality}</Badge>
        {c.negated && <Badge variant="outline">Negated</Badge>}
      </div>
      {c.condition && <p className="condition">Only if: {c.condition}</p>}
      <p className="meta">Attributed to: {c.attribution.label}</p>
      <p className="meta">
        Event: {c.time.event?.value ?? "Unknown"} · Applies from:{" "}
        {c.time.valid_from?.value ?? "Unknown"} · Until:{" "}
        {c.time.valid_to?.value ?? "Unknown"}
      </p>
    </>
  );
}
export function SourceDialog({
  inspection,
  close,
}: {
  inspection?: Inspection;
  close: () => void;
}) {
  const s = inspection?.observation;
  return (
    <Dialog
      open={!!s}
      onOpenChange={(open) => {
        if (!open) close();
      }}
    >
      <DialogContent className="evidence-dialog">
        <DialogHeader>
          <DialogTitle>
            <FileText aria-hidden="true" /> Original source
          </DialogTitle>
          <DialogDescription>
            Original and formatted text belong to the same observation.
          </DialogDescription>
        </DialogHeader>
        {s && (
          <div id="evidence">
            <div className="tags">
              <Badge variant="secondary">
                {s.source_key.split(":").at(-1)}
              </Badge>
              <Badge variant="outline">Revision {s.revision}</Badge>
              <Badge variant="outline">
                {inspection?.job?.status ?? "No job"}
              </Badge>
            </div>
            <h3>Original transcript</h3>
            <p className="passage" id="raw-text">
              {s.raw_text}
            </p>
            <h3>Formatted text</h3>
            <p className="passage" id="formatted-text">
              {s.formatted_text ?? "No formatted variant provided."}
            </p>
            <dl className="metadata">
              <dt>Captured</dt>
              <dd id="captured-at">{s.captured_at ?? "Not provided"}</dd>
              <dt>Imported</dt>
              <dd>{s.imported_at}</dd>
              <dt>Source ID</dt>
              <dd>{s.id}</dd>
              <dt>Job attempts</dt>
              <dd>{inspection?.job?.attempts ?? "Not available"}</dd>
            </dl>
            <details>
              <summary>Capture metadata</summary>
              <pre>
                {s.capture_metadata === null
                  ? "No capture metadata was provided."
                  : JSON.stringify(s.capture_metadata, null, 2)}
              </pre>
            </details>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
export function OriginalButton({
  onClick,
  children = "Inspect original",
  disabled,
}: {
  onClick: () => void;
  children?: ReactNode;
  disabled?: boolean;
}) {
  return (
    <Button
      type="button"
      variant="ghost"
      size="sm"
      onClick={onClick}
      disabled={disabled}
    >
      {children}
      <ArrowUpRight />
    </Button>
  );
}
