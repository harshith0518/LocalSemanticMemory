import { useState } from "react";
import { BookOpen, FileText, Search as SearchIcon, Upload } from "lucide-react";
import { Button } from "./ui/button";
import { Input } from "./ui/input";
import { Badge } from "./ui/badge";
import { Empty, Heading, OriginalButton, Qualifiers } from "./common";
import type { Workspace } from "@/lib/use-workspace";
import type { Search } from "@/lib/types";
import { isCancelled } from "@/lib/api";

export function Sources({ workspace: w }: { workspace: Workspace }) {
  const [file, setFile] = useState<File>();
  const [fileKey, setFileKey] = useState(0);
  const [result, setResult] = useState<Search>();
  const [searchState, setSearchState] = useState(
    "Search runs only when you ask.",
  );
  async function importFile() {
    if (!file) return;
    if (!file.size || file.size > 1024 * 1024) {
      w.setNotice({
        text: "Choose a nonempty JSONL file no larger than 1 MB.",
        error: true,
      });
      return;
    }
    const receipt = await w.run("Importing your original dictations", () =>
      w.importContent(file),
    );
    if (receipt) {
      setFile(undefined);
      setFileKey((previous) => previous + 1);
      setResult(undefined);
    }
  }
  async function search(form: HTMLFormElement) {
    const data = new FormData(form);
    await w.run("Searching saved evidence", async () => {
      setResult(undefined);
      setSearchState("Searching saved evidence…");
      try {
        const response = await w.session.post<Search>("/search", {
          namespace: w.namespace,
          query: data.get("query"),
          representation: data.has("memories")
            ? "sources_and_memories"
            : "sources",
          history: data.has("history"),
          captured_from: data.get("from")
            ? `${data.get("from")}T00:00:00Z`
            : null,
          captured_to: data.get("to")
            ? `${data.get("to")}T23:59:59.999999Z`
            : null,
          include_undated: data.has("undated"),
        });
        setResult(response);
        setSearchState(
          response.status === "no_matches"
            ? "No matching evidence found. Different wording may help; this does not establish that a fact is unknown."
            : response.status === "evidence_budget_exceeded"
              ? "The matching record is too large for this view. Browse its original source."
              : `${response.matches.length} matching sources.${response.has_more ? " More evidence is available; narrow your search." : ""}${response.budget_limited ? " The evidence limit was reached; records were kept whole." : ""}`,
        );
      } catch (error) {
        if (!isCancelled(error))
          setSearchState(
            "Search could not finish. This does not mean evidence is absent.",
          );
        throw error;
      }
    });
  }
  return (
    <>
      <Heading
        eyebrow="01 / Keep the original"
        title="Every memory starts somewhere."
        action={
          <Button
            variant="outline"
            disabled={!!w.busy}
            onClick={() => void w.open()}
          >
            Open collection
          </Button>
        }
      >
        Your exact words, their context, and the evidence you can always
        inspect.
      </Heading>
      <section className="sample-banner">
        <div className="sample-symbol">
          <BookOpen />
        </div>
        <div>
          <h2>Meet Jarvis through a small story.</h2>
          <p>
            Eight synthetic notes: changing plans, uncertain ownership, scoped
            preferences and conflicting amounts.
          </p>
        </div>
        <Button disabled={!!w.busy} onClick={() => void w.sample()}>
          Try the sample
        </Button>
      </section>
      <div className="sources-grid">
        <section className="panel source-library">
          <div className="section-title">
            <h2>Original sources</h2>
            <Badge variant="secondary">
              {w.sources
                ? `${w.sources.observations.length}${w.sources.next_after ? "+" : ""}`
                : "Not opened"}
            </Badge>
          </div>
          <p className="meta">
            Collection: {w.namespace}. Capture dates are shown only when
            provided.
          </p>
          {!w.sources ? (
            <Empty icon={<FileText />} title="Open your collection">
              Choose Open collection to read saved sources.
            </Empty>
          ) : !w.sources.observations.length ? (
            <Empty icon={<FileText />} title="Room for your first thought">
              Save a note in Conversation, import a file, or try the synthetic
              sample.
            </Empty>
          ) : (
            <ul id="source-list" className="source-list">
              {w.sources.observations.map((source) => (
                <li key={source.id}>
                  <button
                    disabled={!!w.busy}
                    onClick={() => void w.inspect(source.id)}
                  >
                    <span className="source-icon">
                      <FileText />
                    </span>
                    <span>
                      <strong>{source.source_key.split(":").at(-1)}</strong>
                      <small>
                        Captured: {source.captured_at ?? "Not provided"} ·
                        revision {source.revision}
                      </small>
                    </span>
                    <span aria-hidden="true">↗</span>
                  </button>
                </li>
              ))}
            </ul>
          )}
          {w.sources?.next_after && (
            <Button
              variant="outline"
              disabled={!!w.busy}
              onClick={() =>
                void w.run("Loading more sources", () =>
                  w.loadSources(w.sources?.next_after ?? undefined),
                )
              }
            >
              Load more sources
            </Button>
          )}
        </section>
        <section className="panel import-panel">
          <span className="empty-icon">
            <Upload />
          </span>
          <h2>Bring your words.</h2>
          <p>
            Import raw and optional formatted transcripts together. Reimporting
            the same records is safe.
          </p>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              void importFile();
            }}
          >
            <label htmlFor="import-file">Add dictations</label>
            <Input
              key={fileKey}
              type="file"
              id="import-file"
              accept=".jsonl,application/x-ndjson"
              onChange={(e) => setFile(e.target.files?.[0])}
              disabled={!!w.busy}
            />
            <span className="meta">
              JSONL · up to 1 MB · one observation per line
            </span>
            <Button
              type="submit"
              variant="outline"
              disabled={!!w.busy || !file}
            >
              Import to collection
              <Upload />
            </Button>
          </form>
          <details>
            <summary>File format</summary>
            <pre>
              {
                '{"record_id":"note-1","raw_transcript":"Your exact words","formatted_text":null,"metadata":null}'
              }
            </pre>
            <p className="meta">
              Record IDs must be stable. Changed content under the same ID is
              rejected atomically.
            </p>
          </details>
        </section>
      </div>
      <section className="panel search-panel" aria-labelledby="search-title">
        <div className="section-title">
          <h2 id="search-title">Find the thread.</h2>
          <Badge variant="outline">No model needed</Badge>
        </div>
        <form
          autoComplete="off"
          onSubmit={(e) => {
            e.preventDefault();
            void search(e.currentTarget);
          }}
        >
          <label htmlFor="search-query">Search saved evidence</label>
          <div className="search-row">
            <Input
              id="search-query"
              name="query"
              placeholder="A project, a decision, a detail…"
              required
              maxLength={512}
              disabled={!!w.busy}
            />
            <Button type="submit" disabled={!!w.busy}>
              <SearchIcon />
              Search
            </Button>
          </div>
          <details>
            <summary>Search options</summary>
            <div className="form-grid">
              <label>
                <input type="checkbox" name="memories" /> Include learned
                memories
              </label>
              <label>
                <input type="checkbox" name="history" /> Include historical
                memory
              </label>
              <label>
                Captured from (UTC)
                <Input type="date" id="search-from" name="from" />
              </label>
              <label>
                Captured until (UTC)
                <Input type="date" id="search-to" name="to" />
              </label>
              <label>
                <input
                  type="checkbox"
                  name="undated"
                  id="search-undated"
                  defaultChecked
                />{" "}
                Include undated sources
              </label>
            </div>
          </details>
        </form>
        <p id="search-state" className="meta" role="status">
          {searchState}
        </p>
        <div id="search-results">
          {result?.sources.map((source) => (
            <article className="search-result" key={source.id}>
              <h3>{source.source_key.split(":").at(-1)}</h3>
              <p className="meta">
                {result.matches.some((match) => match.source_id === source.id)
                  ? "Matching source"
                  : "Additional supporting source"}{" "}
                · Captured: {source.captured_at ?? "Not provided"}
              </p>
              <h4>Original transcript</h4>
              <p className="passage">{source.raw_text}</p>
              {source.formatted_text !== null && (
                <>
                  <h4>Formatted text · same observation</h4>
                  <p className="passage">{source.formatted_text}</p>
                </>
              )}
              {result.memories
                .filter((memory) =>
                  memory.passages.some(
                    (passage) => passage.source_id === source.id,
                  ),
                )
                .map((memory) => (
                  <div key={memory.id}>
                    <p>
                      {memory.content.subject.label} ·{" "}
                      {String(memory.content.value.value)}
                    </p>
                    <Qualifiers claim={memory} />
                  </div>
                ))}
              <OriginalButton
                disabled={!!w.busy}
                onClick={() => void w.inspect(source.id)}
              />
            </article>
          ))}
        </div>
      </section>
    </>
  );
}
