// Synthetic UI acceptance against compose.test.yaml's isolated PostgreSQL backend.
import { after, before, test } from "node:test";
import assert from "node:assert/strict";
import { readFile, mkdir } from "node:fs/promises";
import { randomUUID } from "node:crypto";
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

async function eventually(check, message = "Expected UI state did not arrive") {
  const deadline = Date.now() + 8000;
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
      assert.deepEqual(await page.evaluate(() => window.storageWrites), []);
      assert.deepEqual(await context.cookies(), []);
    } finally {
      await context.close();
    }
  });
  return page;
}

async function importFile(page, namespace, content = fixture) {
  await page.getByLabel("Collection name", { exact: true }).fill(namespace);
  await page.getByLabel("Add dictations", { exact: true }).setInputFiles({
    name: "synthetic.jsonl",
    mimeType: "application/x-ndjson",
    buffer: content,
  });
  await page.getByRole("button", { name: "Import to collection" }).click();
  await eventually(async () =>
    assert.match(await page.locator("#feedback").innerText(), /Saved \d+ new/),
  );
  await eventually(async () =>
    assert.equal(
      await page.locator("#normal-panel").getAttribute("aria-busy"),
      "false",
    ),
  );
}

test("S08 searches original pairs without a model and clears search on Private", async (t) => {
  const page = await pageFor(t);
  await importFile(page, `search-${randomUUID()}`);
  const requests = [];
  page.on("request", (request) => {
    if (request.url().endsWith("/search")) requests.push(request);
  });
  await page
    .getByLabel("Search saved evidence", { exact: true })
    .fill("spending limit");
  await page.getByRole("button", { name: "Search", exact: true }).click();
  await eventually(async () =>
    assert.match(
      await page.locator("#search-results").innerText(),
      /fifteen thousand/,
    ),
  );
  assert.match(await page.locator("#search-results").innerText(), /50,000/);
  assert.equal(await page.locator("#search-results article").count(), 1);
  assert.equal(requests[0].method(), "POST");
  assert.equal(new URL(requests[0].url()).search, "");
  if (process.env.JARVIS_UI_SCREENSHOTS === "1") {
    const directory = new URL("../../.tmp/ui-review/", import.meta.url);
    await mkdir(directory, { recursive: true });
    await page.locator('[aria-labelledby="search-title"]').screenshot({
      path: new URL("s08-search.png", directory).pathname.replace(
        /^\/(\w:)/,
        "$1",
      ),
    });
  }
  await page
    .getByRole("button", { name: "Inspect original", exact: true })
    .click();
  await eventually(async () =>
    assert.match(
      await page.locator("#raw-text").innerText(),
      /fifteen thousand/,
    ),
  );
  await page.getByRole("radio", { name: "Private", exact: true }).check();
  assert.equal(await page.locator("#search-results").innerText(), "");
  assert.equal(await page.locator("#search-query").inputValue(), "");
  assert.equal(requests.length, 1);
  await page.getByRole("radio", { name: "Normal", exact: true }).check();
  assert.equal(await page.locator("#search-results").innerText(), "");
});

