# Design: Catalog-Driven Onboarding (`forge onboard <cliente>`)

## Technical Approach

Add one new adapter package (`odoo_forge_catalog`) implementing `CatalogIndex`
against a single hand-authored YAML file, wire it through a new
`_make_catalog_index()` composition factory, and add a catalog-driven
dispatch branch to the existing `onboard` command. The catalog-driven branch
resolves a `ManifestRef` via the already-tested `ProjectCatalogResolver`,
then re-enters the *exact* existing manifest→lock→project→backend pipeline
(`plan_projection` → `project_workspace` → `plan_backend` →
`DockerBackendProvider.run`) used by `project`/`run` today. No core function
signature changes.

## Architecture Decisions

| Decision | Choice | Alternatives considered | Rationale |
|---|---|---|---|
| Catalog source format | Single YAML file, list of records under `records:`, path defaults to `catalog.yaml` (cwd), overridable by `--catalog` | (a) directory of per-project files (b) TOML/JSON | Matches this repo's existing flat-file, hand-authored declarative convention (`project.yaml`, `project.lock`, `credentials.sops.yaml`); one file is trivially diffable/reviewable for a small client roster. Directory-per-project deferred — natural future split when the file grows large, no contract change needed since it's adapter-internal. |
| Record shape on disk | Mirrors `CatalogRecord` fields 1:1 (`record_id`, `client_key`, `project_key`, `aliases`, `manifest_ref`, `source_context`, `defaults`) | Flattened/renamed on-disk keys | Zero translation layer — `CatalogRecord.model_validate(raw_record)` per entry, same pattern as `Manifest.model_validate(data)` in `manifest.py`. |
| Adapter error boundary | Adapter raises its own `CatalogSourceError` (new, in `odoo_forge_catalog/errors.py`) only for source-level failures (missing file, malformed YAML, malformed record schema). `find_matches` never raises for "no match"/"ambiguous" — those stay `ProjectCatalogResolutionFailure` cases owned by the resolver. | Adapter swallows source errors into an empty match list | An empty list would silently misreport a broken catalog as "not found," hiding an ops mistake. Distinct exception type lets the CLI render a distinguishable message. |
| Onboard CLI signature | `client: str \| None = typer.Argument(None)`, `manifest: Path \| None = typer.Option(None, "--manifest")`. Both `None` → legacy default (`project.yaml`, unchanged). Both given → error, exit 1. Only `client` → catalog path. Only `manifest` → legacy path (today's behavior, byte-identical). | Keep `manifest` defaulting to `Path("project.yaml")` and infer explicitness from Typer context | `Path("project.yaml")` as a literal default is indistinguishable from an explicit `--manifest project.yaml`; using `None` sentinels makes mutual-exclusivity and "neither given" detectable without touching Typer internals. **Flagged for spec reconciliation**: exact error message/type for the both-given case is my call (`ManifestError("onboard accepts either a client name or --manifest, not both")`), pending alignment with the parallel sdd-spec output for the `manifest` capability. |
| `source_context`/defaults handling | Transported on `ResolvedCatalogResult`, read by the CLI for future logging only — never fed into `plan_projection`/`plan_backend`, which keep taking `Manifest`+`Lockfile`+`host_roots` exactly as before. | Feed `source_context.repos` into a new projection path bypassing the manifest file | ADR-0001: no remote/target actioning this slice. `plan_projection`/`plan_backend` are explicitly frozen (must-not-modify). The manifest file at `manifest_ref.manifest_path` remains the single source of repo declarations; `source_context` is catalog-authority metadata, not a competing repo list. |

## Data Flow

    forge onboard <client>
        │
        ▼
    _composition._make_catalog_index()  ──▶ YamlCatalogIndex(catalog_path)
        │
        ▼
    ProjectCatalogResolver.resolve(request)
        │
        ├─▶ ProjectCatalogResolutionFailure (not-found/ambiguous/invalid)
        │        └─▶ typer.echo("error: <type>: <details>"); exit 1
        │
        └─▶ ResolvedCatalogResult
                 │  (manifest_ref.manifest_path)
                 ▼
        [existing pipeline, unchanged]
        _read_manifest_data → Manifest.model_validate → compose
              → _load_lock (project.lock alongside manifest_path)
              → plan_projection → project_workspace
              → plan_backend → DockerBackendProvider.run

## File Changes

| File | Action | Description |
|---|---|---|
| `src/odoo_forge_catalog/__init__.py` | Create | Package init, exports `YamlCatalogIndex` |
| `src/odoo_forge_catalog/provider.py` | Create | `YamlCatalogIndex.find_matches`, YAML load + per-record `CatalogRecord.model_validate` |
| `src/odoo_forge_catalog/errors.py` | Create | `CatalogSourceError` |
| `src/odoo_forge_cli/_composition.py` | Modify | Add `_make_catalog_index(*, catalog_path: Path = Path("catalog.yaml"))` |
| `src/odoo_forge_cli/commands/manifest.py` | Modify | `onboard` signature + dispatch branch; both-given error |
| `pyproject.toml` | Modify | Add `odoo_forge_catalog` to wheel packages, importlinter root_packages, new forbidden-import contract |
| `tests/adapters/test_catalog_index_provider.py` | Create | match/no-match/ambiguous-passthrough/source-error cases |
| `tests/cli/test_manifest_onboard.py` (or extend existing) | Modify | catalog-driven mode + both-given + neither-given coverage |

## Interfaces / Contracts

```python
# odoo_forge_catalog/provider.py
class YamlCatalogIndex:
    def __init__(self, catalog_path: Path = Path("catalog.yaml")) -> None: ...
    def find_matches(self, request: ProjectCatalogRequest) -> list[CatalogRecord]: ...
```

No changes to `CatalogIndex`, `CatalogRecord`, `ProjectCatalogResolver`, `plan_backend`, `plan_projection`, `project_workspace`, or `DockerBackendProvider.run`.

## Testing Strategy

| Layer | What to Test | Approach |
|---|---|---|
| Unit | `YamlCatalogIndex` match/no-match/ambiguous/malformed-source | Faked catalog file fixtures, no real disk I/O beyond tmp_path |
| Unit | `_make_catalog_index()` returns a `CatalogIndex`-conforming instance | `isinstance` check |
| Integration (CLI) | `onboard <client>` end-to-end via fake `CatalogIndex` + fake `BackendProvider` | Assert rendered output/exit code, not call order (per proposal) |
| Integration (CLI) | `onboard --manifest <path>` unchanged | Re-run existing test suite unmodified as regression gate |
| Integration (CLI) | both-given / neither-given dispatch | New cases asserting exit code 1 + single `error:` line for both-given |

## Threat Matrix

N/A — no routing, shell, subprocess, VCS/PR automation, executable-file classification, or process-integration boundary. The new adapter only parses a local YAML file already trusted at the same level as `project.yaml`/`credentials.sops.yaml`.

## Migration / Rollout

No migration required. Purely additive: new package, new factory, new dispatch branch. `catalog.yaml` does not need to exist for the legacy `--manifest` path to keep working (untouched code path, no catalog read attempted).

## Open Questions

- [ ] Exact wording/type for the both-given (`client` + `--manifest`) error — flagged for spec reconciliation with the parallel `manifest` capability delta, since no spec.md for that dispatch branch was found alongside this design.
- [ ] Whether `CatalogSourceError` should render under its own `error:` prefix or be folded into the `invalid-catalog` message class for CLI consistency — currently designed as distinct, open for spec confirmation.
