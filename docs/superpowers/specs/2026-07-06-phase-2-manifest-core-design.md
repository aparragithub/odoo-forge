# Phase 2 — Slice 1: Manifest Core (pure domain)

**Date:** 2026-07-06
**Status:** Approved design, pre-implementation
**Parent:** [Modular Odoo Platform — Product Design](../../specs/2026-07-05-modular-odoo-platform-design.md) §2.3, §6
**Phase:** 2 (CLI core + manifest + local backend) — first vertical slice

## 1. Scope

Phase 2 as written in the platform spec (§7) is three independent subsystems: the
manifest/lockfile domain, the workspace projection, and the local Docker backend.
Building them under one plan would let the design rot mid-way. This slice delivers
**only the first: the pure manifest core.** No git, no Docker, no network.

**In scope:**

- Pydantic v2 schemas for `project.yaml` (manifest) and `project.lock` (lockfile),
  modeled faithfully to platform spec §2.3.
- Onion composition logic (ordering + coherence validation).
- Drift detection as a pure function over three in-memory models.
- The `SourceProvider` port — interface only, no adapter.
- A thin `forge validate` CLI command.
- `import-linter` in CI on the first commit (gate #1 from the Phase 2 architecture
  assessment): the core never imports infrastructure or framework code.

**Explicitly deferred** (later slices, each its own spec → plan cycle):

- Git `SourceProvider` adapter + `forge lock` (resolve refs → SHAs). — Slice 2
- Workspace projection: pinned checkouts, read-only lower layers, unlock. — Slice 3
- Local Docker backend: run the instance. — Slice 4

## 2. Rationale for the decomposition

- **Pure first, infra later.** Resolving a pin (`ref: "19.0"` → commit SHA, or
  `registry://…` → digest) requires talking to a git host or registry. That is
  infrastructure and must live behind a port/adapter, never in the core (platform
  spec §6.1). Starting with the pure domain keeps the import-linter gate trivial
  to pass and forces the hexagonal boundary from commit one.
- **The contract is the deliverable.** The manifest schema is validated by the
  fire test — expressing the real `odoo-idp` project as a `project.yaml` (platform
  spec §7). That validation needs zero `git clone`. If the schema cannot express
  `odoo-idp`, the schema is wrong.
- **Full schema now (Approach 1).** Modeling the complete §2.3 schema (including
  `overrides`, used only in later slices) is cheap — it is declaration, not logic —
  and it closes the contract so the fire test can run. Rejected: a minimal schema
  (cannot express `odoo-idp` → cannot run the fire test) and a fire-test-derived
  schema (couples the product schema to one client — the §1 anti-pattern).

## 3. Architecture — package layout

`src/` layout, screaming the domain, hexagonal (platform spec §6.1):

```
odoo-forge/
  pyproject.toml            # uv; deps: pydantic v2, pyyaml, typer; dev: pytest, import-linter
  factory/                  # Phase 1 — untouched
  src/
    odoo_forge/             # THE CORE — zero infrastructure
      __init__.py
      manifest/
        schema.py           # Manifest, Layer (discriminated union), Client, Override, GitRepo
        lockfile.py         # Lockfile, ResolvedLayer, ResolvedRepo
        composition.py      # onion: order + coherence validation
        drift.py            # pure fn: (manifest, lock, materialized) -> DriftReport
        state.py            # MaterializedState model (populated by adapters later)
        errors.py           # domain exceptions
      ports/
        source_provider.py  # SourceProvider interface (Protocol/ABC) — no implementation
    odoo_forge_cli/         # thin CLI — delegates to the core
      __init__.py
      main.py               # Typer app: `forge validate`
  tests/
    manifest/               # domain tests (TDD)
    fixtures/               # example project.yaml + odoo-idp fire-test manifest
  importlinter.ini          # or [tool.importlinter] in pyproject.toml
```

Design points:

1. **`src/` layout** (not flat) so tests import the installed package, not the repo
   tree — kills "works in my tree, breaks installed".
2. **`ports/` separate from any backend.** This slice defines only the
   `SourceProvider` interface. Adapters (git, docker) are separate packages in
   later slices. The core depends on the interface, never an implementation.
3. **CLI in its own package** (`odoo_forge_cli`) from day 1, so import-linter can
   forbid the core from importing Typer and forbid the core from importing the CLI.

## 4. Domain model (Pydantic v2)

### 4.1 `manifest/schema.py` — intent

```python
class GitRepo(BaseModel):
    url: str
    ref: str

class PublishedLayer(BaseModel):          # layer consumed from a registry
    name: str
    source: str                            # registry://.../odoo-ee
    version: str                           # "19.0.2026-06-01"

class GitLayer(BaseModel):                 # layer assembled from git repos
    name: str
    repos: list[GitRepo]

Layer = PublishedLayer | GitLayer          # discriminated by field presence

class Client(BaseModel):
    addons_path: Path
    python_requirements: Path | None = None

class Override(BaseModel):                  # temporary fork/patch of a lower layer
    layer: str
    repo: str
    fork: str
    ref: str

class Manifest(BaseModel):
    name: str
    odoo_version: str                      # "19.0" — string, not enum (see below)
    edition: Literal["community", "enterprise"]
    layers: list[Layer] = []
    client: Client
    overrides: list[Override] = []
```

