import { useRef, useState } from "react";
import { m } from "motion/react";
import {
  ArrowDown,
  ArrowRight,
  ArrowUp,
  BookOpen,
  Check,
  FilePlus2,
  MessageCircle,
  Sparkles,
} from "lucide-react";
import { Button } from "./ui/button";
import { Textarea } from "./ui/textarea";
import { Tabs, TabsList, TabsTrigger } from "./ui/tabs";
import { Activity, OriginalButton, Sprout } from "./common";
import type { Workspace } from "@/lib/use-workspace";
import type { Representation, Turn } from "@/lib/types";

function Reply({ turn, workspace }: { turn: Turn; workspace: Workspace }) {
  const [diagnosis, setDiagnosis] = useState("unclear");
  const answer = turn.answer;
  return (
    <article className="conversation-turn">
      <div className="user-message">
        <span className="eyebrow">You</span>
        <p>{turn.question}</p>
      </div>
      {answer ? (
        <m.div
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.25 }}
          className="reply"
        >
          <div className="reply-byline">
            <Sprout />
            <strong>jarvis</strong>
            <span>
              {
                {
                  answered: "From your recorded evidence",
                  draft: "Draft · not sent",
                  unknown: "Not established by available evidence",
                  clarification: "Clarification needed",
                }[answer.status]
              }
            </span>
          </div>
          <p className="reply-text">{answer.text}</p>
          <div className="citations">
            {answer.citations.map((passage, index) => (
              <details key={`${passage.source_id}-${index}`}>
                <summary>
                  <BookOpen aria-hidden="true" />
                  <span>
                    Source:{" "}
                    {answer.sources
                      .find((source) => source.id === passage.source_id)
                      ?.source_key.split(":")
                      .at(-1) ?? "Original record"}{" "}
                    · {passage.variant}
                  </span>
                </summary>
                <blockquote>{passage.exact_text}</blockquote>
                <OriginalButton
                  disabled={!!workspace.busy}
                  onClick={() => void workspace.inspect(passage.source_id)}
                >
                  Inspect cited source
                </OriginalButton>
              </details>
            ))}
          </div>
          {!!answer.call_ids.length && (
            <details className="reply-feedback">
              <summary>Something off? Review this answer</summary>
              <p className="meta">
                Identify the issue first. This does not silently change memory.
              </p>
              <label>
                What needs attention?
                <select
                  value={diagnosis}
                  onChange={(e) => setDiagnosis(e.target.value)}
                >
                  <option value="unclear">Help me identify the issue</option>
                  <option value="memory">A memory is wrong</option>
                  <option value="world_change">Something has changed</option>
                  <option value="retrieval">
                    Relevant evidence is missing
                  </option>
                  <option value="generation">
                    The interpretation is wrong
                  </option>
                  <option value="style">The answer style</option>
                  <option value="operation">An operation failed</option>
                </select>
              </label>
              <Button
                variant="outline"
                disabled={!!workspace.busy}
                onClick={() => void workspace.feedback(turn, diagnosis)}
              >
                Review feedback
              </Button>
            </details>
          )}
          <p className="meta answer-note">
            Source references are checked. Review the interpretation; generated
            replies are not learned as evidence.
          </p>
        </m.div>
      ) : turn.error ? (
        <div className="reply error-card" role="alert">
          <strong>The answer could not finish</strong>
          <p>{turn.error}</p>
          <p className="meta">
            A service failure does not establish that a fact is unknown.
          </p>
          <Button
            variant="outline"
            disabled={!!workspace.busy}
            onClick={() => void workspace.ask(turn.request)}
          >
            Try question again
          </Button>
        </div>
      ) : (
        <Activity label="Reading evidence and checking the answer" />
      )}
    </article>
  );
}

