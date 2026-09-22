// Synthetic UI acceptance against compose.test.yaml's isolated PostgreSQL backend.
import { after, before, test } from "node:test";
import assert from "node:assert/strict";
import { readFile, mkdir } from "node:fs/promises";
import { randomUUID } from "node:crypto";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const origin = "http://127.0.0.1:8001"; // Deliberately not configurable to the application port.
const fixture = await readFile(
  new URL("../../data/synthetic/sample-dictations.jsonl", import.meta.url),
);
let browser;
before(async () => {
  const ready = await fetch(`${origin}/ready`).then((response) =>
    response.json(),
  );
  assert.equal(
    ready.status,
    "ready",
    "Start the isolated Compose web service after migrations.",
  );
  browser = await chromium.launch({ headless: true });
});
after(async () => {
  await browser?.close();
});

async function eventually(
  check,
  message = "Expected UI state did not arrive",
  timeoutMs = 8000,
) {
  const deadline = Date.now() + timeoutMs;
  let last;
  do {
    try {
      return await check();
    } catch (error) {
      last = error;
    }
    await new Promise((resolve) => setTimeout(resolve, 40));
  } while (Date.now() < deadline);
  throw new Error(message, { cause: last });
}

async function pageFor(t, viewport = { width: 1440, height: 1100 }) {
  const context = await browser.newContext({ viewport });
  const page = await context.newPage();
  const errors = [];
  const external = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.route("**/*", (route) => {
    if (new URL(route.request().url()).origin !== origin) {
      external.push(route.request().url());
      return route.abort();
    }
    return route.continue();
  });
  await page.addInitScript(() => {
    window.storageWrites = [];
    window.cspViolations = [];
    document.addEventListener("securitypolicyviolation", (e) =>
      window.cspViolations.push(e.violatedDirective),
    );
    for (const method of ["setItem", "removeItem", "clear"]) {
      Storage.prototype[method] = () => {
        window.storageWrites.push(method);
        throw new Error("Storage must remain unused");
      };
    }
    indexedDB.open = () => {
      window.storageWrites.push("indexedDB");
      throw new Error("IndexedDB must remain unused");
    };
    if (navigator.serviceWorker)
      navigator.serviceWorker.register = () => {
        window.storageWrites.push("serviceWorker");
        throw new Error("Service workers must remain unused");
      };
  });
  await page.goto(origin);
  await page.getByText("Workspace connected", { exact: true }).waitFor();
  t.after(async () => {
    try {
      assert.deepEqual(errors, []);
      assert.deepEqual(external, []);
      assert.deepEqual(await page.evaluate(() => window.cspViolations), []);
      assert.deepEqual(await page.evaluate(() => window.storageWrites), []);
      assert.deepEqual(await context.cookies(), []);
    } finally {
      await context.close();
    }
  });
  return page;
}

const nav = (page, name) =>
  page
    .getByRole("navigation", { name: "Workspace pages" })
    .getByRole("button", { name, exact: true })
    .click();
const button = (page, name) => page.getByRole("button", { name, exact: true });
const idle = (page) =>
  eventually(async () =>
    assert.equal(
      await page.locator("#normal-panel").getAttribute("aria-busy"),
      "false",
    ),
  );
const notice = (page, pattern) =>
  eventually(async () =>
    assert.match(await page.locator("#feedback").innerText(), pattern),
  );
const normal = (page) =>
  page.getByRole("radio", { name: "Normal", exact: true }).check();
const privateMode = (page) =>
  page.getByRole("radio", { name: "Private", exact: true }).check();
async function closeDialog(page) {
  if (await page.getByRole("dialog").count())
    await button(page, "Close").click();
}
async function screenshot(page, name) {
  const directory = new URL("../../.tmp/react-review/", import.meta.url);
  await mkdir(directory, { recursive: true });
  await page.screenshot({
    path: fileURLToPath(new URL(`${name}.png`, directory)),
    fullPage: !(await page.getByRole("dialog").count()),
  });
}
async function importFile(page, namespace, content = fixture) {
  await closeDialog(page);
  await page.getByLabel("Collection name", { exact: true }).fill(namespace);
  await nav(page, "Sources");
  await page.getByLabel("Add dictations", { exact: true }).setInputFiles({
    name: "synthetic.jsonl",
    mimeType: "application/x-ndjson",
    buffer: content,
  });
  await button(page, "Import to collection").click();
  await notice(page, /Saved \d+ new/);
  await idle(page);
}
async function processFixture(page, namespace) {
  await nav(page, "Memory");
  await eventually(async () =>
    assert.equal(await page.locator(".waiting-sources li").count(), 8),
  );
  await button(page, "Process sources").click();
  await idle(page);
  await eventually(
    async () => {
      const response = await fetch(
        `${origin}/processing?namespace=${namespace}`,
        { headers: { "X-Jarvis-Mode": "normal" } },
      );
      assert.equal((await response.json()).counts.succeeded, 8);
    },
    "All eight deterministic processing jobs did not finish",
    20000,
  );
  await button(page, "Refresh memories").click();
  await idle(page);
}
async function hold(page, pattern) {
  let release, reached;
  const gate = new Promise((resolve) => {
    release = resolve;
  });
  const arrived = new Promise((resolve) => {
    reached = resolve;
  });
  await page.route(pattern, async (route) => {
    const response = await route.fetch();
    reached();
    await gate;
    await route.fulfill({ response }).catch(() => {});
  });
  return {
    arrived,
    release: async () => {
      release();
      await page.unroute(pattern, undefined, { behavior: "wait" });
    },
  };
}

