import type { ModelMetric, Turn } from "@/lib/types";
import { formatBytes } from "@/lib/utils";
import "./request-metrics.css";

type ModelCall = ModelMetric;
type Span = { name: string; duration: number };

const stages: Record<string, { label: string; note: string }> = {
  request: {
    label: "Server request",
    note: "Includes the stages in this request",
  },
  assessment: {
    label: "Assess message",
    note: "Decide what deserves retention and which answer context is needed",
  },
  turn_assessment: {
    label: "Assess message",
    note: "Includes the retention and answer-route decision",
  },
  assessment_validation: {
    label: "Validate retention decision",
    note: "Check allowed decisions and exact quotations from the message",
  },
  lease: {
    label: "Coordinate workspace access",
    note: "Acquire the processing lease",
  },
  reserve: {
    label: "Reserve model allowance",
    note: "Check and reserve the shared budget",
  },
  model: { label: "Model inference", note: "Wait for the provider response" },
  accounting: {
    label: "Record model usage",
    note: "Store measured usage and call status",
  },
  proposal_validation: {
    label: "Validate proposed memories",
    note: "Check the model's structured proposal",
  },
  memory_commit: {
    label: "Save memory decision",
    note: "Recheck eligibility and commit the result",
  },
  answer_context: {
    label: "Retrieve answer context",
    note: "Select eligible notes and memories",
  },
  answer_validation: {
    label: "Validate answer",
    note: "Check response format and source references",
  },
  answer_release: {
    label: "Release answer",
    note: "Recheck that evidence can still be used",
  },
  answer: {
    label: "Answer service",
    note: "Includes retrieval, inference and validation",
  },
};

const phaseLabels: Record<string, string> = {
  assessment: "Assess what to remember",
  capture: "Assess and retain message",
  learn: "Learn useful facts",
  answer: "Answer",
};

function duration(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value))
    return "Not measured";
  return value >= 1000
    ? `${(value / 1000).toLocaleString(undefined, { maximumFractionDigits: 2 })} s`
    : `${value.toLocaleString(undefined, { maximumFractionDigits: 1 })} ms`;
}

function parseSpans(value: string): Span[] {
  return value.split(",").flatMap((entry) => {
    const match = /^\s*([a-z_0-9]+);dur=([0-9.]+)\s*$/.exec(entry);
    if (!match) return [];
    const elapsed = Number(match[2]);
    return Number.isFinite(elapsed)
      ? [{ name: match[1], duration: elapsed }]
      : [];
  });
}

function count(value: number | null | undefined): string {
  return value === null || value === undefined
    ? "Unknown"
    : value.toLocaleString();
}

function tokenTotal(
  calls: ModelCall[],
  field: "input_tokens" | "output_tokens",
) {
  const known = calls.filter((call) => call[field] !== null);
  if (!calls.length) return "0";
  if (!known.length) return "Unknown";
  const total = known.reduce((sum, call) => sum + (call[field] ?? 0), 0);
  return `${total.toLocaleString()}${known.length < calls.length ? " + unknown" : ""}`;
}

function CallStatus({ call }: { call: ModelCall }) {
  const tone =
    call.status === "succeeded"
      ? "success"
      : call.status === "failed"
        ? "failure"
        : "neutral";
  return (
    <span className={`metric-status metric-status-${tone}`}>
      {call.status.replaceAll("_", " ")}
    </span>
  );
}

