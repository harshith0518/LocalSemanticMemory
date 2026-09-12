export type Page = "conversation" | "sources" | "memories" | "usage" | "workflow";
export type Representation = "sources" | "sources_and_memories" | "history";
export type SourceSummary = {
  id: string;
  source_key: string;
  revision: number;
  captured_at: string | null;
  imported_at: string;
};
export type Source = SourceSummary & {
  raw_text: string;
  formatted_text: string | null;
  capture_metadata: Record<string, unknown> | null;
  kind: string;
};
export type Job = { id: string; status: string; attempts: number };
export type Inspection = {
  observation: Source;
  job: Job | null;
  latest_revision: number;
};
export type SourcePage = {
  namespace: string;
  policy_revision: number;
  observations: SourceSummary[];
  next_after: string | null;
};
export type Passage = {
  source_id: string;
  source_revision: number;
  variant: "raw" | "formatted";
  start: number;
  end: number;
  exact_text: string;
};
export type TimeValue = { precision: "date" | "instant"; value: string } | null;
export type ClaimContent = {
  subject: { label: string; entity_id: string | null };
  predicate: string;
  value: {
    kind: "text" | "date" | "quantity" | "boolean";
    value: string | boolean;
    unit?: string | null;
  };
  scope: {
    kind: "unspecified" | "global" | "project" | "task";
    key: string | null;
  };
  attribution: { label: string; entity_id: string | null };
  evidence_status: "reported" | "tentative" | "disputed";
  modality: "asserted" | "conditional" | "hypothetical" | "question" | "quoted";
  negated: boolean;
  condition: string | null;
  time: { event: TimeValue; valid_from: TimeValue; valid_to: TimeValue };
};
export type Claim = {
  id: string;
  claim_id: string;
  revision: number;
  lifecycle: string;
  content: ClaimContent;
  passages: Passage[];
};
export type MemoryPage = { memories: Claim[]; next_after: string | null };
export type History = {
  revisions: Claim[];
  relations: {
    kind: string;
    from_revision_id: string;
    to_revision_id: string;
  }[];
};
export type Processing = {
  counts: Record<string, number>;
  decisions: Record<string, number>;
  provider_enabled: boolean;
  failures: { job_id: string; reason: string }[];
};
export type Search = {
  status: "matched" | "no_matches" | "evidence_budget_exceeded";
  matches: { source_id: string }[];
  sources: Source[];
  memories: Claim[];
  evidence_bytes: number;
  has_more: boolean;
  budget_limited: boolean;
  policy_revision: number | null;
};
export type AnswerRequest = {
  namespace: string;
  question: string;
  representation: Representation;
};
export type Answer = {
  status: "answered" | "draft" | "unknown" | "clarification";
  text: string;
  citations: Passage[];
  sources: Source[];
  representation: Representation;
  call_ids: string[];
  evidence_bytes: number;
  model: string | null;
  metrics?: {
    calls: {
      id: string;
      model: string;
      input_tokens: number | null;
      output_tokens: number | null;
      reserved_tokens: number;
      elapsed_ms: number | null;
      status: string;
      error_code: string | null;
    }[];
    actual_cost_usd: number | null;
    semantic_entailment_certified: boolean;
  };
};
export type Turn = {
  id: string;
  question: string;
  request: AnswerRequest;
  answer?: Answer;
  error?: string;
  timing?: Timing;
};
export type ImportReceipt = {
  created: number;
  unchanged: number;
  policy_revision: number;
  observations: { source_id: string; record_id: string }[];
};
export type ModelUsage = {
  model: string;
  role: string;
  allowance: string;
  attempts: number;
  succeeded: number;
  failed: number;
  in_flight: number;
  known_input_tokens: number;
  known_output_tokens: number;
  known_usage_calls: number;
  unknown_usage_calls: number;
  unsettled_reserved_tokens: number;
  timed_calls: number;
  latency_p50_ms: number | null;
  latency_p95_ms: number | null;
};
export type Usage = {
  storage: {
    source_revisions: number;
    source_text_utf8_bytes: number;
    claim_revisions: number;
    claim_json_utf8_bytes: number;
    supporting_passages: number;
    passage_text_utf8_bytes: number;
    claim_lifecycle: Record<string, number>;
  };
  jobs: Record<string, number>;
  models: ModelUsage[];
};
export type ControlAction = "correct" | "world_change" | "forget";
export type ControlCommand = {
  operation_id: string;
  namespace: string;
  target_revision_id: string;
  expected_policy_revision: number;
  action: ControlAction;
  statement?: string;
  replacement?: ClaimContent;
  preview_token?: string;
};
export type ControlPreview = {
  preview_token: string;
  sources: Source[];
  affected_revision_ids: string[];
  statement?: string;
  replacement?: ClaimContent;
};
export type FeedbackResult = {
  status: string;
  guidance: string;
  answer?: Answer;
  request?: AnswerRequest;
};
export type Timing = {
  elapsed_ms: number;
  stages: string;
  outcome: "completed" | "failed";
};