test("React shell has local assets, accessible navigation, no personal startup reads or microphone", async (t) => {
  const page = await pageFor(t);
  const calls = [];
  page.on("request", (request) => calls.push(request.url()));
  await page.getByRole("heading", { name: /hey jarvis/ }).waitFor();
  assert.equal(
    await page
      .getByRole("button", { name: /microphone|record audio|speak/i })
      .count(),
    0,
  );
  assert.equal(await page.locator("audio,video").count(), 0);
  for (const name of ["Sources", "Memory", "Usage", "Conversation"])
    await nav(page, name);
  assert.deepEqual(calls, []);
  await page.evaluate(() => document.fonts.ready);
  await screenshot(page, "home-desktop");
  await page.setViewportSize({ width: 390, height: 844 });
  assert.equal(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
    true,
  );
  await screenshot(page, "home-mobile");
});

test("typed note preserves whitespace, Unicode and raw/formatted pairing, without capture-time invention", async (t) => {
  const page = await pageFor(t);
  const namespace = `typed-${randomUUID()}`;
  const raw = "  Ravi might own Atlas\nif Finance approves. नमस्ते ₹ 👋  ";
  const formatted = "Ravi might own Atlas if Finance approves.";
  await page.getByLabel("Collection name").fill(namespace);
  await page.getByRole("tab", { name: "Save a note" }).click();
  await page.getByLabel("Original transcript", { exact: true }).fill(raw);
  await page.getByText("Add a formatted version", { exact: false }).click();
  await page.getByLabel("Formatted transcript").fill(formatted);
  await button(page, "Save note").click();
  await notice(page, /Saved 1 new/);
  await idle(page);
  await button(page, "View source").click();
  assert.equal(await page.locator("#source-list li").count(), 1);
  await page.locator("#source-list button").click();
  await page.getByRole("dialog").waitFor();
  assert.equal(await page.locator("#raw-text").textContent(), raw);
  assert.equal(await page.locator("#formatted-text").textContent(), formatted);
  assert.equal(
    await page.locator("#captured-at").textContent(),
    "Not provided",
  );
  await screenshot(page, "typed-evidence");
  await page.keyboard.press("Escape");
  assert.equal(await page.getByRole("dialog").count(), 0);
});

test("a committed typed-note response lost in transit can be retried without duplicate observation", async (t) => {
  const page = await pageFor(t);
  await page.getByLabel("Collection name").fill(`retry-${randomUUID()}`);
  await page.getByRole("tab", { name: "Save a note" }).click();
  await page
    .getByLabel("Original transcript", { exact: true })
    .fill("Synthetic retry-safe note");
  await page.route("**/sources/import?*", async (route) => {
    await route.fetch();
    await route.abort();
  });
  await button(page, "Save note").click();
  await notice(page, /may have completed/);
  await idle(page);
  await page.unroute("**/sources/import?*");
  await button(page, "Save note").click();
  await notice(page, /Saved 0 new.*1 unchanged/);
  await idle(page);
  assert.equal(
    await page.getByLabel("Original transcript", { exact: true }).inputValue(),
    "",
  );
});

test("imports and reimports exact paired evidence through isolated PostgreSQL", async (t) => {
  const page = await pageFor(t);
  const namespace = `source-${randomUUID()}`;
  await importFile(page, namespace);
  assert.equal(await page.locator("#source-list li").count(), 8);
  await page.getByRole("button", { name: /dict[ _]0008/ }).click();
  await page.getByRole("dialog").waitFor();
  assert.match(
    await page.locator("#raw-text").textContent(),
    /fifteen thousand rupees/,
  );
  assert.match(await page.locator("#formatted-text").textContent(), /₹50,000/);
  await importFile(page, namespace);
  await notice(page, /Saved 0 new.*8 unchanged/);
  await page.getByRole("button", { name: /dict[ _]0007/ }).click();
  await page.getByRole("dialog").waitFor();
  assert.equal(
    await page.locator("#captured-at").textContent(),
    "Not provided",
  );
  assert.match(
    await page.locator("#formatted-text").textContent(),
    /25 September 2026/,
  );
});

test("invalid and conflicting imports fail atomically without echoing driver/input errors", async (t) => {
  const page = await pageFor(t);
  await importFile(page, `conflict-${randomUUID()}`);
  const rows = fixture.toString().trim().split("\n").map(JSON.parse);
  rows[0].raw_transcript = "SYNTHETIC_CONFLICT_DO_NOT_ECHO";
  rows.push({ record_id: "extra", raw_transcript: "Should not be committed" });
  for (const [content, message] of [
    [rows.map(JSON.stringify).join("\n"), /No records.*changed/],
    ["INVALID_SYNTHETIC_CONTENT", /Check the input/],
  ]) {
    await page.getByLabel("Add dictations").setInputFiles({
      name: "invalid.jsonl",
      mimeType: "application/x-ndjson",
      buffer: Buffer.from(content),
    });
    await button(page, "Import to collection").click();
    await notice(page, message);
    await idle(page);
    assert.equal(await page.locator("#source-list li").count(), 8);
    assert.doesNotMatch(
      await page.locator("body").innerText(),
      /SYNTHETIC_CONFLICT_DO_NOT_ECHO|INVALID_SYNTHETIC_CONTENT/,
    );
  }
});

test("source markup remains literal text with no executable element or outside request", async (t) => {
  const page = await pageFor(t);
  const markup =
    '<img src="/unexpected-image" onerror="window.xss=1"><script>window.xss=2</script> ₹ नमस्ते';
  await importFile(
    page,
    `markup-${randomUUID()}`,
    Buffer.from(
      JSON.stringify({
        record_id: "markup",
        raw_transcript: markup,
        formatted_text: markup,
        metadata: { note: markup },
      }),
    ),
  );
  await page.getByRole("button", { name: /markup/ }).click();
  await page.getByRole("dialog").waitFor();
  assert.equal(await page.locator("#raw-text").textContent(), markup);
  assert.equal(
    await page.locator("#raw-text img,#formatted-text script").count(),
    0,
  );
  assert.equal(await page.evaluate(() => window.xss), undefined);
});

