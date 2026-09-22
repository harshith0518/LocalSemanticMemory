import { Activity as ActivityIcon, Database, RefreshCw } from "lucide-react";
import { Button } from "./ui/button";
import { Empty, Heading } from "./common";
import type { Workspace } from "@/lib/use-workspace";
import { formatBytes } from "@/lib/utils";

const number = (value: number) => value.toLocaleString();
export function Usage({ workspace: w }: { workspace: Workspace }) {
  const s = w.usage?.storage;
  return (
    <>
      <Heading
        eyebrow="A little transparency"
        title="See what your context costs."
        action={
          <Button
            variant="outline"
            disabled={!!w.busy}
            onClick={() => void w.refreshUsage()}
          >
            <RefreshCw />
            Refresh usage
          </Button>
        }
      >
        Measured work, honest limits. A snapshot across all your collections,
        including retained history.
      </Heading>
      {!s ? (
        <Empty icon={<ActivityIcon />} title="Measurements, when you ask">
          Refresh usage to read your saved storage and model-call totals.
        </Empty>
      ) : (
        <div id="usage-results">
          <div className="metric-grid">
            <article className="metric-card">
              <Database />
              <span>Original sources</span>
              <strong title={`${number(s.source_text_utf8_bytes)} bytes`}>
                {formatBytes(s.source_text_utf8_bytes)}
                <small>UTF-8 text</small>
              </strong>
              <p>{s.source_revisions} revisions · raw + formatted</p>
            </article>
            <article className="metric-card">
              <span>Structured memories</span>
              <strong title={`${number(s.claim_json_utf8_bytes)} bytes`}>
                {formatBytes(s.claim_json_utf8_bytes)}
                <small>UTF-8 JSON</small>
              </strong>
              <p>{s.claim_revisions} revisions</p>
            </article>
            <article className="metric-card">
              <span>Supporting passages</span>
              <strong title={`${number(s.passage_text_utf8_bytes)} bytes`}>
                {formatBytes(s.passage_text_utf8_bytes)}
                <small>UTF-8 text</small>
              </strong>
              <p>{s.supporting_passages} exact passages</p>
            </article>
          </div>
          <p className="meta">
            Sizes use decimal units: 1 KB = 1,000 bytes. Hover over a size for
            the exact byte count. Payload sizes, not physical database
            allocation or compression savings. RAM and table/index allocation
            are measured separately in the isolated evaluator report.
          </p>
          <section className="panel">
            <h2>Processing & history</h2>
            <p>
              Jobs:{" "}
              {Object.entries(w.usage!.jobs)
                .map(([name, n]) => `${n} ${name}`)
                .join(" · ") || "none"}
            </p>
            <p>
              Claim history:{" "}
              {Object.entries(s.claim_lifecycle)
                .map(([name, n]) => `${n} ${name}`)
                .join(" · ") || "none"}
            </p>
          </section>
          <section className="panel">
            <h2>Model usage</h2>
            <p className="meta">
              Application usage by model and role, not account-wide or per-key
              billing.
            </p>
            {!w.usage!.models.length && (
              <p>No model calls recorded for this owner.</p>
            )}
            {w.usage!.models.map((model, index) => (
              <article className="model-usage" key={index}>
                <span className="eyebrow">{model.role}</span>
                <h3>{model.model}</h3>
                <p>
                  Allowance: {model.allowance}. {model.attempts} attempts ·{" "}
                  {model.succeeded} passed application checks · {model.failed}{" "}
                  failed · {model.in_flight} unsettled.
                </p>
                <p>
                  Known tokens: {number(model.known_input_tokens)} input +{" "}
                  {number(model.known_output_tokens)} output from{" "}
                  {model.known_usage_calls} calls.
                </p>
                <p className="meta">
                  {model.unknown_usage_calls} calls have unknown usage;{" "}
                  {number(model.unsettled_reserved_tokens)} tokens remain
                  conservatively reserved. Reservations are not measured
                  consumption.
                </p>
                <p>
                  {model.timed_calls
                    ? `Provider latency: p50 ${model.latency_p50_ms?.toFixed(1)} ms · p95 ${model.latency_p95_ms?.toFixed(1)} ms (${model.timed_calls} timed attempts, including failures; small samples are not a benchmark).`
                    : "Provider latency: no timed attempts."}
                </p>
              </article>
            ))}
            <div className="measurement-note">
              <strong>Cost: unmeasured.</strong>
              <p>
                Provider billing and rates are not connected. Semantic accuracy
                requires a labeled evaluation; completed jobs and token totals
                do not establish understanding.
              </p>
            </div>
          </section>
        </div>
      )}
      <section className="panel">
        <h2>This browser action</h2>
        <p id="operation-timing" className="meta">
          {w.timing ? (
            <>
              {w.timing.outcome === "completed" ? "Completed" : "Failed"} in{" "}
              {w.timing.elapsed_ms.toFixed(1)} ms in this browser.{" "}
              {w.timing.stages
                ? `Server stages: ${w.timing.stages}`
                : "Server timing unavailable."}{" "}
              Stages include nested work; do not add them together.
            </>
          ) : (
            "No action measured in this view."
          )}
        </p>
      </section>
    </>
  );
}
