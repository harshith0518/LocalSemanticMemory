import { useEffect, useRef, useState } from "react";
import { ApiSession, isCancelled, messageFor } from "./api";
import type {
  Answer,
  AnswerRequest,
  ControlCommand,
  ControlPreview,
  FeedbackResult,
  History,
  ImportReceipt,
  Inspection,
  MemoryPage,
  Processing,
  SourcePage,
  Timing,
  Turn,
  Usage,
} from "./types";

/** State belongs to this mounted Normal workspace only. The service owns authorization. */
export function useWorkspace(session: ApiSession) {
  const [namespace, setNamespace] = useState("my-notes");
  const [sources, setSources] = useState<SourcePage>();
  const [memories, setMemories] = useState<MemoryPage>();
  const [processing, setProcessing] = useState<Processing>();
  const [inspection, setInspection] = useState<Inspection>();
  const [history, setHistory] = useState<History>();
  const [usage, setUsage] = useState<Usage>();
  const [turns, setTurns] = useState<Turn[]>([]);
  const [contentVersion, setContentVersion] = useState(0);
  const [busy, setBusy] = useState("");
  const [notice, setNotice] = useState({ text: "", error: false });
  const [timing, setTiming] = useState<Timing>();
  const active = useRef(true);
  const running = useRef(false);
  const epoch = useRef(0);
  useEffect(
    () => () => {
      active.current = false;
      session.dispose();
    },
    [session],
  );

  async function run<T>(
    label: string,
    operation: () => Promise<T>,
  ): Promise<T | undefined> {
    if (!active.current || running.current) return;
    const ticket = epoch.current;
    running.current = true;
    setBusy(label);
    setNotice({ text: "", error: false });
    session.timings = [];
    const started = performance.now();
    let outcome: Timing["outcome"] = "completed";
    try {
      return await operation();
    } catch (error) {
      outcome = "failed";
      if (active.current && ticket === epoch.current && !isCancelled(error))
        setNotice({ text: messageFor(error), error: true });
    } finally {
      if (active.current && ticket === epoch.current) {
        setTiming({
          elapsed_ms: performance.now() - started,
          stages: session.timings.join(", "),
          outcome,
        });
        running.current = false;
        setBusy("");
      }
    }
  }
  function clear() {
    epoch.current++;
    session.invalidate();
    running.current = false;
    setBusy("");
    setSources(undefined);
    setMemories(undefined);
    setProcessing(undefined);
    setInspection(undefined);
    setHistory(undefined);
    setUsage(undefined);
    setTurns([]);
    setTiming(undefined);
    setNotice({ text: "", error: false });
  }
  function changeNamespace(value: string) {
    clear();
    setNamespace(value);
  }
  const query = (after?: string) =>
    new URLSearchParams({ namespace, ...(after ? { after } : {}) });
  async function loadSources(after?: string) {
    const result = await session.request<SourcePage>(
      `/sources?${query(after)}`,
    );
    setSources((previous) =>
      after && previous
        ? {
            ...result,
            observations: [...previous.observations, ...result.observations],
          }
        : result,
    );
    return result;
  }
  async function loadMemories(after?: string) {
    const status = await session.request<Processing>(`/processing?${query()}`);
    setProcessing(status);
    const result = await session.request<MemoryPage>(
      `/memories?${query(after)}`,
    );
    setMemories((previous) =>
      after && previous
        ? { ...result, memories: [...previous.memories, ...result.memories] }
        : result,
    );
  }
  async function importContent(content: Blob | string) {
    const page = await loadSources();
    const params = new URLSearchParams({
      namespace,
      expected_policy_revision: String(page.policy_revision),
    });
    const receipt = await session.request<ImportReceipt>(
      `/sources/import?${params}`,
      {
        method: "POST",
        headers: { "Content-Type": "application/x-ndjson" },
        body: content,
      },
    );
    setNotice({
      text: `Saved ${receipt.created} new · ${receipt.unchanged} unchanged.`,
      error: false,
    });
    try {
      await loadSources();
    } catch (error) {
      if (isCancelled(error)) throw error;
      setNotice({
        text: `Import saved: ${receipt.created} new, ${receipt.unchanged} unchanged. Open the collection to refresh its sources.`,
        error: false,
      });
    }
    return receipt;
  }
  const open = () =>
    run("Opening your collection", async () => {
      await loadSources();
      await loadMemories();
      setNotice({ text: "Collection opened.", error: false });
    });
  const inspect = (id: string) =>
    run("Opening the original source", async () => {
      setInspection(undefined);
      setInspection(
        await session.request<Inspection>(`/sources/${encodeURIComponent(id)}`),
      );
    });
  const showHistory = (id: string) =>
    run("Reading memory history", async () => {
      setHistory(undefined);
      setHistory(
        await session.request<History>(`/memories/${encodeURIComponent(id)}`),
      );
    });
  const sample = () =>
    run("Adding the synthetic sample", async () => {
      const data = await session.request<{ jsonl: string }>("/trial/sources");
      return importContent(data.jsonl);
    });
  const process = (retry = false) =>
    run(
      retry ? "Requesting a processing retry" : "Queuing eligible sources",
      async () => {
        if (!sources)
          return setNotice({ text: "Open a collection first.", error: true });
        const receipt = await session.post<{ requested: number }>(
          "/processing",
          {
            namespace,
            expected_policy_revision: sources.policy_revision,
            retry_failed: retry,
          },
        );
        setNotice({
          text: `Queued ${receipt.requested} sources. Processing continues in the background; refresh to inspect the result.`,
          error: false,
        });
        await loadMemories();
      },
    );
  const ask = (request: AnswerRequest) =>
    run("Reading evidence and checking the answer", async () => {
      const turn: Turn = {
        id: crypto.randomUUID(),
        question: request.question,
        request,
      };
      setTurns((previous) => [...previous.slice(-11), turn]);
      try {
        const answer = await session.post<Answer>("/ask", request);
        setTurns((previous) =>
          previous.map((item) =>
            item.id === turn.id ? { ...item, answer } : item,
          ),
        );
      } catch (error) {
        if (!isCancelled(error))
          setTurns((previous) =>
            previous.map((item) =>
              item.id === turn.id
                ? { ...item, error: messageFor(error) }
                : item,
            ),
          );
        throw error;
      }
    });
  const feedback = (turn: Turn, diagnosis: string) =>
    run("Reviewing your feedback", async () => {
      const result = await session.post<FeedbackResult>("/feedback", {
        call_id: turn.answer?.call_ids.at(-1),
        request: turn.request,
        diagnosis,
      });
      if (result.answer && result.request)
        setTurns((previous) =>
          previous.map((item) =>
            item.id === turn.id
              ? { ...item, answer: result.answer, request: result.request! }
              : item,
          ),
        );
      setNotice({ text: result.guidance, error: false });
    });
  const preview = (command: ControlCommand) =>
    run("Checking the proposed change", () =>
      session.post<ControlPreview>("/controls/preview", command),
    );
  const apply = (command: ControlCommand) =>
    run("Saving your reviewed change", async () => {
      const receipt = await session.post<{
        policy_revision: number;
        action: string;
      }>("/controls/apply", command);
      setContentVersion((previous) => previous + 1);
      setSources(undefined);
      setMemories(undefined);
      setProcessing(undefined);
      setTurns([]);
      setInspection(undefined);
      setHistory(undefined);
      setUsage(undefined);
      try {
        await loadSources();
        await loadMemories();
      } catch (error) {
        if (isCancelled(error)) throw error;
      }
      setNotice({
        text:
          receipt.action === "forget"
            ? "Forgotten for future use and learning. Original history remains in Sources."
            : "Change saved with evidence. Open the collection to inspect its current state.",
        error: false,
      });
      return receipt;
    });
  return {
    session,
    namespace,
    changeNamespace,
    sources,
    memories,
    processing,
    inspection,
    setInspection,
    history,
    setHistory,
    usage,
    turns,
    setTurns,
    contentVersion,
    busy,
    notice,
    setNotice,
    timing,
    run,
    open,
    loadSources,
    loadMemories,
    importContent,
    sample,
    inspect,
    showHistory,
    process,
    ask,
    feedback,
    preview,
    apply,
    refreshUsage: () =>
      run("Measuring saved workspace usage", async () =>
        setUsage(await session.request<Usage>("/usage")),
      ),
  };
}
export type Workspace = ReturnType<typeof useWorkspace>;
