# Phase 1 — Image Factory — Design

**Date:** 2026-07-05
**Status:** Approved design, pre-implementation
**Depends on:** [Modular Odoo Platform — Product Design](2026-07-05-modular-odoo-platform-design.md) §6 (technical architecture), §7 (roadmap), §8 (known bugs)

## 1. Goal

Build and publish **Odoo Community base images** for four versions, multi-arch, via GitHub Actions to GitHub Container Registry (GHCR). This is Phase 1 of the roadmap: multi-version base images exist and are usable on their own, even before the CLI, manifest, or any backend exists.

Scope is deliberately narrow:

- **Community edition only.** Enterprise, OCA, and localization layers are Phase 3 (published layers). This factory bakes no addons — it produces a pure Odoo core base image.
- **Four versions:** 16.0, 17.0, 18.0, 19.0.
- **Two architectures:** `linux/amd64` and `linux/arm64`, served as a manifest list.
- **CI/registry:** GitHub Actions + GHCR (the repo lives at `github.com/aparragithub/odoo-forge`).

## 2. Non-Goals

- No addon collection or baking (that is a client-layer / higher-layer concern).
- No CLI, manifest, or lockfile work (Phase 2).
- No enterprise or OCA layers (Phase 3).
- No per-developer UID/GID remapping logic — the base image bakes a fixed `odoo:1000`; per-OS bind-mount UID concerns belong to the local backend adapter (Phase 2).

## 3. Bugs From `odoo-idp` Not Carried Over (design spec §8)

| Bug | Resolution in the factory |
|---|---|
| `requirements.collected.txt` is a checked-in generated artifact with no freshness enforcement | **Eliminated by omission.** A base image collects no addon requirements. Dependencies come only from Odoo's own `requirements.txt` at the pinned branch (version-correct by definition) plus a small, hand-maintained `extra_requirements.txt`. |
| `ODOO_UID` / `ODOO_GID` build args declared but never passed to `docker buildx build` (images always bake UID/GID 1000) | **Fixed by wiring the args for real.** The CI build passes `--build-arg ODOO_UID`/`ODOO_GID`. The default remains 1000; per-dev remapping is a Phase 2 local-adapter concern, not the factory's. |
| `DockerService.build_odoo()` runs `docker compose build odoo` against a non-existent build service | **N/A.** That is CLI code (`DockerService`) which the factory does not copy. |

## 4. Odoo Source Acquisition — Real Parameterization

The Odoo source stops being a git submodule (as in `odoo-idp`'s `.gitmodules` / `COPY src/odoo`). The factory clones it at build time, pinned by the version branch:

```
git clone --branch ${ODOO_VERSION} --depth 1 https://github.com/odoo/odoo.git
```

The resolved commit SHA is baked into the image as an OCI label (`org.opencontainers.image.revision`) so a future lockfile can trace exactly which Odoo source produced a given image.

The Dockerfile takes **two** build args, because the correct Python runtime changes across Odoo versions. Odoo's own `requirements.txt` gates `gevent`/`greenlet` (and other C-extension deps) by `python_version` — so the Python choice is not cosmetic, it selects which pinned dep versions get installed. The chosen Python for each version must select dep versions that **have wheels** (or build cleanly on today's toolchain):

| Odoo version | Python base image | Why |
|---|---|---|
| 16.0 | `python:3.11-slim-bookworm` | 3.10 selects `gevent==21.8.0` (no wheel, fails under Cython 3.x); 3.11 selects `gevent==22.10.2` (wheels) |
| 17.0 | `python:3.11-slim-bookworm` | 3.11 selects `gevent==22.10.2` (wheels) |
| 18.0 | `python:3.11-slim-bookworm` | 3.11 selects `gevent==22.10.2` (wheels) |
| 19.0 | `python:3.12-slim-bookworm` | 3.12 selects `gevent==24.2.1` (wheels); verified building |

```dockerfile
ARG ODOO_VERSION
ARG PYTHON_VERSION
```

The exact `odoo_version → python_version` mapping is validated against each branch's `requirements.txt` during implementation; the table above is the starting point.

## 5. Repository Structure

```
factory/
  Dockerfile              # multi-stage, parameterized; derived from odoo-idp infra/build/Dockerfile
  entrypoint.sh           # adapted from odoo-idp: no submodules, dynamic addons_path
  extra_requirements.txt  # small, hand-maintained extra Python deps
  versions.yaml           # the {odoo, python} matrix — single source of truth
.github/workflows/
  build-images.yml
```