### 4.2 `manifest/lockfile.py` — resolution

```python
class ResolvedRepo(BaseModel):
    url: str
    ref: str
    commit: str                            # resolved SHA

class ResolvedLayer(BaseModel):
    name: str
    digest: str | None = None              # for image/published layers
    repos: list[ResolvedRepo] = []         # for git layers

class Lockfile(BaseModel):
    name: str
    odoo_version: str
    layers: list[ResolvedLayer] = []
    generated_from: str                    # hash of the manifest that produced it
```

Decisions:

1. **`generated_from` (manifest hash)** makes drift detection cheap: manifest
   changed but lock did not → hash mismatch → drift. No blind field-by-field diff.
2. **`odoo_version` is a string, not an enum.** The product must not bake in which
   versions exist — that lives in `factory/versions.yaml` (Phase 1). An enum would
   repeat the §1 sin of a hardcoded version.

## 5. Pure logic

### 5.1 `manifest/composition.py` — the onion

```python
def compose(manifest: Manifest) -> list[Layer]:
    """Order the layers in onion order and validate coherence (§2.1/§2.2):
      - edition=community MUST NOT declare an 'enterprise' layer
      - a layer referenced by an override MUST exist in layers
      - the client is always the final (writable) layer
    Returns the ordered chain. Raises CompositionError on incoherence.
    """
```

Compose is **not** materialize: it orders and validates the onion only — zero
checkout. Materialization is Slice 3.

### 5.2 `manifest/drift.py` — pure three-input function

```python
@dataclass(frozen=True)
class DriftReport:
    manifest_lock_drift: list[str]   # manifest changed, lock did not (hash mismatch)
    lock_state_drift: list[str]      # lock says X, filesystem has Y
    is_clean: bool

def detect_drift(
    manifest: Manifest,
    lock: Lockfile | None,
    materialized: MaterializedState | None,
) -> DriftReport:
    """PURE. Receives the three already-loaded models; does not read disk.
    The caller (an adapter/CLI) reads the filesystem and builds MaterializedState;
    the core only compares.
    """
```

`MaterializedState` (`manifest/state.py`) is a simple model describing which
layers/commits actually exist in a workspace. This slice only defines it; whoever
populates it arrives in Slice 3. Injecting it (not reading it) is what lets the
core be tested with three in-memory objects and no disk mocks.

## 6. CLI

`odoo_forge_cli/main.py`, Typer, thin. One command this slice:

```
forge validate [--manifest project.yaml]
```

Loads `project.yaml`, validates it against the schema, runs `compose()`, and if a
`project.lock` is present reports manifest↔lock drift. The CLI orchestrates and
presents; all logic lives in the core. The CLI may import the core; the core never
imports the CLI.

## 7. import-linter — the day-1 gate

Ships in the **first commit** (platform spec §6.1). Runs in CI as a blocking job,
same pattern as the Phase 1 `actionlint` gate. If the core imports infra, the build
is red — a wall, not a convention.

```ini
[importlinter]
root_packages = odoo_forge, odoo_forge_cli

[importlinter:contract:core-is-pure]
name = Core never imports infrastructure or framework
type = forbidden
source_modules = odoo_forge
forbidden_modules = docker, boto3, kubernetes, git, typer, subprocess

[importlinter:contract:core-ignores-cli]
name = Core never imports the CLI
type = forbidden
source_modules = odoo_forge
forbidden_modules = odoo_forge_cli
```

## 8. Testing (TDD, domain first)

Strict TDD (project convention). Test-first order:

1. `tests/manifest/test_schema.py` — valid parse, rejection of invalid input, the
   discriminated union picks the right layer type.
2. `tests/manifest/test_composition.py` — onion order; community rejects enterprise;
   override referencing a missing layer fails.
3. `tests/manifest/test_drift.py` — the three cases (clean, manifest≠lock,
   lock≠state) with in-memory models.
4. **Fire test** — `tests/fixtures/odoo-idp.project.yaml`: express the real
   `odoo-idp` project as a manifest. If the schema cannot express it, the schema is
   wrong (platform spec §7). This is the slice's acceptance criterion.

No disk/network mocks in the core — everything is in-memory objects.

## 9. Acceptance criteria

- `forge validate` parses and validates a well-formed `project.yaml`, reports clear
  errors on malformed input, and reports manifest↔lock drift when a lockfile exists.
- The fire-test fixture expressing `odoo-idp` parses and composes cleanly.
- `import-linter` passes and runs as a blocking CI job.
- Full domain test suite green; core has zero imports of docker/git/boto3/k8s/typer.

## 10. Out of scope (restated)

Pin resolution, git access, workspace checkouts, Docker, `forge lock`, `forge up`.
Each is a later slice with its own spec.
