import { useEffect, useRef, useState } from "react";
import { flushSync } from "react-dom";
import { LazyMotion, domAnimation, MotionConfig } from "motion/react";
import {
  Activity as ActivityIcon,
  ArrowUpRight,
  BookOpen,
  Brain,
  ChevronRight,
  LockKeyhole,
  Send,
  MessageCircle,
  ShieldCheck,
} from "lucide-react";
import { ApiSession, messageFor, RequestError } from "./lib/api";
import { useWorkspace } from "./lib/use-workspace";
import type { Page, PrivateAnswer } from "./lib/types";
import { Button } from "./components/ui/button";
import { Input } from "./components/ui/input";
import { Textarea } from "./components/ui/textarea";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "./components/ui/tooltip";
import { Activity, SourceDialog, Sprout } from "./components/common";
import { Conversation } from "./components/conversation";
import { Sources } from "./components/sources";
import { Memories } from "./components/memories";
import { Usage } from "./components/usage";
import { Workflow } from "./components/workflow";
import "./workflow.css";

const pages = [
  { id: "conversation", label: "Conversation", icon: MessageCircle },
  { id: "sources", label: "Sources", icon: BookOpen },
  { id: "memories", label: "Memory", icon: Brain },
  { id: "usage", label: "Usage", icon: ActivityIcon },
  { id: "workflow", label: "Workflow & evidence", icon: ShieldCheck },
] as const;
function Normal({
  session,
  page,
  navigate,
}: {
  session: ApiSession;
  page: Page;
  navigate: (page: Page) => void;
}) {
  const w = useWorkspace(session);
  // Navigation is explicit. Merely mounting the shell never reads personal data.
  return (
    <div id="normal-panel" aria-busy={!!w.busy}>
      <div className="workspace-toolbar">
        <form
          id="collection-form"
          onSubmit={(e) => {
            e.preventDefault();
            void w.open();
          }}
          autoComplete="off"
        >
          <label htmlFor="namespace">Collection</label>
          <Input
            id="namespace"
            aria-label="Collection name"
            value={w.namespace}
            onChange={(e) => w.changeNamespace(e.target.value)}
            pattern="[A-Za-z0-9][A-Za-z0-9._-]*"
            minLength={1}
            maxLength={96}
            required
          />
          <Button
            variant="ghost"
            size="sm"
            type="submit"
            disabled={
              !!w.busy || !/^[A-Za-z0-9][A-Za-z0-9._-]{0,95}$/.test(w.namespace)
            }
          >
            Open
            <ArrowUpRight />
          </Button>
        </form>
        <Tooltip>
          <TooltipTrigger asChild>
            <span className="local-badge" tabIndex={0}>
              <ShieldCheck />
              Your local workspace
            </span>
          </TooltipTrigger>
          <TooltipContent>
            Normal mode saves eligible inputs. You control learning and memory
            changes.
          </TooltipContent>
        </Tooltip>
      </div>
      <div className="page-content" key={w.namespace}>
        <nav className="guided-steps" aria-label="Submission walkthrough">
          {(
            [
              ["sources", "1. Import"],
              ["memories", "2. Learn"],
              ["conversation", "3. Ask"],
              ["workflow", "4. Inspect flow"],
              ["usage", "5. Measure"],
            ] as const
          ).map(([id, label]) => (
            <button
              key={id}
              aria-current={page === id ? "step" : undefined}
              onClick={() => navigate(id)}
            >
              {label}
            </button>
          ))}
        </nav>
        <div
          id="feedback"
          className={`notice ${w.notice.error ? "notice-error" : ""}`}
          role={w.notice.error ? "alert" : "status"}
        >
          {w.notice.text}
        </div>
        {w.busy &&
          !(
            page === "conversation" &&
            w.busy === "Reading evidence and checking the answer"
          ) && <Activity label={w.busy} />}
        <div hidden={page !== "conversation"}>
          <Conversation
            key={w.contentVersion}
            workspace={w}
            goSources={() => navigate("sources")}
          />
        </div>
        <div hidden={page !== "sources"}>
          <Sources key={w.contentVersion} workspace={w} />
        </div>
        <div hidden={page !== "memories"}>
          <Memories workspace={w} />
        </div>
        <div hidden={page !== "usage"}>
          <Usage workspace={w} />
        </div>
        <div hidden={page !== "workflow"}>
          <Workflow key={w.contentVersion} workspace={w} />
        </div>
      </div>
      <SourceDialog
        inspection={w.inspection}
        close={() => w.setInspection(undefined)}
      />
    </div>
  );
}
function Private() {
  const [draft, setDraft] = useState("");
  const [turns, setTurns] = useState<
    { id: string; question: string; answer?: PrivateAnswer; error?: string }[]
  >([]);
  const [busy, setBusy] = useState(false);
  const controller = useRef<AbortController | undefined>(undefined);
  useEffect(
    () => () => {
      controller.current?.abort();
    },
    [],
  );
  async function submit() {
    const question = draft.trim();
    if (!question || busy) return;
    const id = crypto.randomUUID();
    setDraft("");
    setBusy(true);
    setTurns((previous) => [...previous.slice(-7), { id, question }]);
    const request = new AbortController();
    controller.current = request;
    try {
      const response = await fetch("/private/ask", {
        method: "POST",
        cache: "no-store",
        credentials: "omit",
        redirect: "error",
        headers: {
          "Content-Type": "application/json",
          "X-Jarvis-Mode": "private",
        },
        body: JSON.stringify({ question }),
        signal: AbortSignal.any([request.signal, AbortSignal.timeout(60000)]),
      });
      const result = await response.json();
      if (!response.ok)
        throw new RequestError(
          typeof result.reason === "string"
            ? result.reason
            : "operation_failed",
        );
      setTurns((previous) =>
        previous.map((turn) =>
          turn.id === id ? { ...turn, answer: result as PrivateAnswer } : turn,
        ),
      );
    } catch (error) {
      if (!(error instanceof DOMException && error.name === "AbortError"))
        setTurns((previous) =>
          previous.map((turn) =>
            turn.id === id ? { ...turn, error: messageFor(error) } : turn,
          ),
        );
    } finally {
      if (controller.current === request) {
        controller.current = undefined;
        setBusy(false);
      }
    }
  }
  return (
    <div id="private-panel" className="private-page">
      <div className="private-symbol">
        <LockKeyhole />
      </div>
      <span className="eyebrow">A thought can stay a thought</span>
      <h1>
        Some things
        <br />
        <em>can just stay here.</em>
      </h1>
      <p>
        Saved sources and memories are not read in Private mode.
        <br />
        Ask the configured model directly. Jarvis does not save this text or its
        reply, and clears both when you leave.
      </p>
      {!!turns.length && (
        <section className="private-turns" aria-live="polite">
          {turns.map((turn) => (
            <article key={turn.id}>
              <p className="private-question">{turn.question}</p>
              {turn.answer ? (
                <div className="private-answer">
                  <p>{turn.answer.text}</p>
                  <small>
                    {turn.answer.model} · {turn.answer.elapsed_ms} ms ·{" "}
                    {turn.answer.input_tokens} in / {turn.answer.output_tokens}{" "}
                    out
                  </small>
                </div>
              ) : turn.error ? (
                <p className="error-card" role="alert">
                  {turn.error}
                </p>
              ) : (
                <p className="meta">Thinking…</p>
              )}
            </article>
          ))}
        </section>
      )}
      <form
        className="private-composer"
        onSubmit={(event) => {
          event.preventDefault();
          void submit();
        }}
        autoComplete="off"
      >
        <label htmlFor="private-draft">Direct question</label>
        <Textarea
          id="private-draft"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(event) => {
            if (
              event.key === "Enter" &&
              !event.shiftKey &&
              !event.nativeEvent.isComposing
            ) {
              event.preventDefault();
              void submit();
            }
          }}
          placeholder="Ask without memory context…"
          autoComplete="off"
          spellCheck={false}
          maxLength={512}
          disabled={busy}
          required
        />
        <Button type="submit" disabled={busy || !draft.trim()}>
          Submit
          <Send />
        </Button>
      </form>
      <div className="private-caption">
        <LockKeyhole />
        <span>No database context · no source or memory is created</span>
      </div>
      <Button
        variant="outline"
        onClick={() => {
          controller.current?.abort();
          setDraft("");
          setTurns([]);
          setBusy(false);
        }}
        disabled={!draft && !turns.length}
      >
        Clear private chat
      </Button>
      <p className="meta">
        The current question is sent to the configured hosted provider under its
        data terms. Private calls are transient and are not included in the
        saved Usage page. Enter sends; Shift+Enter adds a line.
      </p>
    </div>
  );
}

