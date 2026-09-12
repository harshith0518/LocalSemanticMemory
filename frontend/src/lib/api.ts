export const errors: Record<string, string> = {
  network_error:
    "The connection was interrupted. A submitted save may have completed; retry the same input safely.",
  provider_disabled:
    "Live answers are not enabled or a model key is missing. Check model setup below; repeating the question will not enable it. Sources and memory controls still work.",
  trial_input_denied:
    "This installation permits only the approved synthetic corpus and questions. Unfamiliar notes need the operator's explicit unfamiliar opt-in. Your note stays saved locally.",
  budget_exhausted:
    "The evaluation allowance is exhausted. Your saved sources and memories remain available.",
  context_limit:
    "This collection exceeds the processing context limit. No partial interpretation was saved.",
  import_conflict:
    "A record differs from its saved original. No records in this batch were changed.",
  stale_revision:
    "Your workspace changed during this action. Open the collection again before retrying.",
  private_operation_denied: "Saved information is unavailable in Private mode.",
  reference_unavailable:
    "This source is unavailable. Open the collection again.",
  invalid_input:
    "Check the input and its format. The entire request must be valid.",
  database_unavailable:
    "The workspace could not be reached. Try again when the connection is restored.",
  excluded_source: "This evidence was forgotten and cannot be used again.",
  provider_failed:
    "The model provider could not finish. This is a service failure, not missing evidence.",
  provider_response_invalid:
    "The model response failed validation. No answer was released.",
  retry_limit_reached: "This answer has already used its one feedback retry.",
};
export class RequestError extends Error {
  constructor(readonly reason: string) {
    super(
      errors[reason] ??
        "The action could not finish. No external action was performed.",
    );
  }
}
export const isCancelled = (error: unknown) =>
  error instanceof DOMException && error.name === "AbortError";
export const messageFor = (error: unknown) =>
  error instanceof RequestError
    ? error.message
    : "The connection was interrupted. A submitted save may have completed; retry the same input safely.";

/** One ephemeral Normal session. No storage, automatic retry, analytics or query-string prompts. */
export class ApiSession {
  private disposed = false;
  private generation = 0;
  private controllers = new Set<AbortController>();
  timings: string[] = [];
  dispose() {
    this.disposed = true;
    this.invalidate();
  }
  invalidate() {
    this.generation += 1;
    for (const controller of this.controllers) controller.abort();
    this.controllers.clear();
    this.timings = [];
  }
  async request<T>(path: string, options: RequestInit = {}): Promise<T> {
    if (this.disposed) throw new DOMException("Cancelled", "AbortError");
    const ticket = this.generation;
    const controller = new AbortController();
    this.controllers.add(controller);
    const assertCurrent = () => {
      if (ticket !== this.generation)
        throw new DOMException("Cancelled", "AbortError");
    };
    try {
      const response = await fetch(path, {
        ...options,
        cache: "no-store",
        credentials: "omit",
        redirect: "error",
        headers: { "X-Jarvis-Mode": "normal", ...options.headers },
        signal: AbortSignal.any([
          controller.signal,
          AbortSignal.timeout(
            path === "/ask" || path === "/feedback" ? 390000 : 15000,
          ),
        ]),
      });
      assertCurrent();
      const result = await response.json();
      assertCurrent();
      const timing = response.headers.get("Server-Timing");
      if (timing && /^[a-z_0-9.;= ,]+$/.test(timing)) this.timings.push(timing);
      if (!response.ok)
        throw new RequestError(
          typeof result.reason === "string"
            ? result.reason
            : "operation_failed",
        );
      return result as T;
    } catch (error) {
      assertCurrent();
      if (error instanceof RequestError || isCancelled(error)) throw error;
      throw new RequestError("network_error");
    } finally {
      this.controllers.delete(controller);
    }
  }
  post<T>(path: string, body: unknown) {
    return this.request<T>(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  }
}
