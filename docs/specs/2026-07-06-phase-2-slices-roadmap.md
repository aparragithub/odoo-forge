# Phase 2 — Vertical Slices Roadmap

> **Historical roadmap (superseded).** This document preserves the Phase 2 delivery record and
> must not be used as the current platform plan. Use
> [`docs/specs/platform/portfolio.json`](platform/portfolio.json) for authoritative status,
> dependencies, acceptance evidence, and handoffs.

**Status:** historical/superseded · **Last updated:** 2026-07-07 (Slice 2 FULLY DONE)

Phase 2 (CLI core + manifest + local backend) is delivered as vertical slices, each a
self-contained SDD change. This is the forward map: what each slice owns and what feeds
it. Authoritative scope boundaries were set in the Slice 1 proposal (Out of Scope) and
design; this doc consolidates them so the next slice starts from a known line, not memory.

Source of truth for Slice 1 boundaries:
`openspec/changes/archive/2026-07-06-phase-2-manifest-core/{proposal,design}.md`.

---

## Slice 1 — Manifest Core ✅ DONE (archived 2026-07-06)

Pure manifest/lockfile domain, no I/O.

- Pydantic v2 schema (`Manifest`/`Lockfile`, `core` field, `requires_edition` gating,
  discriminated `Layer` union).
- Onion composition (order + coherence) and pure `detect_drift(manifest, lock, materialized)`.
- `SourceProvider` **port (interface only)**.
- Thin `forge validate` CLI; import-linter purity gate from commit one.

Baseline spec: `openspec/specs/manifest/spec.md`.

---

## Slice 2a — Pure Resolution Prep ✅ DONE (archived 2026-07-07)

Foundation work — pure logic only, zero I/O, no new runtime deps.

- **Default-ref substitution helper** — `resolve_default_ref(core, odoo_version) -> str`, pure function that returns `odoo_version` when `core.ref is None`, else echoes `core.ref` unchanged.
- **Lockfile serialization contract** — formalized JSON schema (add `schema_version: int` field starting at 1), deterministic key ordering, byte-stable round-trip (`to_canonical_json()` / `from_json()`).
- **Drift back-compat regression** — confirm legacy (Slice-1-era) locks without `schema_version` validate and yield identical `DriftReport` results.
- **Spec amendment** — update `openspec/specs/manifest/spec.md` with new Req 1 (default-ref helper) and Req 2 (canonical lockfile format). Resolves verify-report **W1** (naming divergence) with method names `to_canonical_json()`/`from_json()`.
- **W3 debt closed** — lockfile-format debt formalized; no longer a residual warning.

Baseline spec: `openspec/specs/manifest/spec.md` (amended 2026-07-07).

---

## Slice 2b — Git Resolution & Lock Writer ✅ DONE (archived 2026-07-07)

Turns declared *intent* into pinned, reproducible `project.lock`. I/O boundary successfully added.

**Delivered:**
- **Concrete git `SourceProvider` adapter** (new package `odoo_forge_git`; network/git implementation behind the Slice 1 port).
- **Pin resolution — ref → commit SHA** via `git ls-remote` (subprocess adapter; typed error handling for ref-not-found / auth-failure / network-failure).
- **`forge lock` CLI command** — produces canonical `project.lock` by composing manifest, substituting default refs (Slice 2a), resolving SHAs via injected adapter.
- **Error taxonomy** — `ResolutionError`/`RefNotFoundError`/`AuthenticationError`/`NetworkError` in core errors module.
- **Import-linter third contract** — forbidden `odoo_forge` → `odoo_forge_git` (target achieved: 3 kept / 0 broken, core purity intact).
- **Resilient CLI boundary** — atomic write (`tempfile` + `os.replace`), clean error messages, no partial locks on failure.

**Key design decisions:**
- Adapter in new sibling package (not inside core) to preserve import-linter purity gate.
- `git ls-remote` via argv-list subprocess (no cloning, no `shell=True`).
- `build_lock(manifest, provider)` is a pure core use-case (Protocol-injected) — testable via fake, zero concrete imports.
- Composition root is CLI (`_make_provider()` constructs `GitSourceProvider()`).

