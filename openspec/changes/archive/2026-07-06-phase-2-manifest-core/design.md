# Design: Phase 2 Slice 1 — Manifest Core (pure domain)

## Technical Approach

Deliver a PURE Pydantic v2 domain (`odoo_forge`) plus a thin Typer CLI
(`odoo_forge_cli`), gated by import-linter from commit one. Maps directly to the
approved slice design §3/§7/§8 and platform spec §6.1 (hexagonal + screaming
structure). This design confirms that layout and closes the three proposal
amendments (`core` field, per-repo `requires_edition`, explicit discriminated
union) plus the hash-purity clarification. Domain-first strict TDD: every model
and function is designed so tests are writable before implementation, with zero
disk/network — `detect_drift` receives three in-memory models.

## Architecture Decisions

| Decision | Choice | Rejected | Rationale |
|----------|--------|----------|-----------|
| Package layout | `src/` layout, `odoo_forge` core + `odoo_forge_cli`; core sub-pkgs `manifest/`, `ports/` | flat layout; single package | tests import installed pkg, not tree; two root pkgs let import-linter forbid core→CLI |
| Core base pin | first-class `Manifest.core: CoreLayer` | freeform `layers` entry | exactly-one always-present base deserves a required field; carries intent only |
| Edition gating | per-artifact `requires_edition` on `GitRepo` + each layer | whole-layer check | catches `odoo-argentina-ee` nested in localization |
| Union parsing | explicit `Field(discriminator="type")` w/ `Literal` tags | smart-mode union | single-member errors; smart-mode gives ambiguous dual errors |
| Manifest hash | sha256 over canonical `model_dump(mode="json")` w/ sorted keys | raw file bytes | keeps hashing pure, immune to formatting/whitespace |
| Port style | `typing.Protocol` (`@runtime_checkable`) | ABC | structural typing, zero coupling, adapters need not import core base class |
| CLI framework | Typer, thin, in separate pkg | Click/argparse; core-embedded | forbidden in core by import-linter; presentation only |
| Tooling | uv + `pyproject.toml`, `[tool.importlinter]` inline | poetry; standalone `importlinter.ini` | project standard (spec §6.3); one config file |

### Hash canonicalization (concrete)

`compute_manifest_hash(m: Manifest) -> str` = `sha256(m.model_dump_json().encode()).hexdigest()`
with models declared under `model_config = ConfigDict(...)` and dumping via a
canonical form: `json.dumps(m.model_dump(mode="json"), sort_keys=True,
separators=(",", ":"))`. Sorted keys + compact separators make the hash
independent of field declaration order and YAML formatting. Pure: no `pathlib`,
no file read. `Lockfile.generated_from` stores this digest.

## Data Flow

    project.yaml ──(CLI: yaml.safe_load)──▶ dict
         │
         ▼
    Manifest.model_validate(dict)      [core/schema]
         │
         ├──▶ compose(manifest) ──▶ ordered [Layer] | CompositionError   [core/composition]
         │
    project.lock ─(CLI load)─▶ Lockfile.model_validate
         │                         │
         ▼                         ▼
    MaterializedState (Slice 3 adapter; None here)
         │
         ▼
    detect_drift(manifest, lock, materialized) ──▶ DriftReport   [core/drift, PURE]
         │
         ▼
    CLI renders report / errors (exit code)   [odoo_forge_cli]

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `pyproject.toml` | Create | uv project, deps + `[tool.importlinter]` contracts |
| `src/odoo_forge/__init__.py` | Create | package marker |
| `src/odoo_forge/manifest/schema.py` | Create | `CoreLayer`, `GitRepo`, `PublishedLayer`, `GitLayer`, `Layer`, `Client`, `Override`, `Manifest` |
| `src/odoo_forge/manifest/lockfile.py` | Create | `ResolvedRepo`, `ResolvedLayer`, `Lockfile`, `compute_manifest_hash` |
| `src/odoo_forge/manifest/composition.py` | Create | `compose()` order + coherence |
| `src/odoo_forge/manifest/drift.py` | Create | `DriftReport`, `detect_drift()` (pure) |
| `src/odoo_forge/manifest/state.py` | Create | `MaterializedState`, `MaterializedLayer` |
| `src/odoo_forge/manifest/errors.py` | Create | `ManifestError`, `CompositionError` |
| `src/odoo_forge/ports/source_provider.py` | Create | `SourceProvider` Protocol (interface only) |
| `src/odoo_forge_cli/__init__.py` / `main.py` | Create | Typer app: `forge validate` |
| `tests/manifest/test_*.py` | Create | schema, composition, drift unit tests |
| `tests/fixtures/*.project.yaml` | Create | valid + malformed + odoo-idp fire test |
| `.github/workflows/quality.yml` | Create | import-linter + pytest gate (mirrors actionlint job) |