`versions.yaml` is the single source of truth for the build matrix. The workflow reads it; versions are never hardcoded in two places.

### 5.1 Dockerfile

Derived from `odoo-idp`'s `infra/build/Dockerfile` (multi-stage builder → production, cached layered pip installs, non-root `odoo` user, `wkhtmltopdf` per-arch, healthcheck), with these changes:

- `FROM python:${PYTHON_VERSION}-slim-bookworm` in both stages (parameterized, not hardcoded to 3.12).
- Odoo source obtained via `git clone --branch ${ODOO_VERSION}` instead of `COPY src/odoo`.
- Only two pip layers: Odoo's own `requirements.txt` (from the clone) and `extra_requirements.txt`. No `requirements.collected.txt` layer.
- `ENV ODOO_VERSION=${ODOO_VERSION}` (parameterized).
- OCI labels including `org.opencontainers.image.revision` = resolved Odoo SHA.
- `ARG ODOO_UID=1000` / `ARG ODOO_GID=1000` retained and actually passed by CI.
- Existing `suds-jurko → suds-community` fix retained (unmaintained, broken on Python 3.12).

### 5.2 entrypoint.sh

Adapted from `odoo-idp`'s `infra/build/entrypoint.sh`:

- Keep: dynamic `addons_path` discovery (scan for `__manifest__.py`), `wait-for-psql`, config injection ("one image, two environments"), debug/`debugpy` helper.
- **Drop `INIT_BASE` auto-init.** A base image is a neutral building block: it must not initialize a database on its own. DB init is a caller/policy decision — the smoke test passes `-i base,sale,purchase,stock` explicitly, and higher layers / the local backend (Phase 2) own init policy. Baking auto-init would impose behavior on every consumer and break the layer model.
- The mount points remain (`/mnt/custom`, `/mnt/community`, etc.) so higher layers and the local backend can mount source later, but the base image ships with none of them populated.

## 6. CI Pipeline (`build-images.yml`)

Standard build-by-digest + merge pattern for multi-arch:

1. **Matrix job** over `(version × arch)`, each on a native runner (arm64 on GitHub-hosted ARM runners — no QEMU):
   1. `docker buildx build` the image for that single arch, passing `--build-arg ODOO_VERSION`, `--build-arg PYTHON_VERSION`, `--build-arg ODOO_UID`, `--build-arg ODOO_GID`.
   2. **Smoke test (publish gate):** start an ephemeral PostgreSQL service container, then run the freshly built image with `odoo -i base,sale,purchase,stock --stop-after-init`. If Odoo fails to initialize the database with those modules, the job fails and nothing is published. This catches missing runtime Python dependencies that a bare `odoo --version` would not — exactly the class of failure that differs across Odoo versions.
   3. Push the image **by digest** to GHCR.
2. **Merge job** per version: assemble the multi-arch manifest list from the per-arch digests and apply the tags.

The matrix (versions and their Python bases) is read from `factory/versions.yaml`.

## 7. Tags

Each version publishes two tags to `ghcr.io/aparragithub/odoo-ce`:

- **Moving:** `ghcr.io/aparragithub/odoo-ce:19` — always the latest good build of 19. For developer ergonomics.
- **Immutable:** `ghcr.io/aparragithub/odoo-ce:19.0-YYYYMMDD` — reproducible; what a future lockfile pins (by digest, never by the moving tag).

Rule for downstream: the Phase 2+ lockfile always resolves to a **digest**, never to a moving tag.

## 8. Success Criteria

- `docker pull ghcr.io/aparragithub/odoo-ce:19` (and `:18`, `:17`, `:16`) returns a working multi-arch image on both amd64 and arm64.
- Running the image against a PostgreSQL boots Odoo and serves `/web/health`.
- A red smoke test blocks publication (verified by intentionally breaking a dependency).
- The image carries an OCI `revision` label pointing at the exact Odoo source SHA.
- Adding a fifth version is a single entry in `versions.yaml` plus its Python mapping — no Dockerfile or workflow branching.

## 9. Open Questions

- Exact `odoo_version → python_version` mapping per branch's `requirements.txt` (resolved during implementation).
- Whether `extra_requirements.txt` needs per-version variants or a single shared file suffices (start shared; split only if a version demands it).