test("S08 distinguishes search outage from no matches and ignores late results", async (t) => {
  const page = await pageFor(t, { width: 390, height: 844 });
  await importFile(page, `search-failure-${randomUUID()}`);
  await page.getByText("Search options", { exact: true }).click();
  await page.locator("#search-from").fill("2030-01-01");
  await page.getByLabel("Search saved evidence", { exact: true }).fill("Orion");
  await page.getByRole("button", { name: "Search", exact: true }).click();
  await eventually(async () =>
    assert.match(
      await page.locator("#search-results").innerText(),
      /Captured: Not provided/,
    ),
  );
  assert.equal(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
    true,
  );
  if (process.env.JARVIS_UI_SCREENSHOTS === "1") {
    const directory = new URL("../../.tmp/ui-review/", import.meta.url);
    await mkdir(directory, { recursive: true });
    await page.locator('[aria-labelledby="search-title"]').screenshot({
      path: new URL("s08-mobile.png", directory).pathname.replace(
        /^\/(\w:)/,
        "$1",
      ),
    });
  }
  await page.locator("#search-undated").uncheck();
  await page.getByRole("button", { name: "Search", exact: true }).click();
  await eventually(async () =>
    assert.match(
      await page.locator("#search-state").innerText(),
      /No matching evidence/,
    ),
  );
  await page.locator("#search-from").fill("");
  await page.locator("#search-undated").check();
  await page
    .getByLabel("Search saved evidence", { exact: true })
    .fill("Quasar passport");
  await page.getByRole("button", { name: "Search", exact: true }).click();
  await eventually(async () =>
    assert.match(
      await page.locator("#search-state").innerText(),
      /No matching evidence/,
    ),
  );
  await page.route("**/search", (route) => route.abort());
  await page.getByRole("button", { name: "Search", exact: true }).click();
  await eventually(async () =>
    assert.match(
      await page.locator("#search-state").innerText(),
      /Search could not finish/,
    ),
  );
  await page.unroute("**/search");
  let release, intercepted;
  const arrived = new Promise((resolve) => {
    intercepted = resolve;
  });
  const held = new Promise((resolve) => {
    release = resolve;
  });
  await page.route("**/search", async (route) => {
    const response = await route.fetch();
    intercepted();
    await held;
    await route.fulfill({ response }).catch(() => {});
  });
  await page.getByLabel("Search saved evidence", { exact: true }).fill("Atlas");
  await page.getByRole("button", { name: "Search", exact: true }).click();
  await arrived;
  await page.getByRole("radio", { name: "Private", exact: true }).check();
  release();
  await page.getByRole("radio", { name: "Normal", exact: true }).check();
  assert.equal(await page.locator("#search-results").innerText(), "");
  assert.equal(await page.locator("#search-query").inputValue(), "");
  assert.equal(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
    true,
  );
});

test("S07 processes synthetic fixtures and exposes memory history through the real backend", async (t) => {
  const page = await pageFor(t);
  const namespace = `memory-${randomUUID()}`;
  await importFile(page, namespace);
  await page
    .getByRole("button", { name: "Process pending", exact: true })
    .click();
  await eventually(async () => {
    const response = await fetch(
      `${origin}/processing?namespace=${namespace}`,
      { headers: { "X-Jarvis-Mode": "normal" } },
    );
    assert.equal((await response.json()).counts.succeeded, 8);
  });
  await page
    .getByRole("button", { name: "Refresh memories", exact: true })
    .click();
  await eventually(async () =>
    assert.equal(
      await page.locator("#memory-list > li > .source-button").count(),
      11,
    ),
  );
  await page
    .getByRole("button", { name: /Atlas · launch date: 2026-09-21/ })
    .click();
  await eventually(async () =>
    assert.match(
      await page.locator("#memory-history").innerText(),
      /2026-09-18/,
    ),
  );
  const history = await page.locator("#memory-history").innerText();
  assert.match(history, /superseded/);
  assert.match(history, /legal review needs more time/);
  assert.match(history, /Applies from: Unknown/);
  const ownerButton = page.getByRole("button", {
    name: /Atlas · budget owner: Ravi/,
  });
  assert.match(await ownerButton.innerText(), /tentative.*conditional/s);
  assert.match(await ownerButton.innerText(), /Only if: Finance signs off/);
  await ownerButton.click();
  await eventually(async () =>
    assert.match(
      await page.locator("#memory-history").innerText(),
      /tentative/,
    ),
  );
  assert.match(
    await page.locator("#memory-history").innerText(),
    /Finance signs off/,
  );
  await page.getByText("Search options", { exact: true }).click();
  await page.locator("#search-memories").check();
  await page.getByLabel("Search saved evidence", { exact: true }).fill("Ravi");
  await page.getByRole("button", { name: "Search", exact: true }).click();
  await eventually(async () =>
    assert.match(
      await page.locator("#search-results").innerText(),
      /Only if: Finance signs off/,
    ),
  );
  assert.match(
    await page.locator("#search-results").innerText(),
    /tentative.*conditional.*Scope: Atlas/,
  );
  if (process.env.JARVIS_UI_SCREENSHOTS === "1") {
    const path = new URL("../../.tmp/ui-review/", import.meta.url);
    await mkdir(path, { recursive: true });
    await page.screenshot({
      path: new URL("s07-memories.png", path).pathname.replace(
        /^\/(\w:)/,
        "$1",
      ),
      fullPage: true,
    });
  }
  await page.getByRole("radio", { name: "Private", exact: true }).check();
  assert.equal(
    await page.locator("#memory-list > li > .source-button").count(),
    0,
  );
  assert.equal(await page.locator("#memory-history").textContent(), "");
  await page.getByRole("radio", { name: "Normal", exact: true }).check();
  assert.equal(
    await page.locator("#memory-list > li > .source-button").count(),
    0,
  );
});

