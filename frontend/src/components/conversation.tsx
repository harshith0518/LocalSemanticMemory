import { useRef, useState } from "react";
import { m } from "motion/react";
import {
  ArrowDown,
  ArrowRight,
  ArrowUp,
  BookOpen,
  Check,
  Cpu,
  FilePlus2,
  MessageCircle,
  Sparkles,
} from "lucide-react";
import { Button } from "./ui/button";
import { Textarea } from "./ui/textarea";
import { Tabs, TabsList, TabsTrigger } from "./ui/tabs";
import { Activity, OriginalButton, sourceLabel, Sprout } from "./common";
import type { Workspace } from "@/lib/use-workspace";
import type { ModelSetup, Representation, Turn } from "@/lib/types";
import { errors } from "@/lib/api";
import { RequestMetrics } from "./request-metrics";
import "./conversation-help.css";

const retentionReasons: Record<string, string> = {
  general_request:
    "This asks for general information without adding a personal fact.",
  personal_question: "This asks about your context without adding a new fact.",
  useful_assertion:
    "This includes personal or project information worth checking for future use.",
  hypothetical: "A hypothetical example does not establish a fact about you.",
  one_off: "This is a one-time request without lasting personal context.",
  small_talk: "This is conversational, without a lasting fact to learn.",
  ambiguous: "The meaning needs clarification before anything can be learned.",
  current_information:
    "This asks for current information without adding a personal fact.",
  clock: "The date or time can be answered without saving a personal fact.",
};