test("large file is rejected before reads; pagination reaches every original", async (t) => {
  const page = await pageFor(t);
  await nav(page, "Sources");
  const calls = [];
  page.on("request", (request) => {
    if (request.url().includes("/sources")) calls.push(request.url());
  });
  await page.getByLabel("Add dictations").setInputFiles({
    name: "large.jsonl",
    mimeType: "application/x-ndjson",
    buffer: Buffer.alloc(1024 * 1024 + 1, "x"),
  });
  await button(page, "Import to collection").click();
  await notice(page, /no larger than 1 MB/);
  assert.deepEqual(calls, []);
  const rows = Array.from({ length: 55 }, (_, i) =>
    JSON.stringify({
      record_id: `record_${i}`,
      raw_transcript: `Synthetic pagination ${i}`,
    }),
  );
  await importFile(page, `pages-${randomUUID()}`, Buffer.from(rows.join("\n")));
  assert.equal(await page.locator("#source-list li").count(), 50);
  await button(page, "Load more sources").click();
  await idle(page);
  assert.equal(await page.locator("#source-list li").count(), 55);
  assert.equal(
    new Set(await page.locator("#source-list strong").allTextContents()).size,
    55,
  );
  assert.equal(await button(page, "Load more sources").count(), 0);
});

test("search keeps conflicting variants and distinguishes undated, absent evidence and outage", async (t) => {
  const page = await pageFor(t, { width: 390, height: 844 });
  await importFile(page, `search-${randomUUID()}`);
  await page
    .getByLabel("Search saved evidence", { exact: true })
    .fill("spending limit");
  await button(page, "Search").click();
  await idle(page);
  assert.match(
    await page.locator("#search-results").innerText(),
    /fifteen thousand/,
  );
  assert.match(await page.locator("#search-results").innerText(), /50,000/);
  assert.equal(await page.locator("#search-results article").count(), 1);
  await button(page, "Inspect original").click();
  await page.getByRole("dialog").waitFor();
  await closeDialog(page);
  await page.getByText("Search options", { exact: true }).click();
  await page.locator("#search-from").fill("2030-01-01");
  await page.getByLabel("Search saved evidence", { exact: true }).fill("Orion");
  await button(page, "Search").click();
  await idle(page);
  assert.match(
    await page.locator("#search-results").innerText(),
    /Captured: Not provided/,
  );
  await page.locator("#search-undated").uncheck();
  await button(page, "Search").click();
  await idle(page);
  assert.match(
    await page.locator("#search-state").innerText(),
    /No matching evidence/,
  );
  await page.route("**/search", (route) => route.abort());
  await button(page, "Search").click();
  await idle(page);
  assert.match(
    await page.locator("#search-state").innerText(),
    /Search could not finish/,
  );
  assert.equal(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
    true,
  );
  await screenshot(page, "sources-mobile");
});

test("learned memories retain conditional meaning, unknown times and superseded history", async (t) => {
  const page = await pageFor(t);
  const namespace = `memory-${randomUUID()}`;
  await importFile(page, namespace);
  await processFixture(page, namespace);
  assert.equal(await page.locator("#memory-list li").count(), 11);
  await page
    .getByRole("button", { name: /Atlas · launch date: 2026-09-21/ })
    .click();
  await idle(page);
  assert.match(await page.locator("#memory-history").innerText(), /2026-09-18/);
  assert.match(
    await page.locator("#memory-history").innerText(),
    /superseded/i,
  );
  await eventually(async () =>
    assert.equal(
      await page
        .locator("#memory-history")
        .evaluate(
          (element) =>
            document.activeElement === element &&
            element.getBoundingClientRect().top >= 0 &&
            element.getBoundingClientRect().top < innerHeight,
        ),
      true,
    ),
  );
  const owner = page
    .locator("#memory-list li")
    .filter({ hasText: /budget owner: Ravi/ });
  assert.match(await owner.innerText(), /tentative.*conditional/s);
  assert.match(await owner.innerText(), /Only if: Finance signs off/);
  await owner.getByRole("button").click();
  await idle(page);
  assert.match(
    await page.locator("#memory-history").innerText(),
    /Applies from: Unknown/,
  );
  await screenshot(page, "memory-desktop");
  await nav(page, "Sources");
  await page.getByText("Search options", { exact: true }).click();
  await page.getByLabel("Include learned memories", { exact: true }).check();
  await page.getByLabel("Search saved evidence", { exact: true }).fill("Ravi");
  await button(page, "Search").click();
  await idle(page);
  assert.match(
    await page.locator("#search-results").innerText(),
    /Only if: Finance signs off/,
  );
});

test("Ask cites original evidence, diagnoses feedback and permits only one explicit retry", async (t) => {
  const page = await pageFor(t);
  await importFile(page, `ask-${randomUUID()}`);
  await nav(page, "Conversation");
  await page.getByRole("button", { name: /Ask with context/ }).click();
  await idle(page);
  assert.match(
    await page.getByLabel("Ask a question").inputValue(),
    /Atlas launch/,
  );
  await page.getByLabel("Ask a question").press("Enter");
  assert.equal(await page.getByLabel("Ask a question").inputValue(), "");
  await idle(page);
  assert.match(
    await page.locator("#ask-result").innerText(),
    /Synthetic contract answer/,
  );
  await page.locator(".citations summary").first().click();
  await button(page, "Inspect cited source").first().click();
  await page.getByRole("dialog").waitFor();
  await closeDialog(page);
  await page
    .getByText("Something off? Review this answer", { exact: true })
    .click();
  await button(page, "Review feedback").click();
  await notice(page, /Which source/);
  await idle(page);
  await page.getByLabel("What needs attention?").selectOption("generation");
  await button(page, "Review feedback").click();
  await notice(page, /One new answer/);
  await idle(page);
  await button(page, "Review feedback").click();
  await idle(page);
  assert.match(
    await page.locator("#feedback").innerText(),
    /retry|already|limit/i,
  );
  await screenshot(page, "conversation-desktop");
  await privateMode(page);
  assert.equal(await page.locator("#ask-result").count(), 0);
  await normal(page);
  assert.equal(await page.getByLabel("Ask a question").inputValue(), "");
});