test("Private drops late memory responses and makes no processing request", async (t) => {
  const page = await pageFor(t);
  await importFile(page, `late-memory-${randomUUID()}`);
  let release;
  let reached;
  const arrived = new Promise((resolve) => {
    reached = resolve;
  });
  const blocked = new Promise((resolve) => {
    release = resolve;
  });
  await page.route("**/memories?*", async (route) => {
    reached();
    await blocked;
    try {
      await route.fulfill({
        json: {
          memories: [{ content: "SYNTHETIC_LATE_MEMORY" }],
          next_after: null,
        },
      });
    } catch {}
  });
  await page
    .getByRole("button", { name: "Refresh memories", exact: true })
    .click();
  await arrived;
  await page.getByRole("radio", { name: "Private", exact: true }).check();
  const requests = [];
  page.on("request", (r) => requests.push(r.url()));
  release();
  await page.waitForTimeout(100);
  assert.doesNotMatch(
    await page.locator("body").textContent(),
    /SYNTHETIC_LATE_MEMORY/,
  );
  assert.deepEqual(requests, []);
});

test("browser imports, reimports and inspects exact paired evidence through PostgreSQL", async (t) => {
  const page = await pageFor(t);
  const namespace = `ui-${randomUUID()}`;
  assert.equal(await page.locator(".source-button").count(), 0);
  await importFile(page, namespace);
  assert.equal(
    await page.locator("#feedback").innerText(),
    "Saved 8 new · 0 unchanged.",
  );
  assert.equal(await page.locator(".source-button").count(), 8);
  await page.getByRole("button", { name: /dict_0008/ }).click();
  await page.locator("#evidence").waitFor({ state: "visible" });
  assert.match(
    await page.locator("#raw-text").innerText(),
    /fifteen thousand rupees/,
  );
  assert.match(await page.locator("#formatted-text").innerText(), /₹50,000/);
  const first = await page.locator("#source-id").innerText();
  await importFile(page, namespace);
  assert.equal(
    await page.locator("#feedback").innerText(),
    "Saved 0 new · 8 unchanged.",
  );
  await page.getByRole("button", { name: /dict_0008/ }).click();
  await eventually(async () =>
    assert.equal(await page.locator("#source-id").innerText(), first),
  );
  await page.getByRole("button", { name: /dict_0007/ }).click();
  await eventually(async () =>
    assert.equal(await page.locator("#record-title").innerText(), "dict_0007"),
  );
  assert.equal(await page.locator("#captured-at").innerText(), "Not provided");
  assert.match(
    await page.locator("#formatted-text").innerText(),
    /25 September 2026/,
  );
  if (process.env.JARVIS_UI_SCREENSHOTS === "1") {
    const path = new URL("../../.tmp/ui-review/", import.meta.url);
    await mkdir(path, { recursive: true });
    await page.screenshot({
      path: new URL("desktop.png", path).pathname.replace(/^\/(\w:)/, "$1"),
      fullPage: true,
    });
  }
});

test("invalid/conflicting imports show bounded failures without partial records", async (t) => {
  const page = await pageFor(t);
  const namespace = `ui-${randomUUID()}`;
  await importFile(page, namespace);
  const rows = fixture.toString("utf8").trim().split("\n").map(JSON.parse);
  rows[0].raw_transcript = "SYNTHETIC_CONFLICT_DO_NOT_ECHO";
  rows.push({ record_id: "extra", raw_transcript: "Should not be committed" });
  await page.getByLabel("Add dictations").setInputFiles({
    name: "conflict.jsonl",
    mimeType: "application/x-ndjson",
    buffer: Buffer.from(rows.map(JSON.stringify).join("\n")),
  });
  await page.getByRole("button", { name: "Import to collection" }).click();
  await eventually(async () =>
    assert.match(await page.locator("#feedback").innerText(), /Import stopped/),
  );
  assert.doesNotMatch(
    await page.locator("body").innerText(),
    /SYNTHETIC_CONFLICT_DO_NOT_ECHO/,
  );
  assert.equal(await page.locator(".source-button").count(), 8);
  await page.getByLabel("Add dictations").setInputFiles({
    name: "invalid.jsonl",
    mimeType: "application/x-ndjson",
    buffer: Buffer.from("INVALID_SYNTHETIC_CONTENT"),
  });
  await page.getByRole("button", { name: "Import to collection" }).click();
  await eventually(async () =>
    assert.match(
      await page.locator("#feedback").innerText(),
      /Check the collection name and file format/,
    ),
  );
  assert.doesNotMatch(
    await page.locator("body").innerText(),
    /INVALID_SYNTHETIC_CONTENT/,
  );
});

