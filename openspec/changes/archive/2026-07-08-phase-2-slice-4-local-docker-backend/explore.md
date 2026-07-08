# Exploration: Phase 2 Slice 4 — Local Docker Backend

**Status:** ready-for-proposal (6 open questions surfaced) · Artifact store: hybrid (mirror of Engram `sdd/phase-2-slice-4-local-docker-backend/explore`)

## Critical finding first

`src/odoo_forge/manifest/locking.py:27-29` already contains this comment:

```python
# `PublishedLayer` has no git repo to pin — omitted from the lock
# until registry resolution lands (Slice 4), never recorded as an
# empty `ResolvedLayer`.
```

Direct code evidence that the roadmap's "HTTP / registry client libraries" line means resolving `PublishedLayer.source`/`version` (schema.py:33-39, the `registry://...` manifest fields from design §2.3) into the lockfile — a separate infrastructure concern from Docker container orchestration. They plug into different seams (`build_lock`/`SourceProvider` vs a brand-new `BackendProvider` port) with no shared code path.

**Recommendation: split into 4a (registry-resolved published layers, small, mirrors Slice 2b) and 4b (local Docker backend, new port + adapter + CLI commands)** — at minimum two chained PRs, possibly two SDD changes.

## Current state (cited)

- Roadmap: `docs/specs/2026-07-06-phase-2-slices-roadmap.md:98-102`.
- Backend contract (7 ops: `materialize/create_instance/destroy/logs/exec/backup/restore/status`): `docs/specs/2026-07-05-modular-odoo-platform-design.md` §2.4, lines 92-116. `local` (Docker) is the "first backend built"; `idp-server`/remote backends are Phase 4/5.
- State model — no parallel registry, ask the backend (§6.2, lines 225-229): a Docker adapter's `status()` must introspect Docker directly (labels / `docker inspect`), never persist a running-instance registry. `MaterializedState` (`src/odoo_forge/manifest/state.py`) is the Slice-3 workspace-projection concept (repos/commits on disk) — NOT the same as a running instance; must not be reused as instance persistence.
- Seeding (§4.3, lines 166-168): designed in workspace/local-backend slices; anonymization is explicit open question §9.5 (line 273) deferred to Phase 4. Slice 4 should design the hook, not implement anonymization.
- Multi-OS (§6.4, lines 237-244): per-OS mount strategy + `doctor` command are adapter-internal.
- Image factory already built (`factory/Dockerfile`, `factory/entrypoint.sh`): creates the SAME 5 mount roots Slice 3 projects onto (Dockerfile:84); `entrypoint.sh:79-91` dynamically builds `addons_path` by scanning them; `entrypoint.sh:143-159` hard-requires a reachable Postgres via `DB_HOST` etc — **Postgres provisioning is an unstated scope gap** the proposal must close. `HEALTHCHECK` / `EXPOSE 8069 8072` give ready `status()`/`logs()` primitives.
- Ports/adapters pattern (2 precedents, `odoo_forge_git`/`odoo_forge_workspace`): `Protocol` port in `src/odoo_forge/ports/`, sibling package adapter, CLI composition root (`_make_*_provider()` in `main.py`), resilient boundary (typed error family → single-line error + `Exit(1)`, atomic writes, stop-on-first-failure).
- Import-linter (`pyproject.toml:32-67`): 4 kept contracts; `docker`/`requests`/`httpx` already defensively forbidden from core (lines 47-48) even before any adapter uses them. Slice 4 adds a 5th (and possibly 6th) contract.
- Test pattern (`tests/adapters/test_git_provider.py`): `monkeypatch.setattr(subprocess, "run", fake)`, zero real subprocess/network in unit tests — Strict TDD compatible; a docker-CLI-subprocess adapter mirrors this exactly, an HTTP/SDK-based adapter would need a different mock shape.
- Deferred debt from Slice 3: override application (unrelated), Docker mount execution (THIS is Slice 4), retry/backoff/observability (git-adapter debt, doesn't hard-carry), branch naming (unrelated).

## Scope forks the proposal must decide

1. **Split 4a/4b** (confirmed by `locking.py` comment) — recommend at least 2 chained PRs.
2. **Backend operation surface**: `create_instance`/`run`, `status`, `stop`/`destroy`, `logs` near-certain IN; `backup`/`restore` likely deferred to Phase 4 (design buckets backup service there, §5 line 185); `exec` undecided.
3. **Registry-resolution protocol (4a)**: real HTTP(S) registry API call now vs Phase-2-scoped stub/typed-error — no fixture/test exercises `PublishedLayer` resolution yet, `registry://` is a placeholder scheme.
4. **Seeding**: define extension point only (e.g. `seed_from` capability), explicit non-goal for anonymization implementation.
5. **Postgres provisioning**: backend spins up its own Postgres container vs requires an external one — must be decided explicitly, not left implicit.

## Approaches (Docker adapter, 4b)

1. **Shell out to `docker` CLI via subprocess** — Low-Medium effort, zero new dependency, matches existing 2 adapters and their test-mocking pattern exactly. Con: argv construction for complex `docker run` flags is more brittle than a typed SDK.
2. **Docker Engine API over HTTP (unix socket)** — Medium-High effort, typed, but conflates "docker adapter" with "HTTP client library" work that more plausibly belongs to 4a. New runtime dependency.
3. **`docker-py` SDK** — Low-Medium effort, maintained/typed, but new dependency and a different test-mocking shape than the established convention.

**Recommendation**: Option 1 for the Docker adapter (lowest deviation, Strict-TDD-compatible); reserve `httpx`/`requests` for the registry-resolution piece (4a), where HTTP client work genuinely belongs.

## Risks

- Bundling 4a+4b as one undifferentiated slice risks blowing the 400-line PR budget across two unrelated I/O boundaries.
- Silent Postgres-provisioning assumption breaks the "one command, working Odoo" Phase-2 exit criterion if left unresolved.
- Choosing an HTTP/SDK-based Docker adapter deviates from Strict TDD's proven subprocess-mocking convention and adds a new runtime dependency without clear necessity for this slice.
- Registry-resolution protocol is fully undecided; picking a real network protocol now vs a stub affects whether Phase 2 needs a new runtime dependency at all.

## Open questions for Angel

1. Split Slice 4 into 4a/4b (confirmed distinct by code)? One SDD change with 2 PRs, or two changes?
2. Which of the 7 backend-contract ops ship now — confirm `backup`/`restore` deferred, decide `exec`.
3. Local backend provisions its own Postgres, or requires external Postgres?
4. Docker adapter strategy — CLI subprocess (recommended) vs HTTP API vs `docker-py` SDK.
5. Registry-resolution protocol for 4a — real network call now, or typed stub deferred further?
6. Scope of §4.3 seeding for Slice 4b — extension point only, confirmed non-goal on anonymization?

## Ready for Proposal

Yes — with the 6 open questions above surfaced before `sdd-propose` locks scope, especially #1 (confirmed 4a/4b split) and #5 (registry protocol / new-dependency decision).
