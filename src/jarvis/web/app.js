"use strict";

// This client retains only the current page's context. The backend owns access and writes.
const ui = Object.fromEntries(
  [...document.querySelectorAll("[id]")].map((node) => [node.id, node]),
);
let mode = "normal";
let epoch = 0;
let pending = null;
let opened = null;
let nextAfter = null;
let policyRevision = null;
let sourceCount = 0;
let memoryAfter = null;
let editing = null;
let reviewedControl = null;
let lastAnswer = null;
let questionIndex = 0;

const messages = {
  provider_disabled:
    "Live model calls are disabled. Source search and memory controls remain available.",
  trial_input_denied:
    "This trial permits only the bundled synthetic sample. Your sources remain saved.",
  budget_exhausted:
    "The evaluation allowance is exhausted. Your saved sources and memories remain available.",
  context_limit:
    "This collection exceeds the current processing context limit. No partial interpretation was saved.",
  import_conflict:
    "Import stopped: a record differs from the saved original. No records in this batch were changed.",
  stale_revision:
    "Your workspace changed during this action. Open the collection again before retrying.",
  private_operation_denied: "Saved sources are unavailable in Private mode.",
  reference_unavailable:
    "This source is no longer available. Open the collection again.",
  invalid_input:
    "Check the collection name and file format. The entire batch must contain valid JSONL records.",
  database_unavailable:
    "The workspace is unavailable. Check the connection and try again.",
  excluded_source: "This evidence was forgotten and cannot be used again.",
  provider_failed:
    "The model provider could not finish. This is a service failure, not missing evidence.",
  provider_response_invalid:
    "The model response failed validation. No answer was released.",
};

function feedback(message = "", error = false) {
  ui.feedback.textContent = message;
  ui.feedback.classList.toggle("error", error);
}

function clearEvidence() {
  ui.evidence.hidden = true;
  ui["evidence-empty"].hidden = false;
  for (const id of [
    "record-title",
    "revision",
    "job-state",
    "raw-text",
    "formatted-text",
    "captured-at",
    "imported-at",
    "source-id",
    "job-status",
    "job-attempts",
    "capture-metadata",
  ])
    ui[id].textContent = "";
  for (const details of ui.evidence.querySelectorAll("details"))
    details.open = false;
}

function clearSources() {
  clearAnswer();
  clearControl();
  ui["search-form"].reset();
  ui["search-results"].replaceChildren();
  ui["search-state"].textContent = "Search runs only when you ask.";
  memoryAfter = null;
  ui["memory-list"].replaceChildren();
  ui["memory-history"].replaceChildren();
  ui["processing-state"].textContent =
    "Open a collection to inspect processing.";
  ui["more-memories"].hidden = true;
  opened = null;
  nextAfter = null;
  policyRevision = null;
  sourceCount = 0;
  ui["source-list"].replaceChildren();
  ui["source-count"].textContent = "—";
  ui["list-state"].textContent = "Open a collection to see its sources.";
  ui["list-state"].hidden = false;
  ui["load-more"].hidden = true;
  clearEvidence();
}

function cancelPending() {
  epoch += 1;
  pending?.abort();
  pending = null;
  setBusy(false);
}

function setBusy(busy) {
  for (const node of document.querySelectorAll("[data-normal]"))
    node.disabled = busy || mode === "private";
  ui.namespace.disabled = busy || mode === "private";
  for (const node of document.querySelectorAll(
    "#source-list button, #memory-list button",
  ))
    node.disabled = busy || mode === "private";
  ui["normal-panel"].setAttribute("aria-busy", String(busy));
}

function switchMode(value) {
  mode = value;
  cancelPending();
  clearSources();
  ui["import-form"].reset();
  ui["collection-form"].reset();
  for (const details of document.querySelectorAll("details"))
    details.open = false;
  feedback();
  document.body.classList.toggle("private", mode === "private");
  ui["normal-panel"].hidden = mode === "private";
  ui["private-panel"].hidden = mode !== "private";
  ui["mode-note"].textContent =
    mode === "private"
      ? "Private mode · Saved sources are not read. Imports are paused."
      : "Normal mode · Imports are saved to your local workspace.";
  setBusy(false);
}