test("source markup remains text and never executes", async (t) => {
  const page = await pageFor(t);
  const markup =
    '<img src="/unexpected-image" onerror="window.xss=1"><script>window.xss=2</script> ₹ नमस्ते';
  await importFile(
    page,
    `ui-${randomUUID()}`,
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
  await page.locator("#evidence").waitFor({ state: "visible" });
  assert.equal(await page.locator("#raw-text").textContent(), markup);
  assert.equal(
    await page.locator("#formatted-text img, #raw-text script").count(),
    0,
  );
  assert.equal(await page.evaluate(() => window.xss), undefined);
});

test("large-file rejection avoids store access and pagination reaches every source", async (t) => {
  const page = await pageFor(t);
  const requests = [];
  page.on("request", (request) => {
    if (request.url().includes("/sources")) requests.push(request.url());
  });
  await page.getByLabel("Add dictations").setInputFiles({
    name: "oversized.jsonl",
    mimeType: "application/x-ndjson",
    buffer: Buffer.alloc(1024 * 1024 + 1, "x"),
  });
  await page.getByRole("button", { name: "Import to collection" }).click();
  assert.match(
    await page.locator("#feedback").innerText(),
    /no larger than 1 MB/,
  );
  assert.deepEqual(requests, []);
  const rows = Array.from({ length: 55 }, (_, i) =>
    JSON.stringify({
      record_id: `record_${String(i).padStart(3, "0")}`,
      raw_transcript: `Synthetic pagination record ${i}`,
    }),
  );
  await importFile(page, `ui-${randomUUID()}`, Buffer.from(rows.join("\n")));
  assert.equal(await page.locator(".source-button").count(), 50);
  await page.getByRole("button", { name: "Load more sources" }).click();
  await eventually(async () =>
    assert.equal(await page.locator(".source-button").count(), 55),
  );
  assert.equal(
    await page.getByRole("button", { name: "Load more sources" }).isVisible(),
    false,
  );
  assert.equal(
    new Set(await page.locator(".source-button strong").allTextContents()).size,
    55,
  );
});

test("Private clears source/file/form state and never reads saved data or backfills", async (t) => {
  const page = await pageFor(t);
  await importFile(page, `ui-${randomUUID()}`);
  await page.getByRole("button", { name: /dict_0008/ }).click();
  await page.locator("#evidence").waitFor({ state: "visible" });
  await page.getByLabel("Add dictations").setInputFiles({
    name: "private.jsonl",
    mimeType: "application/x-ndjson",
    buffer: fixture,
  });
  const requests = [];
  page.on("request", (request) => {
    if (request.url().includes("/sources")) requests.push(request.url());
  });
  await page.getByRole("radio", { name: "Private", exact: true }).check();
  await page.locator("#private-panel").waitFor({ state: "visible" });
  assert.equal(await page.locator("#raw-text").textContent(), "");
  assert.equal(await page.locator("#source-list").textContent(), "");
  assert.equal(await page.locator("#import-file").inputValue(), "");
  assert.equal(await page.locator("#namespace").inputValue(), "diagnostic-v1");
  await page.getByRole("radio", { name: "Normal", exact: true }).check();
  assert.equal(await page.locator(".source-button").count(), 0);
  assert.equal(await page.locator("#import-file").inputValue(), "");
  assert.deepEqual(requests, []);
});

test("late Normal response cannot repopulate Private or the next Normal context", async (t) => {
  const page = await pageFor(t);
  await importFile(page, `ui-${randomUUID()}`);
  let release;
  const gate = new Promise((resolve) => {
    release = resolve;
  });
  let arrived;
  const seen = new Promise((resolve) => {
    arrived = resolve;
  });
  await page.route("**/sources/*", async (route) => {
    const response = await route.fetch();
    arrived();
    await gate;
    await route.fulfill({ response }).catch(() => {}); // An aborted request is expected.
  });
  await page.getByRole("button", { name: /dict_0008/ }).click();
  await seen;
  await page.getByRole("radio", { name: "Private", exact: true }).check();
  await page.getByRole("radio", { name: "Normal", exact: true }).check();
  release();
  await page.unrouteAll({ behavior: "wait" });
  assert.equal(await page.locator("#raw-text").textContent(), "");
  assert.equal(await page.locator(".source-button").count(), 0);
  assert.equal(await page.locator("#feedback").textContent(), "");
});

test("network failure is distinct from an empty collection and errors never echo content", async (t) => {
  const page = await pageFor(t);
  await page.route("**/sources?*", (route) =>
    route.fulfill({
      status: 503,
      contentType: "application/json",
      body: JSON.stringify({ reason: "DATABASE_SECRET_SYNTHETIC_FAILURE" }),
    }),
  );
  await page.getByRole("button", { name: "Open", exact: true }).click();
  await eventually(async () =>
    assert.match(
      await page.locator("#feedback").innerText(),
      /could not be completed/,
    ),
  );
  assert.doesNotMatch(
    await page.locator("body").innerText(),
    /DATABASE_SECRET_SYNTHETIC_FAILURE|This collection is empty/,
  );
});

test("mobile keyboard journey fits viewport; navigation never restores prior evidence", async (t) => {
  const page = await pageFor(t, { width: 390, height: 844 });
  await page
    .getByLabel("Collection name", { exact: true })
    .fill(`empty-${randomUUID()}`);
  await page.getByLabel("Collection name", { exact: true }).press("Enter");
  await eventually(async () =>
    assert.equal(
      await page.locator("#feedback").innerText(),
      "Collection opened.",
    ),
  );
  await importFile(page, `ui-${randomUUID()}`);
  await page.getByRole("button", { name: /dict_0008/ }).click();
  await page.locator("#evidence").waitFor({ state: "visible" });
  assert.equal(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
    true,
  );
  if (process.env.JARVIS_UI_SCREENSHOTS === "1") {
    const path = new URL(
      "../../.tmp/ui-review/mobile.png",
      import.meta.url,
    ).pathname.replace(/^\/(\w:)/, "$1");
    await page.screenshot({ path, fullPage: true });
  }
  await page.goto("about:blank");
  await page.goBack();
  await page.getByRole("heading", { name: "Start with the source." }).waitFor();
  assert.equal(await page.locator("#raw-text").textContent(), "");
  assert.equal(await page.locator(".source-button").count(), 0);
});

test("S06 Ask cites stored evidence, diagnoses feedback, and clears all reply state in Private", async (t) => {
  const page = await pageFor(t);
  await importFile(page, `ask-${randomUUID()}`);
  await page.getByRole("button", { name: "Try a sample question" }).click();
  await eventually(async () =>
    assert.match(
      await page.locator("#ask-question").inputValue(),
      /Atlas launch/,
    ),
  );
  await page.getByRole("button", { name: "Ask from my sources" }).click();
  await eventually(async () =>
    assert.match(
      await page.locator("#ask-result").innerText(),
      /Synthetic contract answer/,
    ),
  );
  assert.ok(await page.locator("#ask-result details").count());
  await page.getByRole("button", { name: "Review feedback" }).click();
  await eventually(async () =>
    assert.match(
      await page.locator("#feedback-guidance").innerText(),
      /Which source/,
    ),
  );
  await page.locator("#feedback-kind").selectOption("generation");
  await page.getByRole("button", { name: "Review feedback" }).click();
  await eventually(async () =>
    assert.match(
      await page.locator("#feedback-guidance").innerText(),
      /One new answer/,
    ),
  );
  if (process.env.JARVIS_UI_SCREENSHOTS === "1")
    await page.screenshot({
      path: new URL(
        "../../.tmp/ui-review/s09-ask.png",
        import.meta.url,
      ).pathname.replace(/^\/(\w:)/, "$1"),
      fullPage: true,
    });
  await page.getByLabel("Private", { exact: true }).check();
  assert.equal(await page.locator("#ask-question").inputValue(), "");
  assert.equal(await page.locator("#ask-result").textContent(), "");
  assert.equal(await page.locator("#feedback-guidance").textContent(), "");
  await page.getByLabel("Normal", { exact: true }).check();
  assert.equal(await page.locator("#ask-result").textContent(), "");
});

test("Ask distinguishes transport failure and rejects a late reply after Private", async (t) => {
  const page = await pageFor(t);
  await importFile(page, `late-ask-${randomUUID()}`);
  await page.locator("#ask-question").fill("Atlas launch");
  await page.route("**/ask", (route) => route.abort());
  await page.getByRole("button", { name: "Ask from my sources" }).click();
  await eventually(async () =>
    assert.match(
      await page.locator("#ask-state").innerText(),
      /could not|failed/i,
    ),
  );
  assert.equal(await page.locator("#ask-result").textContent(), "");
  await page.unroute("**/ask");
  let release, intercepted;
  const arrived = new Promise((resolve) => {
    intercepted = resolve;
  });
  const held = new Promise((resolve) => {
    release = resolve;
  });
  await page.route("**/ask", async (route) => {
    const response = await route.fetch();
    intercepted();
    await held;
    await route.fulfill({ response }).catch(() => {});
  });
  await page.getByRole("button", { name: "Ask from my sources" }).click();
  await arrived;
  await page.getByLabel("Private", { exact: true }).check();
  release();
  await page.getByLabel("Normal", { exact: true }).check();
  assert.equal(await page.locator("#ask-result").textContent(), "");
  assert.equal(await page.locator("#ask-question").inputValue(), "");
  assert.equal(await page.locator("#feedback-guidance").textContent(), "");
});

test("S09 mobile correction, world change, Forget and renamed reimport use the real backend", async (t) => {
  const page = await pageFor(t, { width: 390, height: 844 });
  await importFile(page, `controls-${randomUUID()}`);
  await page
    .getByRole("button", { name: "Process pending", exact: true })
    .click();
  await eventually(async () => {
    if (
      (await page.locator("#normal-panel").getAttribute("aria-busy")) ===
      "false"
    )
      await page.getByRole("button", { name: "Refresh memories" }).click();
    assert.match(
      await page.locator("#processing-state").innerText(),
      /8 succeeded/,
    );
  });
  const launch = () =>
    page
      .locator("#memory-list > li")
      .filter({ hasText: /launch date/ })
      .first();
  for (const [button, date] of [
    ["Correct", "2026-09-23"],
    ["Record a change", "2026-09-25"],
  ]) {
    await launch().getByRole("button", { name: button, exact: true }).click();
    await page
      .locator("#control-statement")
      .fill(`The Atlas launch plan is ${date}.`);
    await page.locator("#control-value").fill(date);
    await page
      .getByRole("button", { name: "Preview change", exact: true })
      .click();
    await page.locator("#confirm-control").waitFor({ state: "visible" });
    assert.match(
      await page.locator("#control-preview").innerText(),
      new RegExp(date),
    );
    await page
      .getByRole("button", { name: "Confirm this change", exact: true })
      .click();
    await eventually(async () =>
      assert.match(await page.locator("#feedback").innerText(), /Change saved/),
    );
    await eventually(async () =>
      assert.match(await launch().innerText(), new RegExp(date)),
    );
  }
  await page.locator("#search-query").fill("legal review launch");
  await page.getByRole("button", { name: "Search", exact: true }).click();
  await eventually(async () =>
    assert.match(
      await page.locator("#search-results").innerText(),
      /2026-09-25/,
    ),
  );
  await launch().getByRole("button", { name: "Forget", exact: true }).click();
  await page
    .getByRole("button", { name: "Preview change", exact: true })
    .click();
  await page.locator("#confirm-control").waitFor({ state: "visible" });
  assert.match(
    await page.locator("#forget-explanation").innerText(),
    /known copies/,
  );
  assert.equal(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
    true,
  );
  if (process.env.JARVIS_UI_SCREENSHOTS === "1")
    await page.screenshot({
      path: new URL(
        "../../.tmp/ui-review/s09-controls-mobile.png",
        import.meta.url,
      ).pathname.replace(/^\/(\w:)/, "$1"),
      fullPage: true,
    });
  await page
    .getByRole("button", { name: "Confirm this change", exact: true })
    .click();
  await eventually(async () =>
    assert.match(
      await page.locator("#feedback").innerText(),
      /Forgotten for future use/,
    ),
  );
  assert.equal(
    await page
      .locator("#memory-list > li")
      .filter({ hasText: /launch date/ })
      .count(),
    0,
  );
  await page.getByRole("button", { name: /dict_0003/ }).click();
  await eventually(async () =>
    assert.match(
      await page.locator("#raw-text").innerText(),
      /september twenty first/,
    ),
  );
  await importFile(page, `renamed-${randomUUID()}`);
  await page.locator("#search-query").fill("eighteenth twenty first launch");
  await page.getByRole("button", { name: "Search", exact: true }).click();
  await eventually(async () =>
    assert.match(
      await page.locator("#search-state").innerText(),
      /No matching|matching source/,
    ),
  );
  assert.doesNotMatch(
    await page.locator("#search-results").innerText(),
    /dict_0001|dict_0003/,
  );
});
