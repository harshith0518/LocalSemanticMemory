# Hey Jarvis — semantic memory

Technical implementation plan for the Jarvis early notes project. Target review: **12 September 2026, afternoon IST**. Primary delivery method: a local application and PostgreSQL database through Docker Compose; hosted model inference may require provider credentials and network access.

**Current state: planning only.** This restart contains documentation and repository hygiene files. The application, database schema, importer, model adapters, CLI, UI and evaluations described here are not implemented. There are no measured product results yet.

The proposed demonstration imports a person's dictations, answers questions or prepares a contextual draft from supported history, and exposes Sources, Correct, Forget and Private. Backend/database/CLI development comes first; a small ordinary-user interface is part of the required result.

## Read in this order

| Document | Purpose |
| --- | --- |
| [PLAN.md](PLAN.md) | Build order, time allocation, milestone gates and scope cuts. |
| [ARCHITECTURE.md](ARCHITECTURE.md) | Shared services, evidence representation, learning, retrieval and repair. |
| [EVALUATION.md](EVALUATION.md) | Cases, deterministic tests, real-model experiments and decision rules. |
| [RUN.md](RUN.md) | Proposed unfamiliar contract and environment prerequisites; no runnable application commands yet. |
| [DECISIONS.md](DECISIONS.md) | Agreed product constraints versus proposed implementation choices. |
| [AGENTS.md](AGENTS.md) | Contribution rules, approval boundaries and truthful progress reporting. |

## Proposed starting stack

| Need | Technology | Why this is enough initially |
| --- | --- | --- |
| Consistent runtime | Ubuntu 24.04 / WSL2, Docker Compose, containerized Python 3.12 | A Linux execution path without changing host Python or requiring deployment. |
| HTTP API and typed boundaries | FastAPI, Pydantic, HTTPX | Small API, validated request/model output contracts and a provider adapter. |
| State and retrieval | PostgreSQL + pgvector; built-in full-text search | One database for sources, claims, revisions, jobs and searchable views. Exact vectors before ANN. |
| DB access and schema changes | SQLAlchemy, psycopg, Alembic | Explicit transactions and reproducible migrations. |
| Developer/unfamiliar CLI | Typer calling the same application services | Import, process, inspect, ask, evaluate and reset without duplicated business rules. |
| Reproducible checks | pytest, HTTPX test client, Ruff, locked dependencies with uv | Cheap contract tests plus separately identified real-model evaluation. |
| Ordinary-user surface | Small HTML/CSS/JavaScript client | Import/status, Ask, Sources and memory controls; richer UI is optional. |

Versions above are candidate major versions, not a resolved dependency lock. Bootstrap must pin compatible packages and image digests. No Redis, separate vector service, graph cluster, autonomous memory framework or Kubernetes is required for the first implementation.

## What must be demonstrated

1. Original records become selective, source-supported memories; raw and formatted variants stay one observation.
2. Information spread across dictations can support a useful answer or draft with citations.
3. Changed facts, tentative statements and conflicting evidence produce different behavior.
4. Correct changes later use; Forget prevents retrieval and relearning; Private neither reads saved personal data nor persists activity.
5. A unfamiliar can import an unfamiliar corpus, inspect actual state, operate the UI and reproduce evaluation.

Approximately 500 development observations and a separate unfamiliar corpus of approximately 500 are required. Eight synthetic Atlas examples in the planning workspace are the starting diagnostic cases, not the complete dataset. DeepSeek is selected for the main model role; [the current shortlist](ARCHITECTURE.md#models-and-repair) compares NVIDIA Nemotron Lightning and Qwen3-8B for memory proposals. Exact model performance, provider access, spend ceiling and retention settings must be verified before live calls.

## History, evidence and AI use

This commit replaces the earlier repository contents with a focused planning baseline. Prior commits remain reachable through normal Git history. Future commits should represent completed, checked milestones; neither timestamps nor results should be manufactured to suggest progress.

These technical documents were prepared with AI assistance, including explainer agents, source research and review. The project's **Phase One positioning and vision must be independently formed and written by the author and preserved before Part Two**. These documents do not fulfill Phase One; its completion is not established in this repository. Do not generate replacement positioning or vision text.

Azure is an optional final experiment after the local review path passes. It is not a dependency of submission. The architecture and evaluation are hypotheses to test, not claims of a best-performing memory system.