function assertCurrent(ticket) {
  if (ticket !== epoch || mode !== "normal")
    throw new DOMException("Cancelled", "AbortError");
}

async function request(path, options, ticket, signal) {
  assertCurrent(ticket);
  const response = await fetch(path, {
    ...options,
    signal: AbortSignal.any([
      signal,
      AbortSignal.timeout(
        path === "/ask" || path === "/feedback" ? 390000 : 15000,
      ),
    ]),
    cache: "no-store",
    credentials: "omit",
    redirect: "error",
    headers: { "X-Jarvis-Mode": "normal", ...options?.headers },
  });
  assertCurrent(ticket);
  const result = await response.json();
  assertCurrent(ticket);
  if (!response.ok)
    throw new Error(
      messages[result.reason] ||
        "The action could not be completed. Please try again.",
    );
  return result;
}

async function action(operation) {
  if (mode !== "normal" || pending) return;
  const controller = new AbortController();
  const ticket = epoch;
  pending = controller;
  setBusy(true);
  feedback("Working…");
  try {
    await operation(ticket, controller.signal);
  } catch (error) {
    if (ticket === epoch && error.name !== "AbortError") {
      // Only fixed locally owned messages reach the page; never echo driver/network errors.
      const known = Object.values(messages).includes(error.message);
      feedback(
        known
          ? error.message
          : "The action could not be completed. Check the connection and try again. An interrupted import may already have saved; retry the same file and collection safely.",
        true,
      );
    }
  } finally {
    if (ticket === epoch) {
      pending = null;
      setBusy(false);
    }
  }
}

function collection() {
  if (!ui["collection-form"].reportValidity()) return null;
  return ui.namespace.value;
}

function date(value) {
  return value === null ? "Not provided" : value;
}

function renderPage(page, append = false) {
  if (!append) {
    clearSources();
    opened = page.namespace;
  }
  policyRevision = page.policy_revision;
  nextAfter = page.next_after;
  for (const source of page.observations) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "source-button";
    button.setAttribute("aria-pressed", "false");
    const title = document.createElement("strong");
    title.textContent = source.source_key.split(":").at(-1);
    const detail = document.createElement("span");
    detail.textContent = source.captured_at
      ? `Captured ${source.captured_at.slice(0, 10)}`
      : "Capture time not provided";
    button.append(title, detail);
    button.addEventListener("click", () => inspect(source.id, button));
    const item = document.createElement("li");
    item.append(button);
    ui["source-list"].append(item);
  }
  sourceCount += page.observations.length;
  ui["source-count"].textContent = `${sourceCount}${nextAfter ? "+" : ""}`;
  ui["list-state"].hidden = sourceCount > 0;
  ui["list-state"].textContent =
    "This collection is empty. Import a file to get started.";
  ui["load-more"].hidden = !nextAfter;
}

async function loadPage(namespace, ticket, signal, after = null) {
  const query = new URLSearchParams({ namespace, limit: "50" });
  if (after) query.set("after", after);
  return request(`/sources?${query}`, {}, ticket, signal);
}

function inspect(id, button) {
  action(async (ticket, signal) => {
    clearEvidence();
    const result = await request(
      `/sources/${encodeURIComponent(id)}`,
      {},
      ticket,
      signal,
    );
    const source = result.observation;
    for (const row of ui["source-list"].querySelectorAll("button"))
      row.setAttribute("aria-pressed", String(row === button));
    ui["record-title"].textContent = source.source_key.split(":").at(-1);
    ui.revision.textContent = `Revision ${source.revision}`;
    ui["job-state"].textContent =
      result.job?.status === "pending"
        ? "Saved · Memory processing has not started."
        : "Saved source · No answer was generated.";
    ui["raw-text"].textContent = source.raw_text;
    ui["formatted-text"].textContent =
      source.formatted_text ?? "No formatted version was provided.";
    ui["captured-at"].textContent = date(source.captured_at);
    ui["imported-at"].textContent = date(source.imported_at);
    ui["source-id"].textContent = source.id;
    ui["job-status"].textContent = result.job?.status ?? "Not available";
    ui["job-attempts"].textContent = result.job
      ? String(result.job.attempts)
      : "Not available";
    ui["capture-metadata"].textContent =
      source.capture_metadata === null
        ? "No capture metadata was provided."
        : JSON.stringify(source.capture_metadata, null, 2);
    ui["evidence-empty"].hidden = true;
    ui.evidence.hidden = false;
    feedback("Original and formatted text belong to the same observation.");
  });
}

