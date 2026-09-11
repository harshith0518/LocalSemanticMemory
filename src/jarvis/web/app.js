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

const messages = {
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
  for (const node of ui["source-list"].querySelectorAll("button"))
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
    signal: AbortSignal.any([signal, AbortSignal.timeout(15000)]),
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