**Deferred non-blocking debt (per design):**
- Real-git integration test (all subprocess mocked).
- Retry/backoff + structured observability on ls-remote.
- Override application (fork url/ref substitution) — deferred to later slice.

Baseline spec: `openspec/specs/manifest/spec.md` (amended 2026-07-07).

---

## Slice 3 — Workspace Projection ✅ DONE (archived 2026-07-08)

Projects composed + materialized layers onto the developer's filesystem.

**Delivered:**
- **Workspace projection** (`plan_projection`, fixed 5-root mount-root classification via optional `category` field).
- **Workspace scan and materialization** (`materialize_state` in core; `WorkspaceProvider` port with git adapter for checkout/scan/promote).
- **`unlock` promotion** to writable worktrees (`forge unlock --layer --repo`); promotes read-only projection to `/mnt/worktrees/<layer>/<repo>` writable copy.
- **`forge project` CLI** executes projection plan through resilient boundary (atomic per-repo, stop-on-failure).
- **`forge validate` scan wiring** now calls real scan, derives `MaterializedState`, and activates the previously-dead `detect_drift(..., materialized=state)` path (no more `materialized=None`).
- **4th import-linter contract** (forbidden `odoo_forge → odoo_forge_workspace`) kept intact.
- **5-PR feature-branch-chain delivery** (all PRs under 400-line budget): PR-1 core schema/port, PR-2a pure execution+checkout adapter, PR-2b scan/promote/materialize, PR-3 forge-project+validate-wiring, PR-4 forge-unlock.

**Key design decisions:**
- Layer→root classification: additive optional `category` field (back-compat, no lock format change).
- `unlock` = git worktree promotion (non-destructive, keeps read-only projection pristine at locked commit).
- Pure core (`plan_projection`, `materialize_state`) with dumb adapter (checkout/scan/promote execute core-decided paths/branch).

**Deferred non-blocking debt:**
- Override application (fork url/ref substitution) — re-deferred to later slice.
- Docker/local-backend mount execution — Slice 4.
- Retry/backoff/observability on checkout — deferred (design scope line).
- Branch naming convention confirmation at next spec update.

Baseline spec: `openspec/specs/manifest/spec.md` (amended 2026-07-08).

---

## Slice 4 — Local Docker Backend ✅ DONE: 4b archived 2026-07-08 | 4a DEFERRED

### Slice 4b ✅ DONE (archived 2026-07-08)

**Delivered:** Local Docker backend (BackendProvider port + pure planner + docker CLI adapter + 5 CLI commands), own-Postgres provisioning, label-based state introspection, named persistent volumes (PG data + Odoo filestore), created-only rollback (critical data-loss guard), PG TCP readiness gate + Odoo health-wait >=180s floor, injectable clock seams, ephemeral host ports.

- 6-PR feature-branch-chain (PR-1a/1b/2a-i/2a-ii/2b/3a/3b): all merged to main
- Baseline spec: `openspec/specs/local-backend/spec.md` (5 capabilities, 17 scenarios)
- CLI commands: `forge run`, `forge status`, `forge stop`, `forge logs`, `forge exec`
- Gates: ✅ 242 tests passed, 1 deselected (integration skeleton); ✅ 5 import-linter contracts kept, 0 broken
- Pure core: `BackendProvider` port + error family + `plan_backend` + `parse_status` (zero subprocess/docker imports)
- Adapter: `odoo_forge_docker` (subprocess-based docker CLI, mirrors git/workspace adapters)
- Size exception: PR-2a-ii 537 lines (34% over budget) — root cause: 14 judgment-day-hardened tests (full run() ordering, PG/Odoo gates, created-only rollback, reattach-then-fail guard, 3 error classification variants) ported verbatim from snapshot; not re-split per explicit orchestrator boundary instruction; flagged for visibility