ui["collection-form"].addEventListener("submit", (event) => {
  event.preventDefault();
  const namespace = collection();
  if (!namespace) return;
  action(async (ticket, signal) => {
    clearSources();
    renderPage(await loadPage(namespace, ticket, signal));
    await refreshMemories(ticket, signal);
    feedback("Collection opened.");
  });
});

ui.namespace.addEventListener("input", () => {
  cancelPending();
  clearSources();
  feedback();
});

ui["import-form"].addEventListener("submit", (event) => {
  event.preventDefault();
  const namespace = collection();
  const file = ui["import-file"].files[0];
  if (!namespace || !file || mode !== "normal") return;
  if (file.size > 1024 * 1024 || file.size === 0) {
    feedback("Choose a nonempty JSONL file no larger than 1 MB.", true);
    return;
  }
  action(async (ticket, signal) => {
    // Fetch the current policy via the shared service; the server rechecks it atomically.
    const page = await loadPage(namespace, ticket, signal);
    renderPage(page);
    const query = new URLSearchParams({
      namespace,
      expected_policy_revision: String(policyRevision),
    });
    const result = await request(
      `/sources/import?${query}`,
      {
        method: "POST",
        headers: { "Content-Type": "application/x-ndjson" },
        body: file,
      },
      ticket,
      signal,
    );
    ui["import-form"].reset();
    feedback(`Saved ${result.created} new · ${result.unchanged} unchanged.`);
    // A refresh failure must not disguise a successful committed import.
    try {
      renderPage(await loadPage(namespace, ticket, signal));
    } catch (error) {
      assertCurrent(ticket);
      feedback(
        `Import saved: ${result.created} new, ${result.unchanged} unchanged. Open the collection to refresh its sources.`,
      );
    }
  });
});

ui["load-more"].addEventListener("click", () => {
  if (!opened || !nextAfter) return;
  action(async (ticket, signal) => {
    renderPage(await loadPage(opened, ticket, signal, nextAfter), true);
    feedback("More sources loaded.");
  });
});

for (const input of document.querySelectorAll('input[name="mode"]'))
  input.addEventListener("change", () => switchMode(input.value));

function paragraph(text, className = "") {
  const node = document.createElement("p");
  node.textContent = text;
  node.className = className;
  return node;
}

function memoryLabel(claim) {
  const c = claim.content;
  const value = c.value;
  return `${c.subject.label} · ${c.negated ? "Not: " : ""}${c.predicate.replaceAll("_", " ")}: ${value.value}${value.unit ? ` ${value.unit}` : ""}`;
}

function clearAnswer() {
  lastAnswer = null;
  ui["ask-form"].reset();
  ui["ask-result"].replaceChildren();
  ui["ask-state"].textContent = "Ask runs only when you choose.";
  ui["answer-feedback"].hidden = true;
  ui["feedback-guidance"].textContent = "";
  ui["feedback-kind"].value = "unclear";
}

function clearControl() {
  editing = null;
  reviewedControl = null;
  ui["control-form"].reset();
  ui["control-panel"].hidden = true;
  ui["control-target"].textContent = "";
  ui["control-qualifiers"].replaceChildren();
  ui["control-preview"].replaceChildren();
  ui["confirm-control"].hidden = true;
}

