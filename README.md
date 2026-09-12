# Hey Jarvis — semantic memory

Technical implementation plan for the Jarvis early notes project. User-confirmed submission deadline: **Saturday, 12 September 2026, 11:30 pm IST**. Primary delivery method: a local application and PostgreSQL database through Docker Compose; hosted model inference may require provider credentials and network access.

**Latest checkpoint:** 244 PostgreSQL tests and 24/24 browser journeys passed. The 540-record synthetic corpus, 84 separate cases, 30 preselected showcases and explicit unfamiliar opt-in are implemented. Lightning returns cited answers but still has semantic weaknesses. A ten-call Ultra comparison did not justify switching models. The previously running browser container still has inference disabled; preparing new Compose configuration does not activate that existing container. [Actual results and setup distinctions](RUN.md#evening-evaluation-preparation-and-llm-check).

**Current state: an integrated synthetic prototype.** The React browser supports typed/pasted notes, import, source inspection, Search, processing, Memories/history, Ask with citations, Correct, Record a change, Forget, feedback diagnosis, sample/corpus import, usage inspection and Private clearing. API, optional CLI, worker and evaluators share one backend. The approved NVIDIA synthetic allowance is **750 lifetime requests / 10,000,000 accounted tokens / $0 paid authorization**, including retries and conservative unknown-usage reservations; prior usage is not reset. Unfamiliar Normal-mode inputs require a separate, default-off unfamiliar opt-in with the operator's own key and explicit data-terms acknowledgement. Private remains blocked from live inference and saved memory. A working transport or passing contract test does not establish model accuracy. Full live corpus evaluation and final acceptance rehearsal remain open.

The proposed demonstration imports a person's dictations, answers questions or prepares a contextual draft from supported history, and exposes Sources, Correct, Forget and Private. The React browser workspace is the primary review surface; further backend milestones must connect their user actions there.

## Read in this order

| Document | Purpose |
| --- | --- |
| [todo.md](todo.md) | Completed, ongoing and pending work; current blocker and the next action. |
| [Interactive progress and walkthrough guide](docs/project-progress.html) | Local HTML snapshot: milestone status, the complete input-to-memory diagram, storage, worked examples, answer/control flows and walkthrough practice. |
| [Visual memory guide](output/pdf/jarvis-memory-visual-guide.pdf) | 18 diagram pages with colors, shapes, labeled arrows, page/node IDs and clickable navigation. |
| [Phase One source notes](docs/part-one/README.md) | Preserved user-supplied notes, earlier-chat provenance and mechanical word counts; finals are held by the author and reported complete, with repository inclusion/mechanical checks pending. |
| [PLAN.md](PLAN.md) | Build order, time allocation, milestone gates and scope cuts. |
| [ARCHITECTURE.md](ARCHITECTURE.md) | Shared services, evidence representation, learning, retrieval and repair. |
| [EVALUATION.md](EVALUATION.md) | Cases, deterministic tests, real-model experiments and decision rules. |
| [RUN.md](RUN.md) | Tested setup, import/inspection contract, policy commands, persistence and isolated checks. |
| [DECISIONS.md](DECISIONS.md) | Agreed product constraints versus proposed implementation choices. |
| [AGENTS.md](AGENTS.md) | Contribution rules, approval boundaries and truthful progress reporting. |

## Starting a fresh implementation chat

Use this implementation repository as the project folder. The user's updated workflow is a fresh discussion chat for understanding the PDF, resolving doubts and reviewing tradeoffs, followed by Codex CLI for approved implementation work. Application processes still run in the verified Docker Linux environment. The CLI's Windows-versus-WSL location, configuration, authentication and repository access must be checked before coding there; Docker readiness does not verify CLI setup. Keep one active checkout. The repository files carry the working context; each chat/session should read them rather than assume it has the previous conversation.

Implementation continues on `dev`; the user controls subsequent merges into `main`. The latest instruction approves the React workspace redesign on top of the completed S10 measurement work and S11 planning handoff; the existing bounded synthetic-only NVIDIA allowance is unchanged. The current acceptance record is in [RUN.md](RUN.md#s09-controls-and-synthetic-ask); [todo.md](todo.md) distinguishes implemented workflows from open live-quality gates. The 18-page PDF remains a historical design snapshot. Final Phase One documents remain with the author and have not been mechanically checked here; the preserved AI-assisted drafts retain separate provenance.

Suggested discussion-chat starting message:

> Read the visual PDF and the repository's AGENTS.md, todo.md, README.md, DECISIONS.md, PLAN.md, ARCHITECTURE.md, EVALUATION.md and RUN.md. Help me understand the diagrams and compare alternatives using page/node IDs. Record agreed decisions in the Markdown files. Review the next bounded milestone in todo.md with me and prepare a clear instruction for Codex CLI once I approve it. Preserve documented open items and distinguish proposed behavior from verified results.

Suggested CLI handoff, after scope approval:

> Read AGENTS.md and the planning documents linked by README.md. Check the actual Git state, approved scope and CLI/Docker access. Implement only the approved milestone through shared services. Run relevant checks, update todo.md, commit, push and verify the remote result. Ask before material changes outside the approved scope. Do not treat an AI-assisted Phase One draft, environment probe or mock model as completed submission or product evidence.

## Project progress and walkthrough guide

Open [docs/project-progress.html](docs/project-progress.html) in a browser. It works as a local file without Docker, installation or model credentials. It includes a clickable 12-stage learning diagram, the actual PostgreSQL storage map, four source-based teaching examples, retrieval and lifecycle explanations, and 12 expandable walkthrough questions. The print action includes the examples and walkthrough answers.

This is a dated reading view of [todo.md](todo.md), based on application commit `1756069`, not a live status monitor or a substitute for the application. It separates recorded contract acceptance from unresolved live quality, marks teaching examples as intended behavior, and links to the actual failure reports. The HTML is AI-assisted technical preparation, not an independently authored Phase One submission. [Static checks and limitations](RUN.md#html-progress-and-walkthrough-guide)

## Using the visual guide

The PDF is a visual companion: short labels inside shapes, a consistent role-color legend, named decision branches, and the same Atlas/Mira examples across pages. Use identifiers such as **09.D** (candidate union) or **14.H** (reply-release guard) when asking questions. Its page-map cards and MAP links navigate within the PDF; every page ends with three clickable reference cards and its supporting Markdown link. The [source register](docs/visual-guide-references.md) records exact brief locators, page-by-page references and evidence limits. Page 2 explicitly maps the project's broad term to our included facts, preferences and useful episodes; automatic procedural learning is deferred.

The diagram snapshot is dated 11 September 2026, revised from visual-guide checkpoint `3eca8fb` to clarify the existing episodic scope and add verified references. Repository reference cards follow `dev`; page 18 records assistant commits to `dev` and user-controlled merges to `main`. It depicts requirements and proposed behavior, with explicit status tags. It does not change the application architecture, close S01, approve S03 or provide measured product results. Markdown and tested code remain the precise, evolving implementation record.

The S06 readiness audit reviewed all 18 pages against the implemented boundaries. DeepSeek labels and pending implementation statuses in the PDF are historical. S09 now implements the controls/feedback path from pages 12–15 and connects Ask to the browser. PostgreSQL tests establish lifecycle and privacy contracts; actual live results and unresolved quality gates are recorded separately. [Current workflow and evidence](RUN.md#s09-controls-and-synthetic-ask)

To regenerate the PDF with Python and ReportLab installed, run `python tools/build_visual_guide.py` from the repository root. It writes the PDF under `output/pdf/`, regenerates `docs/visual-guide-references.md` from `tools/visual_guide_sources.py`, and writes temporary layout metadata under `tmp/pdfs/`. Generation was checked with ReportLab 4.4.9 and the output rendered with Poppler for visual review. This script is documentation tooling, separate from the S03 backend.

The following supporting resources remain in the **parent planning workspace**, outside this Git repository. These paths are relative to the current implementation checkout. They are not automatically present in a fresh clone or isolated worktree; use the original planning workspace to access them. The implementation decisions and acceptance gates are already consolidated in this repository.

| Supporting material | Existing location |
| --- | --- |
| Project brief and extracted text | `../reference/Jarvis_Golden_Goose_Task_Final.pdf` and `.txt` |
| Eight synthetic source observations | `../reference-examples/sample-dictations.jsonl` |
| Separate evaluator questions/labels | `../reference-examples/sample-evaluation-cases.json` — never ingest as memory |
| Deeper implementation research | `../research/implementation-strategy.md`, `implementation-evaluation.md`, `implementation-models.md` |
| Educational memory blueprint | `../jarvis-memory-blueprint.html` |

S05 copied and hash-verified the [eight observations](data/synthetic/sample-dictations.jsonl) and [separate evaluator labels](eval/fixtures/sample-evaluation-cases.json). Fresh clones include both; only the JSONL is source input. Use **Sources > Try the sample** in the browser to import them without selecting a local file. These eight observations do not satisfy the approximately 500-observation corpus requirement. The existing generated 500-record search stress set is also not the varied corpus; [S11 defines the connected/independent scenario allocation](PLAN.md#s11-corpus-and-semantic-evaluation-handoff). The course and research artifacts remain background references.

## Proposed starting stack

| Need | Technology | Why this is enough initially |
| --- | --- | --- |
| Consistent runtime | Ubuntu 24.04 / WSL2, Docker Compose, containerized Python 3.12 | A Linux execution path without changing host Python or requiring deployment. |
| HTTP API and typed boundaries | FastAPI, Pydantic, HTTPX | Small API, validated request/model output contracts and a provider adapter. |
| State and retrieval | PostgreSQL + pgvector; built-in full-text search | One database for sources, claims, revisions, jobs and searchable views. Exact vectors before ANN. |
| DB access and schema changes | SQLAlchemy, psycopg, Alembic | Explicit transactions and reproducible migrations. |
| Optional developer CLI | Typer calling the same application services | Diagnostics and automation through the same services; ordinary-user actions use the browser. |
| Reproducible checks | pytest, HTTPX test client, Ruff, locked dependencies with uv | Cheap contract tests plus separately identified real-model evaluation. |
| Ordinary-user surface | React 19.3 / TypeScript, shadcn/Radix, Motion and local fonts; built by Vite and served by FastAPI | Conversation, typed notes, Sources/Search, Memory/history/controls, Usage and Normal/Private. Docker builds the assets; no separate runtime frontend server. |

The S03 backend versions are now resolved in `uv.lock` and image digests are pinned in Dockerfile/Compose; retrieval and Ask/control implementations are covered by the current acceptance record. Browser tests use an optional separately locked Playwright dependency; end users need neither Node nor Python installed. No Redis, separate vector service, graph cluster, autonomous memory framework or Kubernetes is required for the first implementation.

## What must be demonstrated

1. Original records become selective, source-supported memories; raw and formatted variants stay one observation.
2. Information spread across dictations can support a useful answer or draft with citations.
3. Changed facts, tentative statements and conflicting evidence produce different behavior.
4. Correct changes later use; Forget prevents retrieval and relearning; Private neither reads saved personal data nor persists activity.
5. A unfamiliar can import an unfamiliar corpus, inspect actual state, operate the UI and reproduce evaluation.

Approximately 500 development observations and a separate unfamiliar corpus of approximately 500 are required. The checked-in [540-record corpus](data/synthetic/corpus-540.jsonl) is deterministic AI-assisted fiction, not independently recorded speech. Questions and expected evidence live separately under `eval/fixtures/` and are never imported as memory. The current Compose configuration explicitly selects **Nemotron Lightning** for responses and extraction; historical Kimi failures are retained, and Ultra is evaluation-only with no fallback. [Observed quality and operational limits](eval/reports/s11-ultra-review.json) are not a completed full-corpus score.

## History, evidence and AI use

Commit `596b034` replaced the earlier repository contents with a focused planning baseline. Prior commits remain reachable through normal Git history. After each meaningful milestone, run relevant checks, update [todo.md](todo.md), commit and push the completed work. Neither timestamps nor results should be manufactured to suggest progress.

These technical documents were prepared with AI assistance, including explainer agents, source research and review. The project's **Phase One positioning and vision must be independently formed and written by the author and preserved before Part Two**. The author's supplied [source notes](docs/part-one/README.md) are preserved with provenance and counts; the author now reports the final documents complete and held separately. They have not been inspected or mechanically checked in this checkout. The author explicitly approved S03 proceeding on that basis. These technical documents do not fulfill Phase One. Do not generate replacement positioning or vision text.

Azure is an optional final experiment after the local review path passes. It is not a dependency of submission. The architecture and evaluation are hypotheses to test, not claims of a best-performing memory system.

### Latest provider diagnostic

The [free-provider comparison](eval/reports/s12-free-provider-review.json) completed with 248 backend and 24 browser tests passing. Google Flash-Lite access works, but live conflict handling still fails; OpenRouter returned a rate limit. These results do not establish final acceptance readiness or a completed 540-record live evaluation. See [the single current tracker](todo.md) and [current runtime limitations](RUN.md#free-provider-comparison-and-current-blocker). Provider adapters are default-off; credentials and personal data are not included in the repository.

## Automated unfamiliar and local submission

Use **RUN.md / Automated unfamiliar: replace keys and continue independently** for exact NVIDIA, Google-free and OpenRouter-free configuration, a real probe, collection import/learning/Ask/inspection, failure handling and paced evaluation. Keys are provider-specific; credentials stay outside Git. The user-facing app runs locally at `http://localhost:8000`; no hosted deployment is required.

**Workflow & evidence** embeds the 12-stage source-to-memory diagram and displays source/claim storage explanations and actual synthetic reports. The machine-readable map is `docs/storage-contract.json`. Use `todo.md` for current gates; the S14 live 30-case baseline had 13 mechanical passes and four operational failures and is not concealed. A configured provider, successful import or passing deterministic tests is not proof that every input was learned correctly. Independently authored Phase One work is a separate requirement; AI-assisted technical documentation does not replace it.
