# Design: Phase 2 Slice 4b — Local Docker Backend

## Technical Approach

Extend the proven ports/adapters spine to a third boundary: containers. A pure
core planner turns `Manifest + MaterializedState` into a declarative
`BackendPlan` (typed network/container/mount/env/label specs); a new sibling
adapter `odoo_forge_docker` translates specs into `docker` CLI argv via
`subprocess` (argv-list, no `shell=True`) and parses `docker inspect` JSON back
through a pure core parser. Same invariants as Slices 1-3: pure core decides,
dumb adapter executes; typed error family -> single-line message + `Exit(1)`;
stop-on-first-failure; composition root in `main.py`. State is Docker itself
(labels + inspect), never a registry file (design §6.2).

## Architecture Decisions

### Package name: `odoo_forge_docker`
**Choice**: sibling package named after the runtime tool, like `odoo_forge_git`.
**Rejected**: `odoo_forge_backend` (concern-named, but the port already carries
the concern and a future `idp-server`/`ec2` backend would collide with it).
**Rationale**: the adapter's identity is "the one place that shells out to
`docker`", mirroring `odoo_forge_git` = "shells out to `git`".

### Pure planner emits typed specs, adapter builds argv
**Choice**: planner returns `ContainerSpec`/`NetworkSpec`; adapter maps spec->argv.
**Rejected**: planner builds argv strings directly (core would encode docker CLI).
**Rationale**: keeps `odoo_forge` import-pure (no `subprocess`/`docker`), makes
the planner snapshot-testable on data, and isolates argv brittleness in the
adapter where subprocess mocking already lives.

### `docker inspect` parsing is a pure core function
**Choice**: adapter runs `docker inspect`, hands raw JSON to core
`parse_status(json) -> InstanceStatus`.
**Rationale**: the interesting logic (readiness/state derivation) is pure and
unit-testable without docker; the adapter only does I/O.

### Readiness signal: running-state first, then per-role HEALTHCHECK-aware inspect
**Choice**: `parse_status` derives state in TWO ordered stages, because a
container can be stopped/exited independently of any health verdict, and only
the Odoo image ships a HEALTHCHECK (the stock `postgres` image has none):

**Stage 1 — running state (BOTH roles, evaluated FIRST)**: `parse_status` MUST
inspect `.State.Running`/`.State.Status` BEFORE consulting health. If
`.State.Running == false`, the container is stopped/exited regardless of role or
any stale `.State.Health` value — it MUST map to a not-running/exited status and
MUST NOT be classified as `unknown`. A cleanly-exited or crashed Odoo container
(`Running=false`, `Health` null) is exited, not `unknown`.

**Stage 2 — readiness for a RUNNING container (per role)**: only when
`.State.Running == true`:
- **Odoo role**: `ready` iff `.State.Health.Status == "healthy"`. State mapping:
  `starting` -> not-ready (booting), `unhealthy` -> not-ready, `healthy` ->
  ready. A null/absent `.State.Health` (`<no value>`) on a RUNNING Odoo container
  is unexpected for the Odoo image and maps to `unknown` (not-ready), never
  treated as permanently ready.
- **Postgres role**: the image has NO healthcheck, so `.State.Health` is null
  (`<no value>`) even when running. `parse_status` MUST treat null-health for a
  running Postgres container as "no-healthcheck" running (not permanently
  not-ready). Run-time TCP readiness is gated separately (see `run`
  orchestration).

Enumerated mapping (both roles): `Running=false` -> stopped/exited; `Running=true`
+ health `healthy` -> ready; `Running=true` + health `starting`/`unhealthy` ->
not-ready; `Running=true` + null health (Postgres / no-healthcheck) ->
running/unknown-health.

- **Absent/empty inspect** (container externally removed): `parse_status` MUST
  return a not-running status WITHOUT raising, so `status()` on a manually-removed
  container is well-defined (spec scenario), while `stop`/`logs`/`exec` on an
  absent instance raise `InstanceNotFoundError`.