## Interfaces / Contracts

```python
# manifest/schema.py
class GitRepo(BaseModel):
    url: str
    ref: str
    requires_edition: Literal["enterprise"] | None = None

class CoreLayer(BaseModel):
    type: Literal["core"] = "core"
    url: str = "https://github.com/odoo/odoo.git"
    ref: str | None = None  # defaults to odoo_version branch at compose (Slice 2)

class PublishedLayer(BaseModel):
    type: Literal["published"]
    name: str
    source: str          # registry://.../odoo-ee
    version: str
    requires_edition: Literal["enterprise"] | None = None

class GitLayer(BaseModel):
    type: Literal["git"]
    name: str
    repos: list[GitRepo]
    requires_edition: Literal["enterprise"] | None = None

Layer = Annotated[PublishedLayer | GitLayer, Field(discriminator="type")]

class Client(BaseModel):
    addons_path: Path
    python_requirements: Path | None = None

class Override(BaseModel):
    layer: str; repo: str; fork: str; ref: str

class Manifest(BaseModel):
    name: str
    odoo_version: str
    edition: Literal["community", "enterprise"]
    core: CoreLayer = CoreLayer()
    layers: list[Layer] = []
    client: Client
    overrides: list[Override] = []
```

```python
# ports/source_provider.py — Protocol, no adapter this slice
@runtime_checkable
class SourceProvider(Protocol):
    def resolve_ref(self, url: str, ref: str) -> str: ...   # ref -> commit SHA (Slice 2)
```

`compose(manifest) -> list[Layer]` coherence rules (raise `CompositionError`):
1. **Onion order** — fixed chain `core → published/git layers (declared order) →
   client` (client always last/writable).
2. **Edition gating** — if `edition == "community"`, no `layer.requires_edition`
   nor any `GitRepo.requires_edition == "enterprise"` may appear.
3. **Override target** — every `Override.layer` must match an existing layer
   `name`; `Override.repo` must exist within that layer's `repos`.

`detect_drift(manifest, lock, materialized) -> DriftReport`:
- `manifest_lock_drift`: `lock is None` OR
  `lock.generated_from != compute_manifest_hash(manifest)`.
- `lock_state_drift`: per-layer/commit mismatch between `lock` and
  `materialized` (skipped when `materialized is None`).
- `is_clean`: both lists empty.

## Testing Strategy

| Layer | What to Test | Approach |
|-------|-------------|----------|
| Unit — schema | valid parse; discriminator selects right member; malformed → single-member error; `core` default; `requires_edition` accepted | `model_validate` on fixture dicts |
| Unit — composition | onion order; community rejects enterprise repo/layer; override→missing layer/repo fails | in-memory `Manifest` objects |
| Unit — drift | clean; manifest≠lock (hash); lock≠state; `lock None`/`materialized None` | three in-memory models, no mocks |
| Unit — hash | stable across field/key reorder; formatting-independent | build two equal manifests |
| Fire test | express real `odoo-idp` (core `odoo/odoo@19.0`, 17 ingadhoc localization repos, `odoo-argentina-ee` `requires_edition: enterprise`) parses + composes | `tests/fixtures/odoo-idp.project.yaml` |
| Arch gate | core imports no docker/git/boto3/k8s/typer/subprocess/CLI | import-linter in CI |

## import-linter + CI

`[tool.importlinter]` in `pyproject.toml`:

```ini
[importlinter]
root_packages = odoo_forge, odoo_forge_cli

[importlinter:contract:core-is-pure]
name = Core never imports infrastructure or framework
type = forbidden
source_modules = odoo_forge
forbidden_modules = docker, boto3, kubernetes, git, typer, subprocess, requests, httpx

[importlinter:contract:core-ignores-cli]
name = Core never imports the CLI
type = forbidden
source_modules = odoo_forge
forbidden_modules = odoo_forge_cli
```

`.github/workflows/quality.yml` mirrors the Phase 1 `lint` job: single
`ubuntu-latest` job, `paths: [src/**, tests/**, pyproject.toml,
.github/workflows/**]`, steps `astral-sh/setup-uv` → `uv sync` →
`uv run lint-imports` (blocking) → `uv run pytest`. Blocking = wall, not
convention.

## Migration / Rollout

No migration. Pure additive `src/` tree; revert the branch to roll back. Phase 1
`factory/` untouched.

## Open Questions

- None blocking. `Layer.name → /mnt/*` mount mapping is explicitly Slice 3;
  noted so it is not lost.