test("Ask failure is not an unknown answer, and retry is explicit", async (t) => {
  const page = await pageFor(t);
  await page.getByLabel("Ask a question").fill("Atlas launch");
  await page.route("**/ask", (route) => route.abort());
  await button(page, "Ask").click();
  await idle(page);
  assert.match(
    await page.locator("#ask-result").innerText(),
    /The answer could not finish/,
  );
  assert.match(
    await page.locator("#ask-result").innerText(),
    /service failure does not establish/,
  );
  assert.equal(await button(page, "Try question again").count(), 1);
  assert.equal(await page.locator(".activity").count(), 0);
});

test("Private unmounts Normal content and clears an unsent direct draft without backfill", async (t) => {
  const page = await pageFor(t);
  await importFile(page, `private-${randomUUID()}`);
  await page.getByLabel("Add dictations").setInputFiles({
    name: "pending.jsonl",
    mimeType: "application/x-ndjson",
    buffer: fixture,
  });
  await nav(page, "Conversation");
  await page.getByLabel("Ask a question").fill("SYNTHETIC_NORMAL_DRAFT");
  const calls = [];
  page.on("request", (request) => calls.push(request.url()));
  await privateMode(page);
  assert.equal(await page.locator("#normal-panel").count(), 0);
  assert.doesNotMatch(
    await page.locator("body").textContent(),
    /SYNTHETIC_NORMAL_DRAFT|dict[ _]0008/,
  );
  await page.getByLabel("Direct question").fill("SYNTHETIC_PRIVATE_DRAFT");
  await screenshot(page, "private-desktop");
  await normal(page);
  assert.doesNotMatch(
    await page.locator("body").textContent(),
    /SYNTHETIC_PRIVATE_DRAFT/,
  );
  assert.equal(await page.locator("#import-file").inputValue(), "");
  assert.equal(
    await page.getByLabel("Collection name").inputValue(),
    "my-notes",
  );
  assert.equal(await page.locator("#source-list li").count(), 0);
  assert.deepEqual(calls, []);
});

test("Private direct sends with Enter and keeps the answer out of Normal", async (t) => {
  const page = await pageFor(t);
  const calls = [];
  page.on("request", (request) => calls.push(new URL(request.url()).pathname));
  await privateMode(page);
  await page
    .getByLabel("Direct question")
    .fill("A fictional context-free question");
  await page.getByLabel("Direct question").press("Enter");
  await page
    .getByText("Synthetic context-free answer.", { exact: true })
    .waitFor();
  assert.deepEqual(
    calls.filter((path) => path === "/private/ask"),
    ["/private/ask"],
  );
  assert.match(
    await page.locator("#private-panel").innerText(),
    /20 in \/ 8 out/,
  );
  await normal(page);
  assert.equal(await page.locator("#private-panel").count(), 0);
  await privateMode(page);
  assert.doesNotMatch(
    await page.locator("#private-panel").innerText(),
    /Synthetic context-free answer/,
  );
});

for (const target of [
  "source",
  "search",
  "memory",
  "ask",
  "capture",
  "learning",
  "usage",
]) {
  test(`Private cancels pending ${target}, ignores the late result and prevents follow-up reads`, async (t) => {
    const page = await pageFor(t);
    await importFile(page, `late-${target}-${randomUUID()}`);
    const patterns = {
      source: "**/sources/*",
      search: "**/search",
      memory: "**/memories?*",
      ask: "**/ask",
      capture: "**/conversation/messages",
      learning: "**/conversation/messages/*/learn",
      usage: "**/usage",
    };
    const pending = await hold(page, patterns[target]);
    if (target === "source")
      await page.getByRole("button", { name: /dict[ _]0008/ }).click();
    if (target === "search") {
      await page
        .getByLabel("Search saved evidence", { exact: true })
        .fill("Atlas");
      await button(page, "Search").click();
    }
    if (target === "memory") {
      await nav(page, "Memory");
      await button(page, "Refresh memories").click();
    }
    if (["ask", "capture", "learning"].includes(target)) {
      await nav(page, "Conversation");
      await page.getByLabel("Ask a question").fill("Atlas launch");
      await button(page, "Ask").click();
    }
    if (target === "usage") {
      await nav(page, "Usage");
      await button(page, "Refresh usage").click();
    }
    await pending.arrived;
    assert.ok(await page.locator(".activity").count());
    if (target === "ask") {
      await screenshot(page, "answer-pending");
      await page.emulateMedia({ reducedMotion: "reduce" });
      assert.equal(
        await page
          .locator(".activity-orbit svg")
          .evaluate((element) => getComputedStyle(element).animationName),
        "none",
      );
    }
    await privateMode(page);
    const calls = [];
    page.on("request", (request) => calls.push(request.url()));
    await normal(page);
    await pending.release();
    await page.waitForTimeout(80);
    assert.equal(
      await page
        .locator(
          "#source-list li,#memory-list li,#ask-result,#usage-results,#evidence",
        )
        .count(),
      0,
    );
    assert.equal(await page.locator("#search-results").textContent(), "");
    assert.equal(await page.locator(".activity").count(), 0);
    assert.deepEqual(calls, []);
  });
}