**Design decisions (judgment-day-hardened):**
- Pure planner emits typed specs; adapter builds argv (keeps core import-pure)
- Env plan: single source of truth (Postgres `{POSTGRES_PASSWORD,POSTGRES_USER,POSTGRES_DB}`, Odoo `{DB_HOST,DB_PORT,DB_USER,DB_PASSWORD,POSTGRES_DB}` — no `DB_NAME`; exact entrypoint match per factory/entrypoint.sh:143-159)
- Named PG data + Odoo filestore volumes both persist across stop→run
- Created-only rollback: pre-existing volumes NEVER removed (critical data-loss guard, tested by reattach-then-fail case)
- Running-state-first readiness: exited container never maps to "unknown"
- Postgres TCP readiness gate: `docker exec <db> pg_isready -h 127.0.0.1 -U <user> -d <db>` (bounded retries)
- Odoo health-wait timeout default floor: >=180s (start-period 60s + >=1 interval 30s + cold-boot margin)
- Ephemeral host ports (-p 0:8069/-p 0:8072): supersedes spec's PortConflict requirement (collisions structurally unreachable)
- Docker adapter via subprocess (not HTTP SDK): matches existing adapters, Strict-TDD-compatible
- Status no-raise / stop/logs/exec InstanceNotFoundError divergence: status returns not-running without raising; others raise when absent
- 5th import-linter contract: forbidden `odoo_forge → odoo_forge_docker`

**Deferred non-blocking debt (tracked):**
- **DEBT-1** (monotonic-deadline refinement for _wait_pg_ready/_wait_odoo_healthy): poll loops bound by attempt-count, not wall-clock deadline; under slow daemon real wait can exceed timeout (bounded, no leak — SLA imprecision only). Deferred to hardening pass.
- **DEBT-2** (pure-identity ops without workspace scan): stop/logs/exec/status derive identity via full scan, blocking when workspace corrupted; should derive from manifest.name+instance without scanning. Deferred (couples to plan_backend(state) consumption).

**Out of scope (explicitly deferred):**
- Backup/restore (Phase 4)
- Doctor command (typed DockerUnavailableError covers dependency check)
- Destroy op (stop preserves volumes; reclaim future slice)

Baseline spec: `openspec/specs/local-backend/spec.md` (new).

---

### Slice 4a DEFERRED (future slice)

**Registry Resolution:** Resolve `PublishedLayer.source`/`version` to lockfile entries via HTTP registry API call.

- **Separate infrastructure concern**: network I/O boundary (HTTP) distinct from Docker I/O (subprocess)
- **Different seam**: plugs into `build_lock`/`SourceProvider`, not backend chain
- **Evidence**: `locking.py:27-29` comment ("until registry resolution lands"); explore.md confirms 4a/4b split
- **Deferred alongside**: backup/restore (Phase 4), doctor (hardening), destroy (hardening)

---

## Cross-session pointers (Engram)

- `sdd/phase-2-manifest-core/scope-boundary` (#2290) — why core.ref resolution was deferred (Slice 1).
- `sdd/phase-2-manifest-core/archive-report` (#2291) — Slice 1 close + deferred list.
- `sdd/phase-2-manifest-core/verify-report` (#2289) — residual warnings (W2 fork-url test, W3 ~~lock format~~ CLOSED by Slice 2a).
- `sdd/phase-2-slice-2a-resolution-prep/archive-report` (#2297) — Slice 2a close + Slice 2b handoff.
- `sdd/phase-2-slice-2b-resolution-io/archive-report` (#TBD) — Slice 2b close. Deferred non-blocking: real-git integration test (subprocess mocked), retry/backoff + observability (design scope line), override application (to later slice).

## Non-blocking tracked debt (Slice 4b)

- **DEBT-1** — `_wait_pg_ready`/`_wait_odoo_healthy` (PR-2a-ii tasks section): poll loops bound by attempt-count instead of monotonic wall-clock deadline; under slow daemon real wall-clock wait can exceed configured timeout (bounded, no leak — SLA imprecision only). Deferred to future hardening pass.
- **DEBT-2** — `stop`/`logs`/`exec`/`status` (PR-3b tasks section): derive instance identity via full workspace scan (plan_backend ignores state this slice), so corrupted/absent workspace blocks pure-identity ops with clean ScanError→Exit(1). Should derive identity from manifest.name+instance without scanning, allowing ops when workspace broken. Deferred (couples to plan_backend(state) consumption); current safe behavior documented by `test_scan_error_from_corrupted_checkout_exits_clean_one_error` (parametrized over all 5 commands).

## Non-blocking test debt (earlier slices)

- **W2** — explicit fork-url override test; defer until override application is implemented (later slice).