function renderAnswer(result, payload) {
  lastAnswer = { result, payload };
  ui["ask-result"].replaceChildren(paragraph(result.text, "passage"));
  ui["ask-state"].textContent = {
    answered: "Answer from recorded evidence",
    draft: "Draft — not sent",
    unknown: "Not established by the available evidence",
    clarification: "Clarification needed",
  }[result.status];
  const sources = new Map(result.sources.map((s) => [s.id, s]));
  for (const passage of result.citations) {
    const details = document.createElement("details");
    const summary = document.createElement("summary");
    summary.textContent = `Source: ${sources.get(passage.source_id)?.source_key.split(":").at(-1) ?? "Original record"} · ${passage.variant}`;
    details.append(summary, paragraph(passage.exact_text, "passage"));
    const button = document.createElement("button");
    button.type = "button";
    button.className = "secondary";
    button.textContent = "Inspect cited source";
    button.setAttribute("data-normal", "");
    button.addEventListener("click", () => inspect(passage.source_id, null));
    details.append(button);
    ui["ask-result"].append(details);
  }
  ui["answer-feedback"].hidden = !result.call_ids.length;
}

ui["ask-form"].addEventListener("submit", (event) => {
  event.preventDefault();
  const namespace = collection();
  if (!namespace) return;
  const payload = {
    namespace,
    question: ui["ask-question"].value,
    representation: ui["ask-representation"].value,
  };
  action(async (ticket, signal) => {
    lastAnswer = null;
    ui["answer-feedback"].hidden = true;
    ui["ask-result"].replaceChildren();
    ui["ask-state"].textContent = "Reading evidence and checking the answer…";
    try {
      const result = await request(
        "/ask",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        },
        ticket,
        signal,
      );
      renderAnswer(result, payload);
      feedback(
        "Answer checked against current source references. Review its meaning and evidence.",
      );
    } catch (error) {
      assertCurrent(ticket);
      ui["ask-state"].textContent =
        "The answer could not finish. This does not establish that a fact is unknown.";
      throw error;
    }
  });
});

ui["sample-questions"].addEventListener("click", () =>
  action(async (ticket, signal) => {
    const result = await request("/trial/questions", {}, ticket, signal);
    ui["ask-question"].value =
      result.questions[questionIndex++ % result.questions.length];
    feedback("Synthetic sample question selected. Choose Ask when ready.");
  }),
);

ui["review-feedback"].addEventListener("click", () => {
  if (!lastAnswer?.result.call_ids.length) return;
  const previous = lastAnswer;
  const payload = {
    call_id: previous.result.call_ids.at(-1),
    request: previous.payload,
    diagnosis: ui["feedback-kind"].value,
  };
  action(async (ticket, signal) => {
    const result = await request(
      "/feedback",
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      },
      ticket,
      signal,
    );
    if (result.answer) renderAnswer(result.answer, result.request);
    ui["feedback-guidance"].textContent = result.guidance;
    feedback(result.guidance);
  });
});

function qualifier(label, name, value, choices = null) {
  const field = document.createElement("label");
  field.textContent = label;
  const input = document.createElement(choices ? "select" : "input");
  input.name = name;
  input.setAttribute("data-normal", "");
  if (choices)
    for (const choice of choices) {
      const option = document.createElement("option");
      option.value = choice;
      option.textContent = choice.replaceAll("_", " ");
      input.append(option);
    }
  input.value = value ?? "";
  field.append(input);
  ui["control-qualifiers"].append(field);
}