test("unknown backend errors stay bounded; loading a collection is not mistaken for empty on failure", async (t) => {
  const page = await pageFor(t);
  await page.route("**/sources?*", (route) =>
    route.fulfill({
      status: 503,
      json: { reason: "DATABASE_SECRET_SYNTHETIC_FAILURE" },
    }),
  );
  await button(page, "Open").click();
  await idle(page);
  assert.match(await page.locator("#feedback").innerText(), /could not finish/);
  assert.doesNotMatch(
    await page.locator("body").innerText(),
    /DATABASE_SECRET_SYNTHETIC_FAILURE|Room for your first thought/,
  );
});

test("Normal Ask automatically saves, learns, skips repeats and preserves a changed fact", async (t) => {
  const page = await pageFor(t);
  const namespace = `chat-${randomUUID()}`;
  await page.getByLabel("Collection name", { exact: true }).fill(namespace);
  const rows = fixture
    .toString()
    .trim()
    .split("\n")
    .map((line) => JSON.parse(line));
  for (const [text, expected] of [
    [rows[0].raw_transcript, /1 memory change/],
    [rows[0].raw_transcript, /Already known/],
    [rows[2].raw_transcript, /2 memory change/],
    ["Who approved the Atlas launch?", /Nothing new to remember/],
  ]) {
    await page.getByLabel("Ask a question").fill(text);
    await page.getByLabel("Ask a question").press("Enter");
    await idle(page);
    assert.match(
      await page.locator(".message-learning").last().innerText(),
      expected,
    );
  }
  const headers = { "X-Jarvis-Mode": "normal" };
  const sources = await fetch(`${origin}/sources?namespace=${namespace}`, {
    headers,
  }).then((r) => r.json());
  const memories = await fetch(`${origin}/memories?namespace=${namespace}`, {
    headers,
  }).then((r) => r.json());
  assert.equal(sources.observations.length, 3);
  assert.equal(memories.memories.length, 2);
  const launch = memories.memories.find(
    (m) => m.content.predicate === "launch_date",
  );
  assert.equal(launch.content.value.value, "2026-09-21");
  assert.equal(launch.revision, 2);
  await screenshot(page, "conversation-learning-desktop");
  await page.setViewportSize({ width: 390, height: 844 });
  assert.ok(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  );
  await screenshot(page, "conversation-learning-mobile");
});

test("Answer retry reuses the completed assessment without saving a pure question", async (t) => {
  const page = await pageFor(t);
  const namespace = `retry-chat-${randomUUID()}`;
  await page.getByLabel("Collection name", { exact: true }).fill(namespace);
  await page.getByLabel("Ask a question").fill("What is Atlas?");
  await page.route("**/ask", (route) => route.abort());
  await button(page, "Ask").click();
  await idle(page);
  assert.match(
    await page.locator(".message-learning").innerText(),
    /No source or memory saved/,
  );
  await page.unroute("**/ask");
  await button(page, "Try question again").click();
  await idle(page);
  assert.equal(await page.locator(".conversation-turn").count(), 1);
  await page.locator(".request-metrics > summary").click();
  const callRows = page.getByRole("table", { name: "Model calls by phase" });
  assert.equal(
    await callRows.getByRole("row").filter({ hasText: "Assessment" }).count(),
    1,
  );
  assert.equal(
    await callRows.getByRole("row").filter({ hasText: "Learning" }).count(),
    0,
  );
  const data = await fetch(`${origin}/sources?namespace=${namespace}`, {
    headers: { "X-Jarvis-Mode": "normal" },
  }).then((r) => r.json());
  assert.equal(data.observations.length, 0);
});

test("sample import is idempotent; usage reports measured payloads, timings and unknown billing", async (t) => {
  const page = await pageFor(t);
  await page.getByLabel("Collection name").fill(`sample-${randomUUID()}`);
  await nav(page, "Sources");
  await button(page, "Try the sample").click();
  await notice(page, /Saved 8 new/);
  await idle(page);
  await button(page, "Try the sample").click();
  await notice(page, /Saved 0 new.*8 unchanged/);
  await idle(page);
  await nav(page, "Usage");
  await button(page, "Refresh usage").click();
  await idle(page);
  assert.match(
    await page.locator("#usage-results").innerText(),
    /Original sources/,
  );
  assert.match(
    await page.locator("#usage-results").innerText(),
    /Cost: unmeasured/,
  );
  assert.match(
    await page.locator("#operation-timing").innerText(),
    /usage_snapshot;dur=/,
  );
  await screenshot(page, "usage-desktop");
  await page.setViewportSize({ width: 390, height: 844 });
  assert.equal(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
    true,
  );
  await screenshot(page, "usage-mobile");
});

test("mobile keyboard, dialog focus and back navigation do not restore personal text", async (t) => {
  const page = await pageFor(t, { width: 390, height: 844 });
  await page.getByLabel("Collection name").fill(`keyboard-${randomUUID()}`);
  await page.getByLabel("Collection name").press("Enter");
  await notice(page, /Collection opened/);
  await idle(page);
  await importFile(page, `mobile-${randomUUID()}`);
  await page.getByRole("button", { name: /dict[ _]0008/ }).click();
  await page.getByRole("dialog").waitFor();
  await page.keyboard.press("Tab");
  assert.equal(
    await page.evaluate(
      () => !!document.activeElement.closest('[role="dialog"]'),
    ),
    true,
  );
  assert.equal(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
    true,
  );
  await page.keyboard.press("Escape");
  assert.equal(await page.getByRole("dialog").count(), 0);
  await page.goto("about:blank");
  await page.goBack();
  await page.locator("#workspace").waitFor();
  assert.equal(await page.locator("#source-list li,#evidence").count(), 0);
});