export function Conversation({
  workspace: w,
  goSources,
}: {
  workspace: Workspace;
  goSources: () => void;
}) {
  const [intent, setIntent] = useState("ask");
  const [question, setQuestion] = useState("");
  const [note, setNote] = useState("");
  const [formatted, setFormatted] = useState("");
  const [representation, setRepresentation] =
    useState<Representation>("sources");
  const [saved, setSaved] = useState(false);
  const noteId = useRef(crypto.randomUUID());
  const questionIndex = useRef(0);
  const composer = useRef<HTMLTextAreaElement>(null);
  const end = useRef<HTMLDivElement>(null);
  function changeNote(value: string, variant = false) {
    noteId.current = crypto.randomUUID();
    setSaved(false);
    if (variant) setFormatted(value);
    else setNote(value);
  }
  async function submit() {
    if (w.busy) return;
    if (intent === "ask") {
      if (!question.trim()) return;
      await w.ask({ namespace: w.namespace, question, representation });
    } else {
      if (!note.trim()) return;
      const receipt = await w.run("Preserving your original note", () =>
        w.importContent(
          JSON.stringify({
            record_id: `note-${noteId.current}`,
            raw_transcript: note,
            formatted_text: formatted || null,
            metadata: null,
          }) + "\n",
        ),
      );
      if (receipt) {
        setNote("");
        setFormatted("");
        noteId.current = crypto.randomUUID();
        setSaved(true);
      }
    }
  }
  async function sampleQuestion() {
    const data = await w.run("Loading a sample question", () =>
      w.session.request<{ questions: string[] }>("/trial/questions"),
    );
    if (data) {
      setQuestion(
        data.questions[questionIndex.current++ % data.questions.length],
      );
      setIntent("ask");
      composer.current?.focus();
    }
  }
  return (
    <div className="conversation-page">
      {!w.turns.length ? (
        <div className="welcome">
          <div className="welcome-mark">
            <Sprout />
            <span className="mark-orbit" />
          </div>
          <span className="eyebrow">A little context goes a long way</span>
          <h1>
            hey jarvis<span>.</span>
            <br />
            <em>Let’s connect the dots.</em>
          </h1>
          <p>
            A place for the thoughts you want to keep,
            <br className="desktop-break" /> and the context you want to come
            back to.
          </p>
          <div className="starter-grid">
            <button
              disabled={!!w.busy}
              onClick={() => {
                setIntent("note");
                composer.current?.focus();
              }}
            >
              <FilePlus2 />
              <strong>Leave a thought</strong>
              <span>Type or paste a transcript</span>
              <ArrowUp className="card-arrow" />
            </button>
            <button disabled={!!w.busy} onClick={() => void sampleQuestion()}>
              <MessageCircle />
              <strong>Ask with context</strong>
              <span>Try a synthetic question</span>
              <ArrowUp className="card-arrow" />
            </button>
            <button disabled={!!w.busy} onClick={goSources}>
              <BookOpen />
              <strong>Follow the evidence</strong>
              <span>See where a memory began</span>
              <ArrowUp className="card-arrow" />
            </button>
          </div>
        </div>
      ) : (
        <>
          <header className="conversation-heading">
            <div>
              <span className="eyebrow">Your current conversation</span>
              <h1>Context, connected.</h1>
            </div>
            <Button
              variant="ghost"
              disabled={!!w.busy}
              onClick={() => w.setTurns([])}
            >
              Clear conversation
            </Button>
          </header>
          <div className="turns" id="ask-result">
            {w.turns.map((turn) => (
              <Reply key={turn.id} turn={turn} workspace={w} />
            ))}
          </div>
          <Button
            className="latest-button"
            variant="ghost"
            onClick={() => end.current?.scrollIntoView({ block: "end" })}
          >
            Latest response
            <ArrowDown />
          </Button>
        </>
      )}
      <div className="composer-wrap" ref={end}>
        <form
          className="composer"
          onSubmit={(e) => {
            e.preventDefault();
            void submit();
          }}
          autoComplete="off"
        >
          <div className="composer-top">
            <Tabs
              value={intent}
              onValueChange={(value) => {
                setIntent(value);
                setSaved(false);
              }}
            >
              <TabsList aria-label="Input purpose">
                <TabsTrigger value="ask">
                  <Sparkles />
                  Ask Jarvis
                </TabsTrigger>
                <TabsTrigger value="note">
                  <FilePlus2 />
                  Save a note
                </TabsTrigger>
              </TabsList>
            </Tabs>
            <span className="composer-scope">
              {intent === "ask"
                ? "Current question only"
                : "Saved in Normal mode"}
            </span>
          </div>
          <label className="sr-only" htmlFor="composer-input">
            {intent === "ask" ? "Ask a question" : "Original transcript"}
          </label>
          <Textarea
            ref={composer}
            id="composer-input"
            value={intent === "ask" ? question : note}
            onChange={(e) =>
              intent === "ask"
                ? setQuestion(e.target.value)
                : changeNote(e.target.value)
            }
            placeholder={
              intent === "ask"
                ? "Hey Jarvis, what did we decide about…"
                : "Paste your transcript, or simply type a thought…"
            }
            maxLength={intent === "ask" ? 512 : 65536}
            disabled={!!w.busy}
            required
            spellCheck={false}
          />
          {intent === "note" && (
            <details className="variant-input">
              <summary>
                Add a formatted version <span>optional · same observation</span>
              </summary>
              <label htmlFor="formatted-input">Formatted transcript</label>
              <Textarea
                id="formatted-input"
                value={formatted}
                onChange={(e) => changeNote(e.target.value, true)}
                maxLength={65536}
                disabled={!!w.busy}
                spellCheck={false}
              />
              <p className="meta">
                Both strings are preserved exactly. Missing capture time stays
                unknown.
              </p>
            </details>
          )}
          <div className="composer-bottom">
            {intent === "ask" ? (
              <label className="representation">
                <BookOpen aria-hidden="true" />
                <span className="sr-only">Answer evidence</span>
                <select
                  value={representation}
                  onChange={(e) =>
                    setRepresentation(e.target.value as Representation)
                  }
                  disabled={!!w.busy}
                >
                  <option value="sources">Original sources</option>
                  <option value="sources_and_memories">
                    Sources + memories
                  </option>
                  <option value="history">All permitted history</option>
                </select>
              </label>
            ) : (
              <span className="meta">Your words stay intact.</span>
            )}
            <Button
              className="send-button"
              type="submit"
              disabled={
                !!w.busy || !(intent === "ask" ? question : note).trim()
              }
            >
              {intent === "ask" ? "Ask" : "Save note"}
              <ArrowUp />
            </Button>
          </div>
        </form>
        {saved && (
          <div className="save-receipt" role="status">
            <Check />
            <span>Note saved. Learning is a separate step.</span>
            <Button variant="link" onClick={goSources}>
              View source
              <ArrowRight />
            </Button>
          </div>
        )}
        <p className="composer-footnote">
          Typed or pasted text stands in for a transcript. No microphone needed.
          <br />
          Live inference is currently limited to approved synthetic samples;
          arbitrary notes remain local.
        </p>
      </div>
      {!w.turns.length && (
        <div className="story-line" aria-label="How Jarvis works">
          <span>
            01 <b>Keep the original</b>
          </span>
          <i />
          <span>
            02 <b>Connect the evidence</b>
          </span>
          <i />
          <span>
            03 <b>Stay in control</b>
          </span>
        </div>
      )}
    </div>
  );
}