function editMemory(claim, actionName) {
  if (mode !== "normal" || pending) return;
  clearControl();
  editing = { claim, action: actionName, operation_id: crypto.randomUUID() };
  ui["control-title"].textContent = {
    correct: "Correct an interpretation",
    world_change: "Record a change in the world",
    forget: "Forget this memory",
  }[actionName];
  ui["control-target"].textContent = memoryLabel(claim);
  const forget = actionName === "forget";
  ui["replacement-fields"].hidden = forget;
  ui["forget-explanation"].hidden = !forget;
  ui["control-statement"].required = !forget;
  ui["control-value"].required = !forget;
  const c = claim.content;
  ui["control-value"].value = String(c.value.value);
  if (!forget) {
    qualifier("Who or what", "subject", c.subject.label);
    qualifier("Property", "predicate", c.predicate);
    qualifier("Value type", "kind", c.value.kind, [
      "text",
      "date",
      "quantity",
      "boolean",
    ]);
    qualifier("Units, if any", "unit", c.value.unit);
    qualifier("Applies to", "scope_kind", c.scope.kind, [
      "unspecified",
      "global",
      "project",
      "task",
    ]);
    qualifier("Project or task name", "scope_key", c.scope.key);
    qualifier("Reported by", "attribution", c.attribution.label);
    qualifier("Evidence", "evidence_status", c.evidence_status, [
      "reported",
      "tentative",
      "disputed",
    ]);
    qualifier("Meaning", "modality", c.modality, [
      "asserted",
      "conditional",
      "hypothetical",
      "question",
      "quoted",
    ]);
    qualifier("Is this negated?", "negated", String(c.negated), [
      "false",
      "true",
    ]);
    qualifier("Condition, if any", "condition", c.condition);
    qualifier(
      "Event date/time (blank = unknown)",
      "event",
      c.time.event?.value,
    );
    qualifier(
      "Applies from (blank = unknown)",
      "valid_from",
      c.time.valid_from?.value,
    );
    qualifier(
      "Applies until (blank = unknown)",
      "valid_to",
      c.time.valid_to?.value,
    );
  }
  ui["control-panel"].hidden = false;
  ui["control-panel"].scrollIntoView({ block: "start" });
}

ui["cancel-control"].addEventListener("click", clearControl);
ui["control-form"].addEventListener("input", () => {
  reviewedControl = null;
  ui["control-preview"].replaceChildren();
  ui["confirm-control"].hidden = true;
});
ui["control-form"].addEventListener("submit", (event) => {
  event.preventDefault();
  if (!editing || !opened) return;
  const payload = {
    operation_id: editing.operation_id,
    namespace: opened,
    target_revision_id: editing.claim.id,
    expected_policy_revision: policyRevision,
    action: editing.action,
  };
  if (editing.action !== "forget") {
    const f = Object.fromEntries(new FormData(ui["control-form"]));
    const value = { kind: f.kind, value: ui["control-value"].value };
    if (f.kind === "quantity") value.unit = f.unit || null;
    if (f.kind === "boolean") {
      if (!["true", "false"].includes(value.value)) {
        feedback("A yes/no value must be true or false.", true);
        return;
      }
      value.value = value.value === "true";
    }
    const time = Object.fromEntries(
      ["event", "valid_from", "valid_to"].map((key) => [
        key,
        f[key]
          ? {
              precision: f[key].includes("T") ? "instant" : "date",
              value: f[key],
            }
          : null,
      ]),
    );
    payload.statement = ui["control-statement"].value;
    payload.replacement = {
      subject: { label: f.subject, entity_id: null },
      predicate: f.predicate,
      value,
      scope: {
        kind: f.scope_kind,
        key: ["project", "task"].includes(f.scope_kind) ? f.scope_key : null,
      },
      attribution: { label: f.attribution, entity_id: null },
      evidence_status: f.evidence_status,
      modality: f.modality,
      negated: f.negated === "true",
      condition: f.condition || null,
      time,
    };
  }
  action(async (ticket, signal) => {
    const preview = await request(
      "/controls/preview",
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      },
      ticket,
      signal,
    );
    reviewedControl = { ...payload, preview_token: preview.preview_token };
    const content = document.createDocumentFragment();
    if (preview.replacement)
      content.append(
        paragraph(`Proposed: ${memoryLabel({ content: preview.replacement })}`),
        paragraph(preview.statement, "passage"),
      );
    content.append(
      paragraph(
        `${preview.sources.length} supporting note(s) · ${preview.affected_revision_ids.length} linked revision(s). Original history remains visible.`,
        "help",
      ),
    );
    const details = document.createElement("details");
    const summary = document.createElement("summary");
    summary.textContent = "Review affected notes";
    details.append(summary);
    for (const source of preview.sources)
      details.append(
        paragraph(source.source_key.split(":").slice(1).join(" / "), "help"),
        paragraph(source.raw_text, "passage"),
      );
    content.append(details);
    ui["control-preview"].replaceChildren(content);
    ui["confirm-control"].hidden = false;
    feedback("Review this exact change before confirming.");
  });
});