test("Private direct draft is cleared before browser-history restoration", async (t) => {
  const page = await pageFor(t);
  await privateMode(page);
  await page
    .getByLabel("Direct question")
    .fill("SYNTHETIC_PRIVATE_HISTORY_SENTINEL");
  // Also exercise the persisted pageshow branch deterministically; real history follows.
  await page.evaluate(() =>
    window.dispatchEvent(
      new PageTransitionEvent("pagehide", { persisted: true }),
    ),
  );
  assert.equal(await page.getByLabel("Direct question").inputValue(), "");
  await page
    .getByLabel("Direct question")
    .fill("SYNTHETIC_PRIVATE_HISTORY_SENTINEL");
  await page.goto("about:blank");
  await page.goBack();
  await page.locator("#workspace").waitFor();
  assert.doesNotMatch(
    await page.locator("body").textContent(),
    /SYNTHETIC_PRIVATE_HISTORY_SENTINEL/,
  );
  if (await page.locator("#private-draft").count())
    assert.equal(await page.locator("#private-draft").inputValue(), "");
});

test("Normal greeting stays transient and evidence choices stay collapsed", async (t) => {
  const page = await pageFor(t);
  const calls = [];
  page.on("request", (request) => {
    if (!new URL(request.url()).pathname.startsWith("/assets/"))
      calls.push(request.url());
  });
  assert.equal(await page.getByLabel("Answer evidence").isVisible(), false);
  await page.getByLabel("Ask a question").fill("hello jarvis what are you doing");
  await button(page, "Ask").click();
  await page
    .getByText("Hello! I help you find the details in your notes.", {
      exact: true,
    })
    .waitFor();
  await idle(page);
  assert.ok(calls.some((url) => url.endsWith("/conversation/messages")));
  assert.match(
    await page.locator(".message-learning").innerText(),
    /Nothing new to remember/,
  );
  assert.equal(
    calls.some((url) => url.endsWith("/learn")),
    false,
  );
  await page.getByText("Context: automatic", { exact: true }).click();
  await page.getByLabel("Answer evidence").selectOption("sources_and_memories");
  assert.match(
    await page.locator(".context-options").innerText(),
    /General knowledge is labelled separately/,
  );
  await privateMode(page);
  assert.equal(
    await page
      .getByText("Hello! I help you find the details in your notes.", {
        exact: true,
      })
      .count(),
    0,
  );
});

test("automatic date uses the clock and makes its provenance visible", async (t) => {
  const page = await pageFor(t);
  await page.getByLabel("Ask a question").fill("what is the todays date ?");
  await page.getByLabel("Ask a question").press("Enter");
  await page.getByText("From the application clock", { exact: true }).waitFor();
  const answer = await page.locator(".reply").innerText();
  assert.match(answer, /Today is/);
  assert.match(answer, /no answer model call/);
  await page.locator(".request-metrics > summary").click();
  assert.match(
    await page.locator(".request-metrics").innerText(),
    /1 recorded/,
  );
  assert.match(
    await page.getByRole("table", { name: "Model calls by phase" }).innerText(),
    /Assessment/,
  );
  assert.equal(await page.getByLabel("Ask a question").inputValue(), "");
});

test("540-note import, setup information and 30 preselected showcase questions use real APIs", async (t) => {
  const page = await pageFor(t);
  await page.getByLabel("Collection name").fill(`corpus-${randomUUID()}`);
  await nav(page, "Sources");
  await page
    .getByText("Explore the complete 540-note fictional corpus", {
      exact: true,
    })
    .click();
  await button(page, "Import 540 fictional notes").click();
  await notice(page, /Saved 540 new/);
  await idle(page);
  await button(page, "Import 540 fictional notes").click();
  await notice(page, /Saved 0 new.*540 unchanged/);
  await idle(page);
  await nav(page, "Conversation");
  await page
    .getByText("Model setup and 30 showcase questions", { exact: true })
    .click();
  await button(page, "Check model setup").click();
  await idle(page);
  assert.match(
    await page.locator(".conversation-page .setup-card").innerText(),
    /deterministic-answer-double/,
  );
  await button(page, "Browse 30 showcase cases").click();
  await idle(page);
  assert.equal(await page.locator(".showcase-picker option").count(), 31);
  await page.locator(".showcase-picker select").selectOption({ index: 1 });
  assert.match(await page.getByLabel("Ask a question").inputValue(), /Juniper/);
  await page.setViewportSize({ width: 390, height: 844 });
  assert.equal(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
    true,
  );
  await screenshot(page, "showcase-mobile");
});

