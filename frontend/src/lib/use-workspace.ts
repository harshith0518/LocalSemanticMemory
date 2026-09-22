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
  MessageLearning,
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
  const conversationId = useRef(crypto.randomUUID());
  const [contentVersion, setContentVersion] = useState(0);
  const [busy, setBusy] = useState("");
  const [notice, setNotice] = useState({ text: "", error: false });
  const [timing, setTiming] = useState<Timing>();
  const active = useRef(true);
  const running = useRef(false);
  const epoch = useRef(0);
  const processingPaused = useRef(false);
  const [learning, setLearning] = useState(false);
  useEffect(() => {
    processingPaused.current = true;
    setLearning(false);
  }, [namespace]);
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
    conversationId.current = crypto.randomUUID();
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
      await loadMemories();
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
        const ticket = epoch.current;
        processingPaused.current = false;
        const receipt = await session.post<{ requested: number }>(
          "/processing",
          {
            namespace,
            expected_policy_revision: sources.policy_revision,
            retry_failed: retry,
          },
        );
        setLearning(true);
        let completed = 0;
        const current = () => active.current && ticket === epoch.current;
        try {
          while (current() && !processingPaused.current) {
            const step = await session.post<{
              result: {
                status?: string;
                reason?: string;
                decision?: string;
              } | null;
              pause_ms: number;
            }>(
              `/processing/step?namespace=${encodeURIComponent(namespace)}`,
              {},
            );
            if (!current()) break;
            await loadMemories();
            if (!step.result) {
              setNotice({
                text: `Queued ${receipt.requested}; completed ${completed} here. No job is available now. Another worker may hold the lease; Refresh shows the authoritative status.`,
                error: false,
              });
              break;
            }
            if (step.result.status === "failed") {
              setNotice({
                text: `Learning stopped: ${step.result.reason ?? "operation_failed"}. Originals are preserved. Inspect the trace before an explicit retry.`,
                error: true,
              });
              break;
            }
            completed += 1;
            setNotice({
              text: `Learned ${completed} source(s) in this run. Latest decision: ${step.result.decision ?? "recorded"}.`,
              error: false,
            });
            if (step.pause_ms)
              await new Promise((resolve) =>
                setTimeout(resolve, step.pause_ms),
              );
          }
          if (current() && processingPaused.current)
            setNotice({
              text: `Paused after ${completed} source(s). No further steps will be submitted by this page. An already submitted Normal request can still finish.`,
              error: false,
            });
        } finally {
          if (current()) setLearning(false);
        }
      },
    );
  async function learnMessage(sourceId: string, retryFailed = false) {
    const ticket = epoch.current;
    for (let attempt = 0; ; attempt++) {
      if (!active.current || ticket !== epoch.current)
        throw new DOMException("Cancelled", "AbortError");
      const receipt = await session.post<MessageLearning>(
        `/conversation/messages/${sourceId}/learn`,
        { retry_failed: retryFailed && attempt === 0 },
      );
      if (
        !["pending", "running"].includes(receipt.status) ||
        receipt.error_code ||
        attempt >= 7
      )
        return receipt;
      // Only wait for an occupied lease. Failed provider calls need an explicit retry.
      await new Promise((resolve) => setTimeout(resolve, 1000));
    }
  }
  const retryLearning = (turn: Turn) =>
    run("Checking learning for this saved message", async () => {
      if (!turn.learning?.source_id) return;
      const learning = await learnMessage(turn.learning.source_id, true);
      setTurns((previous) =>
        previous.map((item) =>
          item.id === turn.id
            ? { ...item, learning, learningError: undefined }
            : item,
        ),
      );
      setContentVersion((previous) => previous + 1);
      await loadSources();
      await loadMemories();
    });
  const ask = (request: AnswerRequest, retry?: Turn) =>
    run("Checking your message", async () => {
      const ticket = epoch.current;
      const started = performance.now();
      const measured = (outcome: Timing["outcome"]): Timing => ({
        elapsed_ms: performance.now() - started,
        stages: session.timings.join(", "),
        outcome,
      });
      const turn: Turn = {
        id: retry?.id ?? crypto.randomUUID(),
        conversation_id: retry?.conversation_id ?? conversationId.current,
        question: request.question,
        request,
      };
      setTurns((previous) =>
        retry
          ? previous.map((item) => (item.id === turn.id ? turn : item))
          : [...previous.slice(-11), turn],
      );
      try {
        const saved = await session.post<MessageLearning>(
          "/conversation/messages",
          {
            message_id: turn.id,
            conversation_id: turn.conversation_id,
            request,
          },
        );
        setTurns((previous) =>
          previous.map((item) =>
            item.id === turn.id ? { ...item, learning: saved } : item,
          ),
        );
        setContentVersion((previous) => previous + 1);
        setBusy("Checking your message for new information");
        if (saved.source_id)
          try {
            const learning = await learnMessage(saved.source_id);
            setTurns((previous) =>
              previous.map((item) =>
                item.id === turn.id ? { ...item, learning } : item,
              ),
            );
          } catch (error) {
            if (isCancelled(error)) throw error;
            setTurns((previous) =>
              previous.map((item) =>
                item.id === turn.id
                  ? { ...item, learningError: messageFor(error) }
                  : item,
              ),
            );
          }
        setBusy("Reading evidence and checking the answer");
        const answer = await session.post<Answer>("/ask", request);
        setTurns((previous) =>
          previous.map((item) =>
            item.id === turn.id
              ? { ...item, answer, timing: measured("completed") }
              : item,
          ),
        );
      } catch (error) {
        if (!isCancelled(error))
          setTurns((previous) =>
            previous.map((item) =>
              item.id === turn.id
                ? {
                    ...item,
                    error: messageFor(error),
                    timing: measured("failed"),
                  }
                : item,
            ),
          );
        throw error;
      } finally {
        setContentVersion((previous) => previous + 1);
        // Refresh failures must not replace a completed answer or a saved receipt.
        if (active.current && ticket === epoch.current) {
          try {
            await loadSources();
            await loadMemories();
          } catch {
            /* The next page refresh can recover these derived lists. */
          }
        }
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
    learning,
    stopProcessing: () => {
      processingPaused.current = true;
    },
    ask,
    retryLearning,
    clearConversation: () => {
      setTurns([]);
      conversationId.current = crypto.randomUUID();
    },
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