function Reply({ turn, workspace }: { turn: Turn; workspace: Workspace }) {
  const [diagnosis, setDiagnosis] = useState("unclear");
  const answer = turn.answer;
  const assessment = turn.learning?.assessment;
  const assessmentFailed =
    assessment?.status === "failed" ||
    (!turn.learning?.source_id && turn.learning?.status === "failed");
  const assessmentWaiting = assessment?.status === "running" && !!turn.timing;
  const assessmentStopped = assessmentFailed || assessmentWaiting;
  return (
    <article className="conversation-turn">
      <div className="user-message">
        <span className="eyebrow">You</span>
        <p>{turn.question}</p>
      </div>
      {assessmentFailed && (
        <div
          className="message-learning message-learning-warning"
          role="status"
        >
          <p>Memory check could not finish · No message was saved</p>
          <p className="meta">
            {turn.learningError ??
              errors[
                assessment?.error_code ?? turn.learning?.error_code ?? ""
              ] ??
              "The check did not establish whether this message contains a lasting fact."}
          </p>
        </div>
      )}
      {assessmentWaiting && (
        <div
          className="message-learning message-learning-warning"
          role="status"
        >
          <p>The memory check is still running · No message was saved</p>
          <p className="meta">Check progress to resume this same request.</p>
        </div>
      )}
      {turn.learning?.status === "not_saved" &&
        !assessmentFailed &&
        assessment?.status !== "running" && (
          <div className="message-learning" role="status">
            <p>Nothing new to remember · Only in this chat</p>
            <p className="meta">
              No source or memory saved.
              {assessment?.decision?.reason &&
                retentionReasons[assessment.decision.reason] &&
                ` ${retentionReasons[assessment.decision.reason]}`}
            </p>
          </div>
        )}
      {turn.learning?.source_id && (
        <div className="message-learning" role="status">
          <p>
            <Check size={16} aria-hidden="true" /> Message saved ·{" "}
            {turn.learning.decision === "extracted"
              ? `${turn.learning.revision_ids.length} memory change(s) recorded`
              : turn.learning.decision === "duplicate"
                ? "Already known — no new memory needed"
                : turn.learning.decision === "no_memory"
                  ? "No lasting fact to learn"
                  : turn.learning.decision === "needs_clarification"
                    ? "More detail needed before learning; name the project or fact explicitly"
                    : turn.learning.status === "cancelled"
                      ? "Learning cancelled"
                      : turn.learning.status === "failed"
                        ? "Learning did not finish"
                        : "Learning pending"}
          </p>
          {(turn.learning.error_code || turn.learningError) && (
            <p className="meta">
              {turn.learningError ??
                errors[turn.learning.error_code!] ??
                turn.learning.error_code}
            </p>
          )}
          <OriginalButton
            disabled={!!workspace.busy}
            onClick={() => void workspace.inspect(turn.learning!.source_id!)}
          >
            View saved message
          </OriginalButton>
          {(["pending", "running", "failed"].includes(turn.learning.status) ||
            turn.learningError) && (
            <Button
              variant="link"
              disabled={!!workspace.busy}
              onClick={() => void workspace.retryLearning(turn)}
            >
              Retry learning
            </Button>
          )}
        </div>
      )}
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
                  general: "General knowledge · not from your notes",
                  mixed: "Recorded context and general explanation",
                  clock: "From the application clock",
                }[answer.status]
              }
            </span>
          </div>
          {answer.notice && (
            <p className="meta answer-notice">{answer.notice}</p>
          )}
          {answer.status === "mixed" && (
            <h3 className="answer-section-heading">
              From your recorded evidence
            </h3>
          )}
          <p className="reply-text">{answer.text}</p>
          {answer.retrieval && answer.status !== "clock" && (
            <p className="meta">
              {answer.model ? "Sent to answer model: " : "Selected context: "}
              {answer.retrieval.sources_reviewed}
              {answer.retrieval.eligible_sources !== null
                ? ` of ${answer.retrieval.eligible_sources}`
                : ""}{" "}
              eligible notes
              {" and "}
              {answer.retrieval.memories_reviewed}
              {answer.retrieval.eligible_memories !== null
                ? ` of ${answer.retrieval.eligible_memories}`
                : ""}{" "}
              learned memories. These counts describe supplied context, not a
              guarantee that the model used every item correctly.
              {answer.retrieval.partial ? " Partial collection review." : ""}
              {answer.retrieval.query_expanded
                ? " Also searched alternative wording."
                : ""}
            </p>
          )}
          <div className="citations">
            {answer.citations.map((passage, index) => (
              <details key={`${passage.source_id}-${index}`}>
                <summary>
                  <BookOpen aria-hidden="true" />
                  <span>
                    Original:{" "}
                    {(() => {
                      const source = answer.sources.find(
                        (item) => item.id === passage.source_id,
                      );
                      return source ? sourceLabel(source) : "Recorded source";
                    })()}{" "}
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
          {answer.general_text && (
            <section
              className="general-explanation"
              aria-label="General explanation"
            >
              <h3>General explanation · not from your notes</h3>
              <p className="reply-text">{answer.general_text}</p>
              <p className="meta">
                Uses general model knowledge; not verified by live web search
                and not saved as a memory. Source citations support the recorded
                context above.
              </p>
            </section>
          )}
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
            onClick={() => void workspace.ask(turn.request, turn)}
          >
            Try question again
          </Button>
        </div>
      ) : assessmentStopped ? (
        <div className="reply assessment-actions">
          <p className="meta">
            Answering is paused until the message check finishes.
          </p>
          <Button
            variant="outline"
            disabled={!!workspace.busy}
            onClick={() => void workspace.ask(turn.request, turn)}
          >
            {assessmentWaiting ? "Check progress" : "Retry memory check"}
          </Button>
        </div>
      ) : (
        <Activity
          label={workspace.busy || "Reading evidence and checking the answer"}
        />
      )}
      {(answer || turn.error || (assessmentStopped && turn.timing)) && (
        <RequestMetrics turn={turn} />
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
  const [representation, setRepresentation] = useState<Representation>("auto");
  const [saved, setSaved] = useState(false);
  const [setup, setSetup] = useState<ModelSetup>();
  const [helpVisible, setHelpVisible] = useState(false);
  const [showcases, setShowcases] = useState<
    { title: string; request: string; category: string }[]
  >([]);
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
      if (
        /^(?:hello|hi|hey)(?:\s+jarvis)?(?:[, ]+what (?:are you doing|can you do))?[.!?\s]*$/i.test(
          question.trim(),
        )
      ) {
        setHelpVisible(true);
      } else {
        setHelpVisible(false);
      }
      setQuestion("");
      await w.ask({
        namespace: w.namespace,
        question,
        representation,
        timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
      });
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
            Save your notes. Ask about what happened.
            <br className="desktop-break" /> Check the original evidence behind
            every answer.
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
              onClick={w.clearConversation}
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
        {helpVisible && (
          <section className="setup-card" role="status">
            <strong>Hello! I help you find the details in your notes.</strong>
            <p>
              Share a fact or ask a question here. Questions, small talk and
              one-time instructions stay in this chat. Messages with useful
              personal or project facts are saved and checked for learning.
              Answers link back to evidence. I can recall supported details and
              draft text; I do not send messages or perform external actions.
            </p>
            <small>
              This help text is built in. Your submitted message and its
              learning and answer results appear above.
            </small>
          </section>
        )}
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
                ? "Useful context remembered"
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
            onKeyDown={(event) => {
              if (
                intent === "ask" &&
                event.key === "Enter" &&
                !event.shiftKey &&
                !event.nativeEvent.isComposing
              ) {
                event.preventDefault();
                void submit();
              }
            }}
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
              <div className="composer-controls">
                <label
                  className="model-selector"
                  title="Select the model for the next request"
                >
                  <Cpu aria-hidden="true" />
                  <span>Model</span>
                  <select
                    aria-label="Answer model"
                    value={w.modelSetup?.responder?.model ?? ""}
                    onChange={(e) => void w.changeModel(e.target.value)}
                    disabled={!!w.busy}
                  >
                    {(
                      w.modelSetup?.available_models ?? [
                        w.modelSetup?.responder?.model ?? "gemini-3.6-flash",
                      ]
                    ).map((m) => (
                      <option key={m} value={m}>
                        {m}
                      </option>
                    ))}
                  </select>
                </label>
                <details className="context-options">
                  <summary>
                    Context:{" "}
                    {representation === "auto"
                      ? "automatic"
                      : representation === "sources"
                        ? "relevant notes"
                        : representation === "sources_and_memories"
                          ? "notes and memories"
                          : "whole collection"}
                  </summary>
                  <p>
                    Automatic checks notes and learned memories, reviews
                    complete small collections, and searches alternative wording
                    for larger collections. General knowledge is labelled
                    separately when your notes do not answer.
                  </p>
                  <label className="representation">
                    <BookOpen aria-hidden="true" />
                    <span className="sr-only">Answer evidence</span>
                    <select
                      aria-label="Answer evidence"
                      value={representation}
                      onChange={(e) =>
                        setRepresentation(e.target.value as Representation)
                      }
                      disabled={!!w.busy}
                    >
                      <option value="auto">Automatic (recommended)</option>
                      <option value="sources">Relevant notes only</option>
                      <option value="sources_and_memories">
                        Notes + saved memories
                      </option>
                      <option value="history">
                        Whole collection (small collections only)
                      </option>
                    </select>
                  </label>
                  <p>
                    Notes + memories adds learned facts and their supporting
                    notes. Whole collection is a small-corpus baseline with a
                    strict size limit. All options respect Forget and
                    corrections.
                  </p>
                </details>
              </div>
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
          Jarvis checks what is worth remembering. Questions and one-time requests
          stay in this chat; useful personal or project facts are checked for
          learning, repeats and updates. AI replies are not learned as evidence.
          Private chat does not read or save workspace context.
        </p>
        <details className="setup-card">
          <summary>Model setup and 30 showcase questions</summary>
          <p>
            Start in Sources: import the sample or the 540-note fictional
            corpus. In Memory, choose Process sources, then return here. A
            Normal Ask message is first assessed for useful personal or project
            facts. Eligible messages are saved and checked for new information.
          </p>
          <div className="setup-actions">
            <Button
              type="button"
              variant="outline"
              disabled={!!w.busy}
              onClick={() =>
                void w.run("Checking model configuration", async () => {
                  const data =
                    await w.session.request<ModelSetup>("/inference");
                  setSetup(data);
                  w.setModelSetup(data);
                })
              }
            >
              Check model setup
            </Button>
            <Button
              type="button"
              variant="outline"
              disabled={!!w.busy}
              onClick={() =>
                void w.run("Loading showcase questions", async () => {
                  const data = await w.session.request<{
                    cases: typeof showcases;
                  }>("/trial/showcase");
                  setShowcases(data.cases);
                })
              }
            >
              Browse 30 showcase cases
            </Button>
          </div>
          {setup && (
            <div role="status">
              <p>
                Selected model: <b>{setup.responder.model}</b>. Change it beside
                the composer; switching only updates configuration and does not
                contact a model until the next request.{" "}
                {setup.responder.enabled && setup.responder.key_configured
                  ? "Configured for live requests; this check does not contact or certify the provider."
                  : "Not ready: enable inference and configure the documented key in .env, then restart the API and worker."}
              </p>
              <p>
                {setup.responder.unfamiliar_mode
                  ? "Unfamiliar opt-in is enabled for Normal-mode notes and questions."
                  : setup.responder.unfamiliar_questions &&
                      setup.responder.unfamiliar_sources
                    ? "Flexible demo questions and locally entered synthetic sources are enabled."
                    : setup.responder.unfamiliar_questions
                      ? "Flexible questions are enabled over the checked-in synthetic sources."
                      : "Synthetic-only mode: use bundled sources and showcase questions. New questions need explicit synthetic-question approval."}
              </p>
              <p>{setup.warning}</p>
            </div>
          )}
          {!!showcases.length && (
            <label className="showcase-picker">
              Choose a showcase question
              <select
                defaultValue=""
                onChange={(e) => {
                  setQuestion(e.target.value);
                  setIntent("ask");
                  composer.current?.focus();
                }}
              >
                <option value="" disabled>
                  30 checks, not promised successes
                </option>
                {showcases.map((c) => (
                  <option key={c.request} value={c.request}>
                    {c.title} ({c.category})
                  </option>
                ))}
              </select>
            </label>
          )}
        </details>
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