**Rejected**: keying Odoo state off `.State.Health.Status` alone (a cleanly-exited
Odoo container has null health and would wrongly map to `unknown` instead of
exited); adapter HTTP probe on 8069 (needs `httpx`/`requests` — forbidden
from core, out of scope, and assumes a host port mapping); container-running
only for Odoo (Odoo may still be migrating/booting).
**Rationale**: the Odoo image ALREADY ships a HEALTHCHECK hitting `/web/health`
(Dockerfile:100-101). Reusing the container's own authoritative verdict adds no
dependency and no duplicated probe; Postgres readiness cannot reuse it because
the stock image publishes no healthcheck. Checking `.State.Running` first keeps
the running-vs-stopped distinction (used by the `run` precheck) correct for both
roles.
**Tests (unit, pure)**: `parse_status` cases for `starting`/`unhealthy`/`healthy`,
null-health for the Postgres role (running-based, no-healthcheck), null-health
for a running Odoo container (unknown), an EXITED Odoo container
(`Running=false`, null health -> exited, NOT unknown), and empty/absent inspect
output (not-running, no raise).

### `doctor`: OUT of this slice
**Choice**: no `doctor` command. Missing docker binary / unreachable daemon
surfaces as typed `DockerUnavailableError` -> `Exit(1)`. Full multi-OS `doctor`
(§6.4) deferred.
**Two detection mechanisms**, both mapped to `DockerUnavailableError` — a missing
binary and a down daemon are distinct failures at the subprocess layer:
1. **Missing binary**: `subprocess.run` raises `FileNotFoundError` (docker not on
   `PATH`), same path as the git adapter.
2. **Daemon unreachable**: the binary IS present and runs, but exits non-zero with
   a stderr marker (`Cannot connect to the Docker daemon`). The adapter classifies
   this by stderr-marker matching, mirroring how `odoo_forge_git` classifies
   auth/network failures from `git` stderr markers.
To keep stderr markers locale-stable, the adapter pins `LANG=C`/`LC_ALL=C` in the
subprocess environment for all `docker` invocations (the git adapter already does
this).
**Rationale**: `doctor` is a separate diagnostic capability; a clear typed error
already covers the "docker not available" dependency for run/status/etc.
**Tests (adapter)**: one case injecting `FileNotFoundError`, one injecting a
non-zero exit with the `Cannot connect to the Docker daemon` stderr marker; both
MUST surface as `DockerUnavailableError`.

### Env & credentials: one planner-owned source of truth
**Choice**: the pure planner emits ALL DB env on both `ContainerSpec`s so the two
sides can never drift. Verified against `factory/entrypoint.sh:143-159`, which
reads the connection env, applies defaults, and passes `--database
"${POSTGRES_DB:-postgres}"` — the database selector is **`POSTGRES_DB`, not
`DB_NAME`**. `DB_NAME` is DEAD: the entrypoint never reads it, so setting it makes
Odoo boot the `postgres` maintenance DB. Likewise the stock `postgres` image
requires `POSTGRES_PASSWORD` at boot or the container exits immediately.

Planned env (single source of truth):