export default function App() {
  const [privateMode, setPrivateMode] = useState(false);
  const [privateVersion, setPrivateVersion] = useState(0);
  const [page, setPage] = useState<Page>("conversation");
  function navigate(next: Page) {
    setPage(next);
    window.scrollTo({ top: 0, behavior: "instant" });
  }
  const [connected, setConnected] = useState<boolean>();
  const [session, setSession] = useState(() => new ApiSession());
  const sessionRef = useRef(session);
  sessionRef.current = session;
  function switchMode(next: boolean) {
    sessionRef.current.dispose();
    setPrivateMode(next);
    setPage("conversation");
    if (!next) setSession(new ApiSession());
  }
  useEffect(() => {
    const controller = new AbortController();
    void fetch("/ready", {
      cache: "no-store",
      credentials: "omit",
      redirect: "error",
      signal: AbortSignal.any([controller.signal, AbortSignal.timeout(5000)]),
    })
      .then((response) => response.json())
      .then((result) => setConnected(result.status === "ready"))
      .catch(() => {
        if (!controller.signal.aborted) setConnected(false);
      });
    function hide() {
      sessionRef.current.dispose();
      flushSync(() => {
        setPrivateMode(true);
        setPrivateVersion((previous) => previous + 1);
        setPage("conversation");
      });
    }
    function show(event: PageTransitionEvent) {
      if (event.persisted) hide();
    }
    window.addEventListener("pagehide", hide);
    window.addEventListener("pageshow", show);
    return () => {
      controller.abort();
      window.removeEventListener("pagehide", hide);
      window.removeEventListener("pageshow", show);
    };
  }, []);
  const current = pages.find((item) => item.id === page)!;
  return (
    <MotionConfig reducedMotion="user">
      <LazyMotion features={domAnimation} strict>
        <TooltipProvider delayDuration={300}>
          <div className={`app-shell ${privateMode ? "is-private" : ""}`}>
            <a className="skip-link" href="#workspace">
              Skip to workspace
            </a>
            <aside className="sidebar">
              <button
                className="wordmark"
                aria-label="Jarvis home"
                onClick={() => navigate("conversation")}
              >
                <Sprout />
                <span>
                  jarvis<span className="wordmark-dot">.</span>
                </span>
              </button>
              <div className="sidebar-intro">
                <span className="eyebrow">Your context, connected.</span>
                <p>
                  Small thoughts.
                  <br />A fuller picture.
                </p>
              </div>
              <nav aria-label="Workspace pages">
                {pages.map((item) => (
                  <button
                    key={item.id}
                    aria-current={
                      page === item.id && !privateMode ? "page" : undefined
                    }
                    disabled={privateMode}
                    onClick={() => navigate(item.id)}
                  >
                    <item.icon />
                    <span>{item.label}</span>
                    {page === item.id && !privateMode && (
                      <ChevronRight className="nav-chevron" />
                    )}
                  </button>
                ))}
              </nav>
              <div className="sidebar-bottom">
                <div className="sidebar-story">
                  <Sprout />
                  <p>
                    Keep the words.
                    <br />
                    Find the meaning.
                    <br />
                    <em>Keep the choice.</em>
                  </p>
                </div>
                <span className="prototype-label">
                  A semantic memory prototype
                </span>
              </div>
            </aside>
            <div className="workspace-shell">
              <header className="topbar">
                <div className="breadcrumb">
                  <span>Workspace</span>
                  <ChevronRight />
                  <strong>{privateMode ? "Private" : current.label}</strong>
                </div>
                <fieldset className="mode-switch">
                  <legend className="sr-only">Privacy mode</legend>
                  <label>
                    <input
                      type="radio"
                      name="mode"
                      checked={!privateMode}
                      onChange={() => switchMode(false)}
                    />
                    Normal
                  </label>
                  <label>
                    <input
                      type="radio"
                      name="mode"
                      checked={privateMode}
                      onChange={() => switchMode(true)}
                    />
                    <LockKeyhole />
                    Private
                  </label>
                </fieldset>
              </header>
              <main id="workspace" tabIndex={-1}>
                {privateMode ? (
                  <Private key={privateVersion} />
                ) : (
                  <Normal session={session} page={page} navigate={navigate} />
                )}
              </main>
              <footer className="workspace-footer">
                <span className={`connection ${connected ? "connected" : ""}`}>
                  <i />
                  {connected === undefined
                    ? "Checking connection"
                    : connected
                      ? "Workspace connected"
                      : "Workspace unavailable"}
                </span>
                <span>Evidence before assumptions.</span>
              </footer>
            </div>
          </div>
        </TooltipProvider>
      </LazyMotion>
    </MotionConfig>
  );
}