export function RequestMetrics({ turn }: { turn: Turn }) {
  const answer = turn.answer;
  const assessmentCalls =
    turn.learning?.assessment?.calls ?? answer?.assessment?.calls ?? [];
  const learningCalls = turn.learning?.calls ?? [];
  const answerCalls = answer?.metrics?.calls ?? turn.answerCalls ?? [];
  const calls = [
    ...assessmentCalls.map((call, index) => ({
      ...call,
      phase: "Assessment",
      attempt: index + 1,
    })),
    ...learningCalls.map((call, index) => ({
      ...call,
      phase: "Learning",
      attempt: index + 1,
    })),
    ...answerCalls.map((call, index) => ({
      ...call,
      phase: "Answer",
      attempt: index + 1,
    })),
  ];
  const recordedAnswerCount = answer?.call_ids.length ?? 0;
  const missingAnswerDetails = Math.max(
    0,
    recordedAnswerCount - answerCalls.length,
  );
  const callCount = calls.length + missingAnswerDetails;
  const timing = turn.timing;
  const requests = timing?.requests?.length
    ? timing.requests
    : timing?.stages
      ? [{ phase: "server", stages: timing.stages }]
      : [];
  const rows = requests.flatMap((request, requestIndex) =>
    parseSpans(request.stages).map((span, spanIndex) => ({
      ...span,
      phase: phaseLabels[request.phase] ?? "Server",
      key: `${requestIndex}-${spanIndex}`,
    })),
  );
  const failed = !!turn.error || timing?.outcome === "failed";
  const unmeasuredAnswer =
    failed && !answer?.metrics && turn.answerCalls === undefined;

  return (
    <details className="request-metrics query-metrics">
      <summary>
        <span>Request metrics</span>
        <span className="metrics-summary-detail">
          {timing ? duration(timing.elapsed_ms) : "Timing unavailable"}
          {" · "}
          {callCount} recorded model {callCount === 1 ? "call" : "calls"}
        </span>
      </summary>
      <div className="metrics-content">
        <dl className="metrics-overview">
          <div>
            <dt>Browser total</dt>
            <dd>{duration(timing?.elapsed_ms)}</dd>
            <small>
              {failed
                ? "Latest submission failed"
                : "Latest submission to answer"}
            </small>
          </div>
          <div>
            <dt>Model calls</dt>
            <dd>
              {callCount}
              {unmeasuredAnswer ? " + unknown" : ""}
            </dd>
            <small>
              {assessmentCalls.length} assessment · {learningCalls.length}{" "}
              learning · {answerCalls.length} answer
            </small>
          </div>
          <div>
            <dt>Input tokens</dt>
            <dd>
              {tokenTotal(calls, "input_tokens")}
              {unmeasuredAnswer || missingAnswerDetails ? " (known calls)" : ""}
            </dd>
            <small>All recorded model phases</small>
          </div>
          <div>
            <dt>Output tokens</dt>
            <dd>
              {tokenTotal(calls, "output_tokens")}
              {unmeasuredAnswer || missingAnswerDetails ? " (known calls)" : ""}
            </dd>
            <small>Provider-reported usage</small>
          </div>
        </dl>
        {answer && (
          <dl className="metrics-context" aria-label="Answer evidence metrics">
            <div>
              <dt>Evidence sources</dt>
              <dd>{answer.sources.length}</dd>
            </div>
            <div>
              <dt>Learned memories sent</dt>
              <dd>{count(answer.retrieval?.memories_reviewed)}</dd>
            </div>
            <div>
              <dt>Citations</dt>
              <dd>{answer.citations.length}</dd>
            </div>
            <div>
              <dt>Evidence payload</dt>
              <dd title={`${answer.evidence_bytes.toLocaleString()} bytes`}>
                {formatBytes(answer.evidence_bytes)}
              </dd>
            </div>
            <div>
              <dt>Context mode</dt>
              <dd>{answer.representation.replaceAll("_", " ")}</dd>
            </div>
          </dl>
        )}
        <div
          className="metrics-table-wrap"
          role="region"
          aria-label="Request timing details"
          tabIndex={0}
        >
          <table className="metrics-table">
            <caption>Where time went</caption>
            <thead>
              <tr>
                <th scope="col">Phase</th>
                <th scope="col">Step</th>
                <th scope="col">Duration</th>
                <th scope="col">What it measures</th>
              </tr>
            </thead>
            <tbody>
              <tr className="metric-total-row">
                <th scope="row">Whole turn</th>
                <td>Browser total</td>
                <td className="metric-number">
                  {duration(timing?.elapsed_ms)}
                </td>
                <td>Network, assessment, learning and answer requests</td>
              </tr>
              {rows.map((row) => (
                <tr
                  key={row.key}
                  className={
                    row.name === "request" ? "metric-total-row" : undefined
                  }
                >
                  <th scope="row">{row.phase}</th>
                  <td>
                    {stages[row.name]?.label ?? row.name.replaceAll("_", " ")}
                  </td>
                  <td className="metric-number">{duration(row.duration)}</td>
                  <td>{stages[row.name]?.note ?? "Measured server span"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="metrics-note">
          Server spans overlap and include nested work. Read each duration
          separately; they are not additive portions of the browser total.
        </p>
        {!rows.length && (
          <p className="metrics-note">
            Server stage measurements are unavailable for this response.
          </p>
        )}
        {!!calls.length && (
          <div
            className="metrics-table-wrap"
            role="region"
            aria-label="Model call details"
            tabIndex={0}
          >
            <table className="metrics-table">
              <caption>Model calls by phase</caption>
              <thead>
                <tr>
                  <th scope="col">Phase</th>
                  <th scope="col">Result</th>
                  <th scope="col">Provider time</th>
                  <th scope="col">Input tokens</th>
                  <th scope="col">Output tokens</th>
                </tr>
              </thead>
              <tbody>
                {calls.map((call) => (
                  <tr key={call.id} className="call-metric">
                    <th scope="row">
                      {call.phase} {call.attempt}
                    </th>
                    <td>
                      <CallStatus call={call} />
                      {call.error_code && (
                        <small className="metric-call-error">
                          {call.error_code.replaceAll("_", " ")}
                        </small>
                      )}
                    </td>
                    <td className="metric-number">
                      {duration(call.elapsed_ms)}
                    </td>
                    <td className="metric-number">
                      {count(call.input_tokens)}
                    </td>
                    <td className="metric-number">
                      {count(call.output_tokens)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {unmeasuredAnswer && (
          <p className="metrics-note">
            The answer failed before call details were returned. Its model usage
            is unknown here, not zero. Recorded assessment and learning calls
            remain shown.
          </p>
        )}
        {!!missingAnswerDetails && (
          <p className="metrics-note">
            Details for {missingAnswerDetails} recorded answer call(s) are
            unavailable; their usage is not included in known totals.
          </p>
        )}
        {!callCount && !failed && (
          <p className="metrics-note">
            No model call was needed for this response.
          </p>
        )}
        <p className="metrics-note">
          Provider billing is unmeasured. Tokens include assessment, learning,
          answering and recorded repairs, including earlier learning attempts
          after a retry. Browser total measures only the latest submission.
          Valid source references do not certify the answer's interpretation.
        </p>
        <details className="metrics-diagnostics">
          <summary>Technical details · models, call IDs and raw timing</summary>
          <p>
            Answer model:{" "}
            {answer?.model ??
              (failed ? "Not returned" : "No answer model call")}
            .
          </p>
          <ul>
            {calls.map((call) => {
              const details = call as ModelCall & { phase: string };
              return (
                <li key={call.id}>
                  <span>
                    {call.phase} ·{" "}
                    {details.model ?? "Model not returned for this call"}
                  </span>
                  <code>{call.id}</code>
                  {(call.input_tokens === null ||
                    call.output_tokens === null) &&
                    details.reserved_tokens !== undefined && (
                      <span>
                        Conservative reservation:{" "}
                        {details.reserved_tokens.toLocaleString()} tokens; not
                        measured usage.
                      </span>
                    )}
                </li>
              );
            })}
          </ul>
          <pre>{timing?.stages || "No raw server timing was returned."}</pre>
        </details>
      </div>
    </details>
  );
}