ui["confirm-control"].addEventListener("click", () => {
  if (!reviewedControl) return;
  const payload = reviewedControl;
  action(async (ticket, signal) => {
    const result = await request(
      "/controls/apply",
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      },
      ticket,
      signal,
    );
    clearAnswer();
    clearControl();
    ui["search-results"].replaceChildren();
    ui["memory-history"].replaceChildren();
    policyRevision = result.policy_revision;
    try {
      renderPage(await loadPage(payload.namespace, ticket, signal));
      await refreshMemories(ticket, signal);
    } catch (error) {
      assertCurrent(ticket);
      feedback(
        "Change saved. Open the collection to refresh its current state.",
      );
      return;
    }
    feedback(
      result.action === "forget"
        ? "Forgotten for future use and learning. Original history remains in Sources."
        : "Change saved with evidence. Later searches include your update.",
    );
  });
});

ui["search-form"].addEventListener("submit", (event) => {
  event.preventDefault();
  const namespace = collection();
  if (!namespace || mode !== "normal") return;
  action(async (ticket, signal) => {
    ui["search-results"].replaceChildren();
    ui["search-state"].textContent = "Searching saved evidence…";
    const payload = {
      namespace,
      query: ui["search-query"].value,
      representation: ui["search-memories"].checked
        ? "sources_and_memories"
        : "sources",
      history: ui["search-history"].checked,
      captured_from: ui["search-from"].value
        ? `${ui["search-from"].value}T00:00:00Z`
        : null,
      captured_to: ui["search-to"].value
        ? `${ui["search-to"].value}T23:59:59.999999Z`
        : null,
      include_undated: ui["search-undated"].checked,
    };
    let result;
    try {
      result = await request(
        "/search",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        },
        ticket,
        signal,
      );
    } catch (error) {
      assertCurrent(ticket);
      ui["search-state"].textContent =
        "Search could not finish. This does not mean evidence is absent.";
      throw error;
    }
    const state =
      result.status === "no_matches"
        ? "No matching evidence found. Different wording may help; this does not establish that a fact is unknown."
        : result.status === "evidence_budget_exceeded"
          ? "The matching record is too large for this search view. Browse the original sources to inspect it."
          : `${result.matches.length} matching source${result.matches.length === 1 ? "" : "s"}.${result.has_more ? " More evidence is available; narrow the search for a different selection." : ""}${result.budget_limited ? " The evidence limit was reached; records were kept whole." : ""}`;
    ui["search-state"].textContent = state;
    const primary = result.matches.map((match) => match.source_id);
    const sources = [...result.sources].sort((a, b) => {
      const rank = (id) =>
        primary.includes(id) ? primary.indexOf(id) : primary.length;
      return rank(a.id) - rank(b.id);
    });
    for (const source of sources) {
      const section = document.createElement("article");
      const title = document.createElement("h3");
      title.textContent = source.source_key.split(":").at(-1);
      section.append(
        title,
        paragraph(
          `${primary.includes(source.id) ? "Matching source" : "Additional supporting source"} · Captured: ${source.captured_at ?? "Not provided"}`,
          "help",
        ),
      );
      section.append(
        paragraph("Original transcript", "help"),
        paragraph(source.raw_text, "passage"),
      );
      if (source.formatted_text !== null)
        section.append(
          paragraph("Formatted text · same observation", "help"),
          paragraph(source.formatted_text, "passage"),
        );
      for (const claim of result.memories.filter((m) =>
        m.passages.some((p) => p.source_id === source.id),
      )) {
        const c = claim.content;
        section.append(
          paragraph(memoryLabel(claim)),
          paragraph(
            `${claim.lifecycle} · ${c.evidence_status} · ${c.modality} · Scope: ${c.scope.key ?? c.scope.kind} · Attributed to: ${c.attribution.label}`,
            "help",
          ),
        );
        if (c.condition) section.append(paragraph(`Only if: ${c.condition}`));
        section.append(
          paragraph(
            `Event: ${c.time.event?.value ?? "Unknown"} · Applies from: ${c.time.valid_from?.value ?? "Unknown"} · Until: ${c.time.valid_to?.value ?? "Unknown"}`,
            "help",
          ),
        );
      }
      const button = document.createElement("button");
      button.type = "button";
      button.className = "secondary";
      button.setAttribute("data-normal", "");
      button.textContent = "Inspect original";
      button.addEventListener("click", () => inspect(source.id, null));
      section.append(button);
      ui["search-results"].append(section);
    }
    feedback("Search finished. No question or answer was saved as memory.");
  });
});

