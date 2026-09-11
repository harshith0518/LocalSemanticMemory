# Hey Jarvis — semantic memory

Technical implementation plan for the Jarvis early notes project. Target review: **12 September 2026, afternoon IST**. Primary delivery method: a local application and PostgreSQL database through Docker Compose; hosted model inference may require provider credentials and network access.

**Current state: source workspace, memory-processing contracts and evidence search.** Open [Hey Jarvis](http://127.0.0.1:8000/) to import dictations, search original records and inspect paired sources or source-linked memories/history. Search works without a model key or prior extraction. The browser is the primary user surface. S07 uses deterministic proposals for contract evidence; live extraction/answer quality remains unverified pending the synthetic-only NVIDIA decision. [RUN.md](RUN.md#s08-evidence-search) explains search, actual checks and limits. Generated source-history answers and full Correct/Forget remain open work.

The proposed demonstration imports a person's dictations, answers questions or prepares a contextual draft from supported history, and exposes Sources, Correct, Forget and Private. The minimal browser interface is now the primary review surface; further backend milestones must connect their user actions there.

## Read in this order

| Document | Purpose |
| --- | --- |
| [todo.md](todo.md) | Completed, ongoing and pending work; current blocker and the next action. |
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

At this handoff, S05 is approved and implemented with results in RUN.md. The user also explicitly authorized merging the tested work from `dev` into `main` and pushing it. Implementation continues on `dev`; subsequent merges still follow the user's review/authorization. The user requested an S03–S05 audit, publication to `main`, and starting S06, then explicitly brought the minimal frontend forward so user workflows no longer require the CLI. The audit and bounded S06 proposal are recorded in [RUN.md](RUN.md#s06-readiness-audit) and [PLAN.md](PLAN.md#s06-bounded-bootstrap-proposal). Provider access, retention/no-training terms and the live-call budget remain unsettled; no external inference is authorized by the presence of a key. Final Phase One documents remain with the author; repository inclusion/mechanical checks remain open. The two chat-generated [Phase One drafts](docs/part-one/README.md#ai-assisted-drafts-supplied-in-chat) retain their separate provenance.

Suggested discussion-chat starting message:

> Read the visual PDF and the repository's AGENTS.md, todo.md, README.md, DECISIONS.md, PLAN.md, ARCHITECTURE.md, EVALUATION.md and RUN.md. Help me understand the diagrams and compare alternatives using page/node IDs. Record agreed decisions in the Markdown files. Review the next bounded milestone in todo.md with me and prepare a clear instruction for Codex CLI once I approve it. Preserve documented open items and distinguish proposed behavior from verified results.

Suggested CLI handoff, after scope approval:

> Read AGENTS.md and the planning documents linked by README.md. Check the actual Git state, approved scope and CLI/Docker access. Implement only the approved milestone through shared services. Run relevant checks, update todo.md, commit, push and verify the remote result. Ask before material changes outside the approved scope. Do not treat an AI-assisted Phase One draft, environment probe or mock model as completed submission or product evidence.

## Using the visual guide

The PDF is a visual companion: short labels inside shapes, a consistent role-color legend, named decision branches, and the same Atlas/Mira examples across pages. Use identifiers such as **09.D** (candidate union) or **14.H** (reply-release guard) when asking questions. Its page-map cards and MAP links navigate within the PDF; every page ends with three clickable reference cards and its supporting Markdown link. The [source register](docs/visual-guide-references.md) records exact brief locators, page-by-page references and evidence limits. Page 2 explicitly maps the project's broad term to our included facts, preferences and useful episodes; automatic procedural learning is deferred.

The diagram snapshot is dated 11 September 2026, revised from visual-guide checkpoint `3eca8fb` to clarify the existing episodic scope and add verified references. Repository reference cards follow `dev`; page 18 records assistant commits to `dev` and user-controlled merges to `main`. It depicts requirements and proposed behavior, with explicit status tags. It does not change the application architecture, close S01, approve S03 or provide measured product results. Markdown and tested code remain the precise, evolving implementation record.

The S06 readiness audit reviewed all 18 pages against the implemented boundaries. The PDF's DeepSeek labels on pages 9–11 and 16, page 18's pending S03 status, and its implementation-pending footer are historical: S03–S05 are implemented and Kimi K3 is now the response candidate. The diagrams still guide the sequence. S07 processing contracts and S08 evidence search now have acceptance evidence; generated answers, full controls and live model evaluation remain pending. The minimal source workspace was brought forward from S10 at the user's request. [Page-to-code audit and actual checks](RUN.md#s06-readiness-audit)

To regenerate the PDF with Python and ReportLab installed, run `python tools/build_visual_guide.py` from the repository root. It writes the PDF under `output/pdf/`, regenerates `docs/visual-guide-references.md` from `tools/visual_guide_sources.py`, and writes temporary layout metadata under `tmp/pdfs/`. Generation was checked with ReportLab 4.4.9 and the output rendered with Poppler for visual review. This script is documentation tooling, separate from the S03 backend.

The following supporting resources remain in the **parent planning workspace**, outside this Git repository. These paths are relative to the current implementation checkout. They are not automatically present in a fresh clone or isolated worktree; use the original planning workspace to access them. The implementation decisions and acceptance gates are already consolidated in this repository.

| Supporting material | Existing location |
| --- | --- |
| Project brief and extracted text | `../reference/Jarvis_Golden_Goose_Task_Final.pdf` and `.txt` |
| Eight synthetic source observations | `../reference-examples/sample-dictations.jsonl` |
| Separate evaluator questions/labels | `../reference-examples/sample-evaluation-cases.json` — never ingest as memory |
| Deeper implementation research | `../research/implementation-strategy.md`, `implementation-evaluation.md`, `implementation-models.md` |
| Educational memory blueprint | `../jarvis-memory-blueprint.html` |

S05 copied and hash-verified the [eight observations](data/synthetic/sample-dictations.jsonl) and [separate evaluator labels](eval/fixtures/sample-evaluation-cases.json). Fresh clones include both; only the JSONL is source input. These eight observations do not satisfy the approximately 500-observation corpus requirement. The course and research artifacts remain background references.

## Proposed starting stack

| Need | Technology | Why this is enough initially |
| --- | --- | --- |
| Consistent runtime | Ubuntu 24.04 / WSL2, Docker Compose, containerized Python 3.12 | A Linux execution path without changing host Python or requiring deployment. |
| HTTP API and typed boundaries | FastAPI, Pydantic, HTTPX | Small API, validated request/model output contracts and a provider adapter. |
| State and retrieval | PostgreSQL + pgvector; built-in full-text search | One database for sources, claims, revisions, jobs and searchable views. Exact vectors before ANN. |
| DB access and schema changes | SQLAlchemy, psycopg, Alembic | Explicit transactions and reproducible migrations. |
| Optional developer CLI | Typer calling the same application services | Diagnostics and automation through the same services; ordinary-user actions use the browser. |
| Reproducible checks | pytest, HTTPX test client, Ruff, locked dependencies with uv | Cheap contract tests plus separately identified real-model evaluation. |
| Ordinary-user surface | Small HTML/CSS/JavaScript client served by FastAPI | Import, Sources, Search, processing/status, Memories/history and Normal/Private switching; add Ask and complete controls when their backend gates pass. No separate frontend server/build step. |

The S03 backend versions are now resolved in `uv.lock` and image digests are pinned in Dockerfile/Compose; retrieval and full Ask/control flows describe later work. Browser tests use an optional separately locked Playwright dependency; end users need neither Node nor Python installed. No Redis, separate vector service, graph cluster, autonomous memory framework or Kubernetes is required for the first implementation.

## What must be demonstrated

1. Original records become selective, source-supported memories; raw and formatted variants stay one observation.
2. Information spread across dictations can support a useful answer or draft with citations.
3. Changed facts, tentative statements and conflicting evidence produce different behavior.
4. Correct changes later use; Forget prevents retrieval and relearning; Private neither reads saved personal data nor persists activity.
5. A unfamiliar can import an unfamiliar corpus, inspect actual state, operate the UI and reproduce evaluation.

Approximately 500 development observations and a separate unfamiliar corpus of approximately 500 are required. Eight synthetic Atlas examples in the planning workspace are the starting diagnostic cases, not the complete dataset. The user now selected **Kimi K3** as the S06 response candidate, replacing DeepSeek; [the current shortlist](ARCHITECTURE.md#models-and-repair) compares NVIDIA Nemotron Lightning and Qwen3-8B for memory proposals. Exact model performance, provider access, spend ceiling and retention settings must be verified before live calls.

## History, evidence and AI use

Commit `596b034` replaced the earlier repository contents with a focused planning baseline. Prior commits remain reachable through normal Git history. After each meaningful milestone, run relevant checks, update [todo.md](todo.md), commit and push the completed work. Neither timestamps nor results should be manufactured to suggest progress.

These technical documents were prepared with AI assistance, including explainer agents, source research and review. The project's **Phase One positioning and vision must be independently formed and written by the author and preserved before Part Two**. The author's supplied [source notes](docs/part-one/README.md) are preserved with provenance and counts; the author now reports the final documents complete and held separately. They have not been inspected or mechanically checked in this checkout. The author explicitly approved S03 proceeding on that basis. These technical documents do not fulfill Phase One. Do not generate replacement positioning or vision text.

Azure is an optional final experiment after the local review path passes. It is not a dependency of submission. The architecture and evaluation are hypotheses to test, not claims of a best-performing memory system.
