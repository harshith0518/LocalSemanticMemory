# Review and environment contract

**Planning checkpoint: the application is not runnable yet.** No Compose file, Python package, migrations or model integration is present. This file records the review path that implementation must deliver; it does not claim its commands already work.

## Primary review method

Local Docker Compose application and PostgreSQL database. A hosted model provider may require network access and unfamiliar-supplied credentials. Containerizing the app does not make hosted inference offline. Public deployment is optional and must not be necessary to reproduce the submission.

## Environment recommendation

Use Ubuntu 24.04 under WSL2 on Windows, with Docker Desktop's WSL integration, or an existing native Ubuntu installation with Docker Engine and Compose. Linux containers should run the pinned Python runtime, independent of the host's Python version.

For the initial build, retain the current Windows checkout as the single active source directory. Run application/test processes inside Linux containers and copy source into their images; keep database files in named volumes. No second checkout or source migration is needed for this path. If live source bind mounts become necessary, a Linux-filesystem checkout can avoid cross-filesystem overhead; make that a deliberate move instead of maintaining two diverging copies. [Docker WSL guidance](https://docs.docker.com/desktop/features/wsl/best-practices/)

The initial planning inspection found Docker's Linux engine stopped. During environment preparation on 11 September, the existing Docker Desktop installation was started and checked. No runtime installation, source migration, project database or application service was created.

| Readiness check | Observed result |
| --- | --- |
| Windows Docker client / Linux server | Both `28.4.0`; context `desktop-linux`; server reports Linux. |
| Docker Compose CLI | `2.39.2-desktop.1`. |
| WSL integration | Ubuntu-24.04 and docker-desktop running under WSL2; Docker invoked inside Ubuntu reaches client/server `28.4.0`. |
| Registry connectivity | Official `alpine:3.22` image pulled successfully. This tests Docker Hub access, not model-provider or Python-package access. |
| Linux execution and named-volume persistence | One disposable container wrote a synthetic marker; a new container read the identical marker from the volume. Both ran without networking, with a read-only root filesystem and dropped capabilities. |
| Cleanup | Both test containers auto-removed; only the uniquely named readiness volume was removed after its purpose label was checked. Existing containers and volumes were not modified by the probe. |

Probe image digest: `alpine@sha256:14358309a308569c32bdc37e2e0e9694be33a9d99e68afb0f5ff33cc1f695dce`. This is a readiness-test image, not a selected application base image. Host Python remains 3.14; the proposed Python 3.12 application image will be resolved during bootstrap.

Container replacement with a surviving volume was checked. Database durability, Compose service ordering, image builds, migrations, dependency installation and live model access remain untested until their respective implementation milestones. Starting Docker Desktop can resume other existing workloads according to their own restart policies; the readiness probe did not operate on them.

Useful existing-tool checks from Windows PowerShell:

```powershell
wsl --list --verbose
docker version
docker compose version
wsl -d Ubuntu-24.04 -- docker version
```

If the engine is stopped on a later session, use `docker desktop start`, then verify that `docker version` shows both client and server. Ubuntu integration is already working on this host. Do not install a second conflicting Docker daemon inside WSL without deliberately choosing that setup.

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