function renderMemoryPage(page, append = false) {
  if (!append) ui["memory-list"].replaceChildren();
  for (const claim of page.memories) {
    const item = document.createElement("li");
    const button = document.createElement("button");
    button.type = "button";
    button.className = "source-button";
    const title = document.createElement("strong");
    title.textContent = memoryLabel(claim);
    const qualifier = document.createElement("span");
    const c = claim.content;
    qualifier.textContent = `${c.evidence_status} · ${c.scope.key ?? c.scope.kind} · ${c.modality}`;
    button.append(title, qualifier);
    if (c.condition)
      button.append(paragraph(`Only if: ${c.condition}`, "help"));
    button.addEventListener("click", () =>
      action(async (ticket, signal) => {
        const history = await request(
          `/memories/${encodeURIComponent(claim.claim_id)}`,
          {},
          ticket,
          signal,
        );
        const content = document.createDocumentFragment();
        for (const revision of history.revisions) {
          const section = document.createElement("article");
          const c = revision.content;
          section.append(
            paragraph(
              `Revision ${revision.revision} · ${revision.lifecycle} · ${c.evidence_status}`,
              "help",
            ),
          );
          section.append(paragraph(memoryLabel(revision)));
          section.append(
            paragraph(
              `Scope: ${c.scope.key ?? c.scope.kind} · Attributed to: ${c.attribution.label} · ${c.modality}${c.negated ? " · Negated" : ""}`,
              "help",
            ),
          );
          if (c.condition)
            section.append(paragraph(`Condition: ${c.condition}`));
          section.append(
            paragraph(
              `Event: ${c.time.event?.value ?? "Unknown"} · Applies from: ${c.time.valid_from?.value ?? "Unknown"} · Until: ${c.time.valid_to?.value ?? "Unknown"}`,
              "help",
            ),
          );
          for (const passage of revision.passages) {
            section.append(
              paragraph(
                `Supporting passage · ${passage.variant} · source revision ${passage.source_revision}`,
                "help",
              ),
            );
            section.append(paragraph(passage.exact_text, "passage"));
            const details = document.createElement("details");
            const summary = document.createElement("summary");
            summary.textContent = "Evidence details";
            details.append(
              summary,
              paragraph(
                `Source ${passage.source_id} · characters [${passage.start}, ${passage.end})`,
                "help",
              ),
            );
            const original = document.createElement("button");
            original.type = "button";
            original.className = "secondary";
            original.textContent = "View original source";
            original.setAttribute("data-normal", "");
            original.addEventListener("click", () =>
              inspect(passage.source_id, null),
            );
            details.append(original);
            section.append(details);
          }
          content.append(section);
        }
        if (history.relations.length) {
          const details = document.createElement("details");
          const summary = document.createElement("summary");
          summary.textContent = "Revision links";
          details.append(summary);
          for (const relation of history.relations)
            details.append(
              paragraph(
                `${relation.kind}: ${relation.from_revision_id} → ${relation.to_revision_id}`,
                "help",
              ),
            );
          content.append(details);
        }
        ui["memory-history"].replaceChildren(content);
        feedback("Memory history and exact supporting passages loaded.");
      }),
    );
    item.append(button);
    const controls = document.createElement("div");
    controls.className = "memory-actions";
    for (const [actionName, label] of [
      ["correct", "Correct"],
      ["world_change", "Record a change"],
      ["forget", "Forget"],
    ]) {
      const control = document.createElement("button");
      control.type = "button";
      control.className = "secondary";
      control.textContent = label;
      control.setAttribute("data-normal", "");
      control.addEventListener("click", () => editMemory(claim, actionName));
      controls.append(control);
    }
    item.append(controls);
    ui["memory-list"].append(item);
  }
  memoryAfter = page.next_after;
  ui["more-memories"].hidden = !memoryAfter;
}