// Last: Forget intentionally excludes known sample copies across this isolated owner.
test("mobile Correct, world change and Forget review effects and clear revoked cached results", async (t) => {
  const page = await pageFor(t, { width: 390, height: 844 });
  const namespace = `controls-${randomUUID()}`;
  await importFile(page, namespace);
  await processFixture(page, namespace);
  const launch = () =>
    page
      .locator("#memory-list li")
      .filter({ hasText: /launch date/ })
      .first();
  for (const [name, date] of [
    ["Correct", "2026-09-23"],
    ["Record a world change", "2026-09-25"],
  ]) {
    await launch().getByRole("button").click();
    await idle(page);
    await page
      .locator("#memory-history")
      .getByRole("button", { name, exact: true })
      .click();
    await page
      .getByLabel("Your exact statement")
      .fill(`The Atlas launch plan is ${date}.`);
    await page.getByLabel("New value", { exact: true }).fill(date);
    await button(page, "Review impact").click();
    await idle(page);
    assert.match(
      await page.locator("#control-preview").innerText(),
      new RegExp(date),
    );
    // Editing after preview must invalidate the confirmation.
    await page.getByLabel("New value", { exact: true }).fill(date + "x");
    assert.equal(await button(page, "Confirm change").count(), 0);
    await page.getByLabel("New value", { exact: true }).fill(date);
    await button(page, "Review impact").click();
    await idle(page);
    await button(page, "Confirm change").click();
    await notice(page, /Change saved/);
    await idle(page);
    assert.match(await launch().innerText(), new RegExp(date));
  }
  await nav(page, "Sources");
  await page
    .getByLabel("Search saved evidence", { exact: true })
    .fill("legal review launch");
  await button(page, "Search").click();
  await idle(page);
  assert.match(await page.locator("#search-results").innerText(), /2026-09-25/);
  await nav(page, "Memory");
  await launch().getByRole("button").click();
  await idle(page);
  await page
    .locator("#memory-history")
    .getByRole("button", { name: "Forget", exact: true })
    .click();
  await button(page, "Review impact").click();
  await idle(page);
  assert.match(await page.getByRole("dialog").innerText(), /known copies/);
  assert.equal(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
    true,
  );
  await screenshot(page, "forget-mobile");
  await page.route("**/sources?*", (route) => route.abort());
  await button(page, "Confirm Forget").click();
  await notice(page, /Forgotten for future use/);
  await idle(page);
  assert.equal(await launch().count(), 0);
  assert.equal(await page.locator("#search-results").textContent(), "");
  assert.equal(await page.locator("#source-list li").count(), 0);
  await page.unroute("**/sources?*");
  await nav(page, "Sources");
  await button(page, "Open collection").click();
  await idle(page);
  await page.getByRole("button", { name: /dict[ _]0003/ }).click();
  await page.getByRole("dialog").waitFor();
  assert.match(
    await page.locator("#raw-text").textContent(),
    /september twenty first/,
  );
  await importFile(page, `renamed-${randomUUID()}`);
  await page
    .getByLabel("Search saved evidence", { exact: true })
    .fill("eighteenth twenty first launch");
  await button(page, "Search").click();
  await idle(page);
  assert.doesNotMatch(
    await page.locator("#search-results").innerText(),
    /dict[ _]0001|dict[ _]0003/,
  );
});

test("workflow diagram is navigable and Private clears its loaded evidence", async (t) => {
  const page = await pageFor(t, { width: 390, height: 844 });
  await nav(page, "Workflow & evidence");
  assert.equal(await page.locator(".flow-nodes button").count(), 12);
  await page.locator(".flow-nodes button").nth(3).click();
  assert.match(
    await page.locator(".flow-detail").innerText(),
    /Keep the original first/,
  );
  await button(page, "Lightning smoke").click();
  await idle(page);
  assert.ok(await page.locator(".evidence-json").innerText());
  assert.equal(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
    true,
  );
  await privateMode(page);
  assert.equal(await page.locator(".evidence-json").count(), 0);
  await normal(page);
  await nav(page, "Workflow & evidence");
  assert.equal(await page.locator(".evidence-json").count(), 0);
});

test("general questions stay in the chat without source capture or learning calls", async (t) => {
  const page = await pageFor(t);
  const namespace = `public-${randomUUID()}`;
  await page.getByLabel("Collection name", { exact: true }).fill(namespace);
  const requests = [];
  page.on("request", (request) =>
    requests.push(new URL(request.url()).pathname),
  );
  await page
    .getByLabel("Ask a question")
    .fill(
      "what is the capital of USA ? I just want to know the city and in which state it is present",
    );
  await button(page, "Ask").click();
  await idle(page);
  assert.match(
    await page.locator(".message-learning").innerText(),
    /Only in this chat/,
  );
  assert.equal(
    await page.getByText("View saved message", { exact: true }).count(),
    0,
  );
  assert.equal(requests.filter((path) => path.endsWith("/learn")).length, 0);
  assert.match(
    await page.locator(".reply").innerText(),
    /Sent to answer model: 0 eligible notes and 0 learned memories/,
  );
  const data = await fetch(`${origin}/sources?namespace=${namespace}`, {
    headers: { "X-Jarvis-Mode": "normal" },
  }).then((response) => response.json());
  assert.equal(data.observations.length, 0);
});

test("query exposes evidence selection and actual model-call metrics", async (t) => {
  const page = await pageFor(t);
  await importFile(page, `metrics-${randomUUID()}`);
  await nav(page, "Conversation");
  await page.locator(".context-options > summary").click();
  await page
    .getByLabel("Answer evidence", { exact: true })
    .selectOption("sources_and_memories");
  await page
    .getByLabel("Ask a question", { exact: true })
    .fill(
      "For the Atlas project, I prefer PostgreSQL. What is its latest recorded launch date?",
    );
  await button(page, "Ask").click();
  await idle(page);
  await page.locator(".request-metrics > summary").click();
  assert.match(
    await page.locator(".request-metrics").innerText(),
    /Browser total/,
  );
  assert.match(
    await page.getByRole("table", { name: "Where time went" }).innerText(),
    /Retrieve answer context/,
  );
  const calls = page.getByRole("table", {
    name: "Model calls by phase",
  });
  assert.match(
    await calls.getByRole("row").filter({ hasText: "Learning" }).innerText(),
    /succeeded.*100.*100/s,
  );
  assert.match(await calls.innerText(), /Answer/);
  assert.match(await calls.innerText(), /Assessment/);
  assert.match(await calls.innerText(), /Input tokens.*Output tokens/s);
  assert.match(
    await page.locator(".request-metrics").innerText(),
    /not additive portions/,
  );
  assert.equal(
    await page.locator(".metrics-diagnostics pre").isVisible(),
    false,
  );
  await page.locator(".metrics-diagnostics > summary").click();
  assert.match(
    await page.locator(".metrics-diagnostics pre").innerText(),
    /dur=/,
  );
  await page.setViewportSize({ width: 390, height: 844 });
  assert.equal(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
    true,
  );
});