| ContainerSpec | Env keys | Value |
|---|---|---|
| Postgres | `POSTGRES_PASSWORD` | `odoo` (deterministic local-dev default) |
| Postgres | `POSTGRES_USER` | `odoo` |
| Postgres | `POSTGRES_DB` | project DB name = `sanitize_name(manifest.name)` |
| Odoo | `DB_HOST` | Postgres container network alias (never `localhost`) |
| Odoo | `DB_PORT` | `5432` |
| Odoo | `DB_USER` | `odoo` (matches `POSTGRES_USER`) |
| Odoo | `DB_PASSWORD` | `odoo` (matches `POSTGRES_PASSWORD`) |
| Odoo | `POSTGRES_DB` | project DB name (matches Postgres `POSTGRES_DB`; this is the entrypoint's `--database` selector) |

**Credential source**: deterministic defaults `odoo`/`odoo` (this is a LOCAL dev
backend; the values match the entrypoint's own fallbacks so behavior is identical
whether or not they are set explicitly). The project database name is derived from
`sanitize_name(manifest.name)` so Odoo boots a project DB rather than the
`postgres` maintenance DB. A generated password is a documented future option, not
this slice.
**Rejected**: emitting `DB_NAME` (ignored by the entrypoint); relying on entrypoint
defaults only (leaves the Postgres side with no `POSTGRES_PASSWORD` -> PG exits).
**Tests (unit, pure)**: assert the planned env keys on each `ContainerSpec` EXACTLY
match what `factory/entrypoint.sh:143-159` consumes — Postgres side
`{POSTGRES_PASSWORD, POSTGRES_USER, POSTGRES_DB}`, Odoo side `{DB_HOST, DB_PORT,
DB_USER, DB_PASSWORD, POSTGRES_DB}` — and that Odoo's `DB_USER`/`DB_PASSWORD`/
`POSTGRES_DB` equal Postgres's `POSTGRES_USER`/`POSTGRES_PASSWORD`/`POSTGRES_DB`.
No `DB_NAME` key is emitted anywhere.

### `sanitize_name`: degenerate manifest names
**Choice**: `sanitize_name` is a pure UNARY function mapping `manifest.name`
(a free `str`, schema.py:74) into the docker charset `[a-z0-9][a-z0-9_.-]*`.
Because a unary function cannot observe OTHER names, distinctness is guaranteed
by an ALWAYS-ON lossy-transform rule rather than a cross-name collision check:
- **Lossy-transform rule**: whenever the sanitizing transform is LOSSY — i.e. any
  character is changed or dropped, or the result would be empty or would begin
  with an invalid first char — `sanitize_name` MUST append a short deterministic
  hash suffix derived from the RAW input. A hash of the raw input makes two
  distinct raw names that map to the same sanitized stem land on distinct
  outputs, without needing to see the other name. A name that is already a valid
  docker token (no character lost) is returned unchanged (no suffix).
- input that sanitizes to empty (e.g. all-symbol name) -> fall back to a stable
  slug derived from the short hash of the raw name (this is the lossy rule at the
  limit);
- input whose first char is not `[a-z0-9]` -> prefix/repair so the first char is
  valid (this repair is itself lossy, so the hash suffix is appended).
The hash is deterministic (same raw input -> same output), so the function stays
pure and reproducible.
**Tests (unit, pure)**: already-valid name (returned unchanged, no suffix),
empty-after-sanitize, invalid-first-char, and lossy-transform cases each assert a
valid, deterministic result; two distinct raw names sharing a sanitized stem
assert distinct outputs.

## Naming & Label Schema

Label namespace `com.odoo-forge.*`, applied to every created resource:

| Label | Value |
|---|---|
| `com.odoo-forge.project` | sanitized `manifest.name` |
| `com.odoo-forge.instance` | instance name (default `default`) |
| `com.odoo-forge.role` | `odoo` \| `postgres` |
| `com.odoo-forge.managed` | `true` (scope filter for status/cleanup) |

Deterministic names (targeting) computed by the pure core, complementing labels
(reconstruction): containers `odoo-forge-<project>-<instance>-{odoo,db}`, network
`odoo-forge-<project>-<instance>`. `manifest.name` is sanitized to the docker
charset (`[a-z0-9][a-z0-9_.-]*`) in pure core (`sanitize_name`). `status()`
reconstructs identity purely from labels via
`docker inspect`/`docker ps --filter label=com.odoo-forge.managed=true`.

## Data Flow

    Manifest + MaterializedState
          | plan_backend()  (pure core, zero I/O)
          v
    BackendPlan { NetworkSpec, VolumeSpec(pgdata), VolumeSpec(odoo-filestore),
                  ContainerSpec(pg: POSTGRES_*, pgdata vol),
                  ContainerSpec(odoo: DB_* + POSTGRES_DB, filestore vol) }
          | _make_backend_provider()  (composition root)
          v
    DockerBackendProvider.run --argv--> docker network create
                              --argv--> docker volume create <pgdata>       (created-only)
                              --argv--> docker volume create <odoo-filestore>(created-only)
                              --argv--> docker run <db> (labels, POSTGRES_*, pgdata vol)
                              --poll--> docker exec <db> pg_isready -h 127.0.0.1 -U <user> -d <db>
                              --argv--> docker run <odoo> (network, DB_HOST, POSTGRES_DB, filestore vol, mounts)
                              --poll--> docker inspect <odoo> .State.Health.Status == healthy
                              --returns--> InstanceRef
    status/stop/logs/exec(InstanceRef) --> docker inspect|stop+rm|logs|exec
                                           (label+name scoped) --> parse_status() -> InstanceStatus

## `run` Orchestration & Failure Boundary

Order: (1) `network create` -> (2) `volume create` (named PG data volume) ->
(3) `run` postgres detached with `POSTGRES_*` env + volume mount -> (4) gate PG
TCP readiness -> (5) `run` odoo attached to the network with `DB_HOST=<db alias>`
and the matching `POSTGRES_DB` -> (6) bounded wait for the Odoo container's
`.State.Health.Status == healthy` -> (7) return an `InstanceRef`.

**PG readiness gate (step 4)**: `docker exec <db> pg_isready -h 127.0.0.1 -U
<user> -d <db>` (bounded retries/timeout). The `-h 127.0.0.1` forces the TCP
listener path and `-U`/`-d` scope it to the real role/database — a bare
`pg_isready` over the local socket can report ready DURING the postgres
first-boot bootstrap (socket up before the TCP listener/role/db exist), which is
exactly the race we must not pass. A PG failure surfaces as
`PostgresReadinessError`, distinct from an Odoo boot failure.

**Odoo readiness gate (step 6)**: because `run` returns a handle the spec expects
to be "running, reachable" (see spec scenario), the adapter polls
`docker inspect <odoo> .State.Health.Status` until `healthy` (bounded
retries/timeout) before returning; a timeout surfaces as `ContainerRunError`.
The timeout has a concrete FLOOR reconciled with the image HEALTHCHECK timing
(`Dockerfile:100`: `--start-period=60s --interval=30s --retries=3`): a healthy
cold boot only begins reporting health after the 60s start-period and needs at
least one 30s interval, and a first-boot DB init plus the entrypoint's
`wait-for-psql` can push a HEALTHY instance to ~90-150s+ before it reports
`healthy`. The default Odoo health-wait timeout MUST therefore be at least
**180s** (start-period 60s + >=1 interval 30s + cold-first-boot margin) and MUST
be configurable. A timeout shorter than start-period + one interval would
spuriously raise `ContainerRunError` against a container that is in fact healthy,
so the floor is a correctness requirement, not a tuning preference.

**Defense-in-depth**: the image entrypoint's own 60s `wait-for-psql`
(`entrypoint.sh:143-159`, `--database "${POSTGRES_DB:-postgres}"`) remains the
authoritative in-container gate; the adapter gate is an additional early, typed
signal. The residual bootstrap race is only observable against a REAL daemon, so
run->status->stop timing behavior is covered by `@pytest.mark.integration`
(deselected from the Strict-TDD unit run), not by mocked unit tests.

**Deterministic poll seam**: both readiness poll loops take an injectable
sleep/clock seam (constructor-injected callable, defaulting to `time.sleep`) so
the retry/timeout paths are deterministically unit-testable under Strict TDD
without real waiting.

Transactional boundary: `run` is all-or-nothing, tearing down ONLY what THIS
invocation actually created. Before creating each resource the adapter checks
existence (`docker volume inspect` / network / container inspect); it pushes a
resource onto the rollback stack ONLY if this invocation created it. A resource
that already existed and was merely re-attached (notably a preserved named PG
data volume, or the named Odoo-filestore volume, on a `run` -> `stop` -> `run`
reattach) is NEVER pushed and NEVER torn down. On any step failure the adapter
tears the created-only stack down in REVERSE (`docker rm -f -v` for containers,
`docker volume rm` for volumes this run created, `docker network rm`), scoped to
`com.odoo-forge.managed=true`.

**Created-vs-reattached is a correctness requirement, not an optimization.**
`docker volume create <name>` is idempotent: on the reattach path the second
`run`'s `docker volume create <pgdata>` succeeds against the PRESERVED volume
without recreating it. If that `run` then fails the Odoo health gate
(`ContainerRunError`), an unconditional rollback stack would run
`docker volume rm` and DESTROY the preserved database — silent data loss. The
`managed=true` scope does NOT protect it, because the preserved volume is itself
managed. Recording created-vs-reattached is the only thing that keeps rollback
from deleting a volume it did not create. Requirement/test: a reattach-then-fail
run preserves the existing PG (and filestore) volume.

**Volume `-v` semantics (corrected):** `docker rm -v` removes only ANONYMOUS
volumes attached to the container; NAMED volumes are never touched by `-v`. So
`docker rm -f -v` on the containers reaps stray anonymous volumes but CANNOT and
does NOT remove the named PG or named Odoo-filestore volumes. Named volumes are
managed exclusively by explicit `docker volume rm` (issued during rollback only
for volumes this run created). The earlier claim that "`docker rm` without `-v`
would orphan the named PG data volume" is FALSE and is corrected here: a named
volume is unaffected by the presence or absence of `-v`.

Re-run / lifecycle reconciliation: `run` first inspects for any managed instance
with the same names — RUNNING OR STOPPED — and refuses with `InstanceExistsError`
if one exists, because `docker run --name` / `docker network create` collide with
a merely-stopped container/network too, not only a live one. `stop` is the
disambiguated clearing path (below), so a `run` -> `stop` -> `run` cycle does not
dead-end: `stop` frees the deterministic names while preserving the named PG data
and Odoo-filestore volumes, and the next `run` re-attaches to those volumes
(recorded as reattached, so a subsequent failure never removes them). No separate
`destroy` op is added this slice (op surface stays run/status/stop/logs/exec).

`stop` semantics (disambiguated): `stop` STOPS AND REMOVES the Odoo and Postgres
containers and the network (`docker stop` then `docker rm -f -v`, `docker network
rm`), but PRESERVES the named PG data and Odoo-filestore volumes so BOTH the
database and the filestore (attachments/assets) survive a `stop` -> `run` cycle.
The `-v` on `docker rm` reaps only any stray ANONYMOUS volumes; the named PG and
filestore volumes are immune to `-v` and stay safe, giving a leak-free steady
state. This is what frees the deterministic names for re-run. `stop` on an
instance with no matching managed container raises `InstanceNotFoundError` (spec
`ContainerNotFound`).

**Known limitation (future `destroy`, non-goal this slice):** because `stop`
preserves the named PG and filestore volumes and this slice adds NO destroy op,
preserved volumes ACCUMULATE across `run`/`stop` cycles with no reclaim path.
Reclaiming them is deferred to a future `destroy` op; it is intentionally NOT
added here (op surface stays run/status/stop/logs/exec).

## File Changes

| File | Action | Description |
|---|---|---|
| `src/odoo_forge/ports/backend_provider.py` | Create | `BackendProvider` Protocol |
| `src/odoo_forge/backend/__init__.py` | Create | package marker |
| `src/odoo_forge/backend/plan.py` | Create | `BackendPlan`/`ContainerSpec`/`NetworkSpec`/`VolumeSpec`/`ContainerRole`, `plan_backend`, `sanitize_name` |
| `src/odoo_forge/backend/status.py` | Create | `InstanceRef`/`InstanceStatus`/`ExecResult`, `instance_ref`, pure `parse_status` |
| `src/odoo_forge/backend/errors.py` | Create | `BackendError` family |
| `src/odoo_forge_docker/__init__.py` | Create | package marker |
| `src/odoo_forge_docker/provider.py` | Create | `DockerBackendProvider` (spec->argv, run/status/stop/logs/exec, created-only rollback + named-volume-safe cleanup, injectable clock, `LANG=C`) |
| `src/odoo_forge_cli/main.py` | Modify | 5 commands + `_make_backend_provider()` |
| `pyproject.toml` | Modify | wheel packages + `root_packages` + 5th import-linter contract; integration marker |
| `docs/specs/2026-07-06-phase-2-slices-roadmap.md` | Modify | record 4a/4b split |
| `tests/backend/test_plan.py`, `test_status.py` | Create | pure planner/parser unit tests |
| `tests/adapters/test_docker_provider.py` | Create | subprocess-mock adapter tests |

## Interfaces / Contracts

```python
# ports/backend_provider.py — structural interface only (FINAL signatures)
@runtime_checkable
class BackendProvider(Protocol):
    def run(self, plan: BackendPlan) -> InstanceRef: ...      # returns handle to a ready instance
    def status(self, ref: InstanceRef) -> InstanceStatus: ...
    def stop(self, ref: InstanceRef) -> None: ...             # stop + remove containers/network, keep named PG + filestore volumes
    def logs(self, ref: InstanceRef, role: ContainerRole) -> str: ...  # role param kept; returns str
    def exec(self, ref: InstanceRef, argv: Sequence[str]) -> ExecResult: ...  # exit_code + stdout + stderr

# backend/status.py (pure)
class ExecResult(BaseModel):      exit_code: int; stdout: str; stderr: str

# backend/plan.py (pydantic, pure)
class NetworkSpec(BaseModel):     name: str; labels: dict[str, str]
class VolumeSpec(BaseModel):      name: str; labels: dict[str, str]  # named, persistent volume
class ContainerSpec(BaseModel):
    name: str; image: str; role: ContainerRole; network: str
    env: dict[str, str]; mounts: list[Mount]; labels: dict[str, str]
    volumes: list[VolumeSpec] = []      # named PG data vol (postgres) / named filestore vol (odoo)
    ports: dict[str, int | None] = {}   # 8069/8072; None = ephemeral host port (DECIDED, see below)
class BackendPlan(BaseModel):
    network: NetworkSpec
    volumes: list[VolumeSpec]           # named PG data volume + named Odoo-filestore volume
    postgres: ContainerSpec; odoo: ContainerSpec

def plan_backend(manifest: Manifest, state: MaterializedState,
                 instance: str = "default") -> BackendPlan: ...
```

**`InstanceRef` return (fix #2)**: `run -> InstanceRef` (a lightweight handle
reconstructing container/network identity from labels+names) so the spec scenario
"returned handle reflects a running, reachable Odoo container" is satisfied — the
Odoo readiness gate (step 6) makes the returned handle reachable, not merely
created.

**`runtime_checkable` limitation**: `isinstance(adapter, BackendProvider)` checks
method NAMES only — it does NOT verify parameter lists or return types. So the
contract test suite MUST add an explicit structural/signature conformance test
(e.g. `inspect.signature` comparison per method) in addition to the `isinstance`
check; passing `isinstance` alone does NOT prove the adapter matches these
signatures.

**Host-port strategy: DECIDED = ephemeral.** Host ports are published as ephemeral
(`-p 0:8069`/`-p 0:8072`; `ports` value `None`), and `status()` reports the mapped
host port from `docker inspect`. Consequently host-port conflicts are structurally
unreachable, which supersedes the spec's `PortConflict` requirement (see
`PortConflict` handling below and the spec amendment). This closes the former Open
Question — it is no longer open.