async function refreshMemories(ticket, signal) {
  if (!opened) return;
  const query = new URLSearchParams({ namespace: opened });
  const status = await request(`/processing?${query}`, {}, ticket, signal);
  const counts = Object.entries(status.counts)
    .map(([name, count]) => `${count} ${name}`)
    .join(" · ");
  const decisions = Object.entries(status.decisions)
    .filter(([, n]) => n > 0)
    .map(([name, count]) => `${count} ${name.replaceAll("_", " ")}`)
    .join(" · ");
  const processingErrors = {
    invalid_input: "A model proposal failed validation",
    invalid_passage: "A proposal did not match its source passages",
    invalid_transition: "A proposed memory change was rejected",
    stale_revision:
      "Sources, memories or permissions changed during processing",
    provider_failed: "The model provider could not complete the request",
    provider_response_invalid:
      "The model provider returned an unusable response",
    budget_exhausted: "The evaluation allowance is exhausted",
    context_limit: "The processing context limit was reached",
    operation_failed: "Processing could not complete",
    retry_limit_reached: "The retry limit was reached",
  };
  const failures = [
    ...new Set(
      status.failures.map(
        (f) =>
          processingErrors[f.reason] || "A processing job could not complete",
      ),
    ),
  ].join("; ");
  ui["processing-state"].textContent =
    `${counts || "No sources"}.${decisions ? ` Outcomes: ${decisions}.` : ""}${failures ? ` Issues: ${failures}.` : ""} ${status.provider_enabled ? "Processing is enabled; select Refresh to check progress." : "Live processing is disabled."}`;
  renderMemoryPage(await request(`/memories?${query}`, {}, ticket, signal));
}

for (const [id, retry] of [
  ["process-button", false],
  ["retry-processing", true],
])
  ui[id].addEventListener("click", () => {
    if (!opened) {
      feedback("Open a collection first.", true);
      return;
    }
    action(async (ticket, signal) => {
      const result = await request(
        "/processing",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            namespace: opened,
            expected_policy_revision: policyRevision,
            retry_failed: retry,
          }),
        },
        ticket,
        signal,
      );
      feedback(
        `Queued ${result.requested} sources. Processing continues in the background; refresh to inspect the result.`,
      );
      await refreshMemories(ticket, signal);
    });
  });

ui["refresh-memories"].addEventListener("click", () =>
  action(async (ticket, signal) => {
    await refreshMemories(ticket, signal);
    feedback(opened ? "Memories refreshed." : "Open a collection first.");
  }),
);

ui["more-memories"].addEventListener("click", () => {
  if (!opened || !memoryAfter) return;
  action(async (ticket, signal) => {
    const query = new URLSearchParams({
      namespace: opened,
      after: memoryAfter,
    });
    renderMemoryPage(
      await request(`/memories?${query}`, {}, ticket, signal),
      true,
    );
  });
});

// A restored page must not resurrect the prior DOM or browser-restored file/form state.
window.addEventListener("pagehide", () => {
  switchMode("private");
});
window.addEventListener("pageshow", (event) => {
  if (event.persisted) switchMode("private");
  for (const input of document.querySelectorAll('input[name="mode"]'))
    input.checked = input.value === mode;
});
ui["collection-form"].reset();
ui["import-form"].reset();

fetch("/ready", {
  cache: "no-store",
  credentials: "omit",
  redirect: "error",
  signal: AbortSignal.timeout(5000),
})
  .then((response) => response.json())
  .then((result) => {
    const ready = result.status === "ready";
    ui.connection.textContent = ready
      ? "Workspace connected"
      : "Workspace unavailable";
    ui["connection-dot"].className = `dot ${ready ? "ready" : "offline"}`;
  })
  .catch(() => {
    ui.connection.textContent = "Workspace unavailable";
    ui["connection-dot"].className = "dot offline";
  });
