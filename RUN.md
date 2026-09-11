# Review and environment contract

**Planning checkpoint: the application is not runnable yet.** No Compose file, Python package, migrations or model integration is present. This file records the review path that implementation must deliver; it does not claim its commands already work.

## Primary review method

Local Docker Compose application and PostgreSQL database. A hosted model provider may require network access and unfamiliar-supplied credentials. Containerizing the app does not make hosted inference offline. Public deployment is optional and must not be necessary to reproduce the submission.

## Environment recommendation

Use Ubuntu 24.04 under WSL2 on Windows, with Docker Desktop's WSL integration, or an existing native Ubuntu installation with Docker Engine and Compose. Linux containers should run the pinned Python runtime, independent of the host's Python version.

For WSL development, keep the active checkout in the Linux filesystem, such as `~/projects/ProjectSemanticMemoryJarvis`, when bind mounts are used. Database files belong in a Docker named volume. Avoid two diverging checkouts and double-editing from Windows/WSL. The current planning checkout may remain on Windows until the implementation environment is approved. [Docker WSL guidance](https://docs.docker.com/desktop/features/wsl/best-practices/)

Read-only host inspection on 11 September found Ubuntu-24.04 and Ubuntu registered as WSL2 distributions, both stopped. Docker Desktop/Compose are installed, but the Linux engine was not running. Host Python is 3.14. These are observations, not setup completion. No runtime installation, Docker startup or source migration was performed for this planning commit.

Useful existing-tool checks from Windows PowerShell:

```powershell
wsl --list --verbose
docker version
docker compose version
```

Before the first approved implementation slice, start Docker Desktop, enable the chosen WSL distribution's integration and verify that `docker version` shows both client and server. Do not install a second conflicting Docker daemon inside WSL without deliberately choosing that setup.

## Required final commands and documentation

Implementation must provide and verify the following operations through the CLI and appropriate UI. Exact executable commands will replace this checklist after they work:

1. Configure a documented `.env.example` without committing secrets; identify model IDs, required network access, retention and cost assumptions.
2. Build and start healthy containers; apply migrations exactly once; open the loopback UI.
3. Import raw/formatted records with documented required/optional fields; process pending work; inspect counts, rejected inputs and provenance.
4. Ask Jarvis via UI and CLI; inspect source-supported answers, drafts and unresolved conflicts.
5. Exercise Private, Correct and Forget, including behavior after restart and reimport.
6. Run deterministic tests in an isolated database with no paid calls; separately run real-model evaluation under an explicit budget.
7. Generate inspectable results with commit/model/prompt/config versions, successes and failures, latency, database growth and total cost.
8. Reset only the selected demo/test dataset through an explicit scoped operation; provide safe stop/start instructions that distinguish preserved volumes from destructive reset.

The final README and this file must include a clean-clone walkthrough, corpus import contract, actual results path, known failures, unfamiliar credential options and exact tested release commit. Never present a mock-only run as the live evaluation.

## Container implementation references

- [FastAPI in Docker](https://fastapi.tiangolo.com/deployment/docker/): build an application image rather than depend on an obsolete specialized image.
- [uv in Docker](https://docs.astral.sh/uv/guides/integration/docker/): pin tooling and synchronize the lockfile during builds.
- [Compose startup order](https://docs.docker.com/compose/how-tos/startup-order/): distinguish running services, healthy databases and completed migrations.