test("failed answers keep learning metrics and label unavailable answer usage", async (t) => {
  const page = await pageFor(t);
  await page
    .getByLabel("Collection name")
    .fill(`failed-metrics-${randomUUID()}`);
  await page.route("**/ask", (route) =>
    route.fulfill({
      status: 503,
      contentType: "application/json",
      headers: { "Server-Timing": "answer_context;dur=12.5, request;dur=50" },
      body: JSON.stringify({ reason: "provider_failed" }),
    }),
  );
  await page
    .getByLabel("Ask a question")
    .fill(
      "For the Atlas project, I prefer PostgreSQL. What is its recorded launch date?",
    );
  await button(page, "Ask").click();
  await idle(page);
  await page
    .getByText("The answer could not finish", { exact: true })
    .waitFor();
  await page.locator(".request-metrics > summary").click();
  const metrics = await page.locator(".request-metrics").innerText();
  assert.match(metrics, /Latest submission failed/);
  assert.match(metrics, /model usage is unknown here, not zero/);
  assert.match(metrics, /Learning/);
  assert.match(
    await page.getByRole("table", { name: "Where time went" }).innerText(),
    /Retrieve answer context.*12.5 ms/s,
  );
});

test("failed assessment pauses saving and answering; explicit retry polls the same receipt", async (t) => {
  const page = await pageFor(t);
  const assessmentId = randomUUID();
  const captureBodies = [];
  const answerBodies = [];
  const failedCall = {
    id: randomUUID(),
    model: "synthetic-assessor",
    status: "failed",
    input_tokens: null,
    output_tokens: null,
    elapsed_ms: 1100,
    error_code: "provider_response_invalid",
    reserved_tokens: 2048,
  };
  const completedCall = {
    ...failedCall,
    id: randomUUID(),
    status: "succeeded",
    input_tokens: 100,
    output_tokens: 30,
    elapsed_ms: 900,
    error_code: null,
  };
  await page.route("**/conversation/messages", (route) => {
    captureBodies.push(route.request().postDataJSON());
    const status =
      captureBodies.length === 1
        ? "failed"
        : captureBodies.length === 2
          ? "running"
          : "ready";
    return route.fulfill({
      status: 200,
      headers: {
        "Server-Timing": "turn_assessment;dur=1100, request;dur=1200",
      },
      json: {
        assessment_id: assessmentId,
        assessment: {
          assessment_id: assessmentId,
          status,
          decision:
            status === "ready"
              ? {
                  retention: "skip",
                  route: "general",
                  reason: "general_request",
                  memory_excerpts: [],
                }
              : null,
          calls:
            status === "ready" ? [failedCall, completedCall] : [failedCall],
          error_code: status === "failed" ? "provider_response_invalid" : null,
        },
        source_id: null,
        status: status === "ready" ? "not_saved" : status,
        decision: status === "ready" ? "no_memory" : null,
        revision_ids: [],
        error_code: status === "failed" ? "provider_response_invalid" : null,
        attempts: 0,
        calls: [],
      },
    });
  });
  await page.route("**/ask", (route) => {
    answerBodies.push(route.request().postDataJSON());
    return route.fulfill({
      json: {
        status: "general",
        text: "Synthetic general answer.",
        citations: [],
        sources: [],
        representation: "auto",
        call_ids: [],
        evidence_bytes: 0,
        model: null,
      },
    });
  });
  await page.getByLabel("Ask a question").fill("Tell me a joke.");
  await button(page, "Ask").click();
  await idle(page);
  assert.equal(answerBodies.length, 0);
  assert.match(
    await page.locator(".message-learning-warning").innerText(),
    /No message was saved/,
  );
  assert.equal(await page.locator(".reply.error-card").count(), 0);
  await page.locator(".request-metrics > summary").click();
  assert.match(
    await page.getByRole("table", { name: "Model calls by phase" }).innerText(),
    /Assessment.*failed.*Unknown/s,
  );
  await button(page, "Retry memory check").click();
  await idle(page);
  assert.equal(captureBodies.length, 3);
  assert.deepEqual(
    captureBodies.map((body) => body.retry_failed),
    [false, true, false],
  );
  assert.equal(new Set(captureBodies.map((body) => body.message_id)).size, 1);
  assert.equal(
    new Set(captureBodies.map((body) => body.conversation_id)).size,
    1,
  );
  assert.equal(answerBodies.length, 1);
  assert.equal(answerBodies[0].assessment_id, assessmentId);
  assert.match(
    await page.locator(".message-learning").innerText(),
    /No source or memory saved/,
  );
  assert.equal(await page.locator(".message-learning-warning").count(), 0);
});

test("failed answer call metrics retain unknown usage without turning it into zero", async (t) => {
  const page = await pageFor(t);
  await page
    .getByLabel("Collection name")
    .fill(`known-failure-${randomUUID()}`);
  const callId = randomUUID();
  await page.route("**/ask", (route) =>
    route.fulfill({
      status: 503,
      json: {
        status: "error",
        reason: "provider_failed",
        metrics: {
          calls: [
            {
              id: callId,
              model: "synthetic-answer",
              status: "failed",
              input_tokens: null,
              output_tokens: null,
              elapsed_ms: 1250,
              error_code: "provider_failed",
              reserved_tokens: 4096,
            },
          ],
        },
      },
    }),
  );
  await page
    .getByLabel("Ask a question")
    .fill(
      "For the Atlas project, I prefer PostgreSQL. What is its recorded launch date?",
    );
  await button(page, "Ask").click();
  await idle(page);
  await page.locator(".request-metrics > summary").click();
  const calls = page.getByRole("table", { name: "Model calls by phase" });
  assert.match(
    await calls.getByRole("row").filter({ hasText: "Answer" }).innerText(),
    /failed.*1.25 s.*Unknown.*Unknown/s,
  );
  assert.match(
    await page.locator(".metrics-overview").innerText(),
    /\+ unknown/,
  );
  await page.locator(".metrics-diagnostics > summary").click();
  assert.match(
    await page.locator(".metrics-diagnostics").innerText(),
    new RegExp(callId),
  );
  assert.match(
    await page.locator(".metrics-diagnostics").innerText(),
    /4,096 tokens; not measured usage/,
  );
});