**Odoo filestore volume (`/var/lib/odoo`)**: `Dockerfile:97` declares
`VOLUME ["/var/lib/odoo"]`, so every `docker run` of the Odoo container would
otherwise auto-create an ANONYMOUS filestore volume that orphans on each `stop`.
The planner therefore models a NAMED `VolumeSpec` for the Odoo filestore
(mounted on the Odoo `ContainerSpec`), analogous to the named PG data volume, so
the filestore (attachments, generated assets) genuinely survives a
`stop` -> `run` cycle. Consequently "instance state survives `stop` -> `run`" is
true for BOTH the database (named PG volume) AND the filestore (named Odoo
volume); it would be false for the filestore under an anonymous volume.

Mounts derive from `MaterializedState`: read-only bind for each populated mount
root (`/mnt/community` etc.), `/mnt/worktrees` read-write when promoted layers
exist — matching the entrypoint's addons scan. `BackendError` family:
`DockerUnavailableError`, `ImageNotFoundError`, `PostgresReadinessError`,
`ContainerRunError`, `InstanceNotFoundError`, `InstanceExistsError` — pure,
message-only, mirroring `ResolutionError`/`WorkspaceError`.

**`PortConflict` (fix #2)**: the spec listed `PortConflict` "at minimum" in the
error taxonomy. With the DECIDED ephemeral host-port strategy above, host-port
collisions are structurally unreachable, so no `PortConflict`-equivalent is added
to this family. This deliberately supersedes the spec's `PortConflict`
requirement; the spec is amended in lockstep to record the supersession, so the
two documents do not leave a live contradiction.

## Testing Strategy

| Layer | What | Approach |
|---|---|---|
| Unit (core) | `plan_backend`, `instance_ref`, `sanitize_name`, `parse_status` | Plain manifest+`MaterializedState` fixtures; assert exact specs/labels/env/mounts, including the named PG data volume AND the named Odoo-filestore volume (`plan.volumes`). **Env**: Postgres `{POSTGRES_PASSWORD,POSTGRES_USER,POSTGRES_DB}`, Odoo `{DB_HOST,DB_PORT,DB_USER,DB_PASSWORD,POSTGRES_DB}` matching `entrypoint.sh:143-159`; no `DB_NAME`. **`sanitize_name`**: already-valid (unchanged, no suffix), empty-after-sanitize, invalid-first-char, and two distinct raw names sharing a sanitized stem -> distinct deterministic outputs (always-on lossy-hash rule). **`parse_status`**: `starting`/`unhealthy`/`healthy`, null-health per role for a RUNNING container, EXITED Odoo (`Running=false`, null health -> exited NOT unknown), empty/absent inspect (not-running, no raise). Zero I/O. |
| Unit (adapter) | run/status/stop/logs/exec, rollback, typed errors | `monkeypatch.setattr(subprocess, "run", fake)` like `test_git_provider.py`; assert exact `docker` argv, inspect-JSON parsing, reverse-order rollback argv on injected failure covering ONLY resources this run created (`docker rm -f -v` for created containers, `docker volume rm` for volumes created this run, `docker network rm`), a **reattach-then-fail** case proving a pre-existing named PG/filestore volume is NOT pushed and NOT removed on rollback, `stop` argv (stop + `rm -f -v`, network rm, named PG + filestore volumes preserved), error classification: image-not-found, daemon-down via BOTH `FileNotFoundError` and the `Cannot connect to the Docker daemon` stderr marker, pg-timeout. Injectable sleep/clock seam makes poll/timeout paths deterministic. `LANG=C`/`LC_ALL=C` set on the subprocess env. Zero real docker. |
| Contract | Protocol conformance | `isinstance(DockerBackendProvider(), BackendProvider)` PLUS an explicit signature-conformance test (`inspect.signature` per method), because `runtime_checkable` verifies method names only, not signatures/returns. |
| Integration | real `run`->`status`->`stop`, PG bootstrap race, Odoo `Health=healthy` wait | `@pytest.mark.integration`, opt-in, deselected from the default Strict-TDD unit run (needs a real daemon). Covers the residual pg first-boot race and the Odoo readiness gate that are only observable against a live daemon. |

import-linter: 5th contract forbids `odoo_forge -> odoo_forge_docker`; `docker`
already forbidden from core.

## Migration / Rollout

No migration. Additive slice, no manifest/lock schema change. Revert the
feature-branch chain to remove cleanly; core stays import-clean.

## Resolved Decisions

- [x] Host port strategy: **DECIDED = ephemeral** host ports (`-p 0:8069`/
      `-p 0:8072`), with `status()` reporting the mapped host port from `docker
      inspect`. This drives the `PortConflict` supersession (see Interfaces /
      error family) and is no longer open.

## Open Questions

- [ ] Seeding: extension point only this slice (non-goal to implement).
