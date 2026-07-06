# Tasks: Phase 2 Slice 1 — Manifest Core

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | 900–1100 |
| 400-line budget risk | High |
| Chained PRs recommended | Yes |
| Suggested split | PR 1 → PR 2 → PR 3 |
| Delivery strategy | ask-on-risk |
| Chain strategy | pending |

Decision needed before apply: Yes
Chained PRs recommended: Yes
Chain strategy: pending
400-line budget risk: High

### Suggested Work Units

| Unit | Goal | Likely PR | Notes |
|------|------|-----------|-------|
| 1 | Project scaffold + schema (`CoreLayer`…`Manifest`) + tests | PR 1 | base = feature/tracker branch; tests travel with code |
| 2 | Lockfile/hash + composition + drift (pure core) + tests | PR 2 | base = PR 1 branch if feature-branch-chain, else main |
| 3 | `SourceProvider` port + `forge validate` CLI + import-linter + CI workflow | PR 3 | base = PR 2 branch if feature-branch-chain, else main |

## Phase 1: Foundation — Project Scaffold & Schema

- [x] 1.1 Create `pyproject.toml` (uv project, pydantic v2, pyyaml, typer deps; dev: pytest, import-linter; `[tool.importlinter]` contracts per design)
- [x] 1.2 Create `src/odoo_forge/__init__.py`, `src/odoo_forge/manifest/__init__.py`, `src/odoo_forge/ports/__init__.py` package markers
- [x] 1.3 RED: write `tests/manifest/test_schema.py::test_manifest_requires_core_field` — asserts `Manifest.core` is required `CoreLayer` (spec: Core layer is a first-class field)
- [x] 1.4 GREEN: implement `CoreLayer`, `GitRepo` in `src/odoo_forge/manifest/schema.py`
- [x] 1.5 RED: write `test_schema.py::test_core_default_url_and_ref_none` — default `url`, `ref=None`
- [x] 1.6 GREEN: implement `Manifest.core: CoreLayer = CoreLayer()` default
- [x] 1.7 RED: write `test_schema.py::test_requires_edition_on_repo_and_layer` — `requires_edition` optional field accepted on `GitRepo` and layer variants
- [x] 1.8 GREEN: add `requires_edition: Literal["enterprise"] | None = None` to `GitRepo`, `PublishedLayer`, `GitLayer`
- [x] 1.9 RED: write `test_schema.py::test_discriminated_layer_single_error` — malformed layer yields exactly one error scoped to tagged `type`
- [x] 1.10 GREEN: implement `PublishedLayer`, `GitLayer`, `Layer = Annotated[PublishedLayer | GitLayer, Field(discriminator="type")]`
- [x] 1.11 RED: write `test_schema.py::test_client_and_override_and_manifest_parse` — full `Manifest.model_validate` on a valid fixture dict
- [x] 1.12 GREEN: implement `Client`, `Override`, `Manifest` per design interfaces
- [x] 1.13 Create `tests/fixtures/valid.project.yaml` and `tests/fixtures/malformed.project.yaml`

## Phase 2: Core Implementation — Hash, Composition, Drift

- [ ] 2.1 RED: write `tests/manifest/test_lockfile.py::test_hash_stable_across_key_order` — two semantically-equal manifests hash identically
- [ ] 2.2 GREEN: implement `compute_manifest_hash()` in `src/odoo_forge/manifest/lockfile.py` (sha256 over sorted-key `model_dump(mode="json")`)
- [ ] 2.3 GREEN: implement `ResolvedRepo`, `ResolvedLayer`, `Lockfile` models in `lockfile.py`
- [ ] 2.4 Create `src/odoo_forge/manifest/errors.py` with `ManifestError`, `CompositionError`
- [ ] 2.5 RED: write `tests/manifest/test_composition.py::test_onion_order_core_first_client_last`
- [ ] 2.6 GREEN: implement `compose()` ordering logic in `src/odoo_forge/manifest/composition.py`
- [ ] 2.7 RED: write `test_composition.py::test_community_rejects_nested_enterprise_repo` (spec: enterprise repo nested in localization rejected)
- [ ] 2.8 GREEN: implement edition-coherence check (recursive repo/layer scan) in `compose()`
- [ ] 2.9 RED: write `test_composition.py::test_override_missing_layer_raises_no_io`
- [ ] 2.10 GREEN: implement override-target validation in `compose()`
- [ ] 2.11 Create `tests/fixtures/odoo-idp.project.yaml` (core odoo/odoo@19.0, enterprise layer, ~17 ingadhoc repos incl. `odoo-argentina-ee` requires_edition:enterprise, edition:enterprise)
- [ ] 2.12 RED: write `test_composition.py::test_odoo_idp_fire_test_composes_cleanly`
- [ ] 2.13 GREEN: verify fixture composes with zero I/O (fix any schema/composition gaps found)
- [ ] 2.14 Create `src/odoo_forge/manifest/state.py` with `MaterializedState`, `MaterializedLayer`
- [ ] 2.15 RED: write `tests/manifest/test_drift.py::test_clean_state_is_clean`
- [ ] 2.16 RED: write `test_drift.py::test_manifest_changed_lock_stale`
- [ ] 2.17 RED: write `test_drift.py::test_lock_state_drift_and_none_inputs`
- [ ] 2.18 GREEN: implement `DriftReport`, `detect_drift()` in `src/odoo_forge/manifest/drift.py` (pure, three in-memory models)

## Phase 3: Integration — Port, CLI, Arch Gate

- [ ] 3.1 Create `src/odoo_forge/ports/source_provider.py` with `SourceProvider` Protocol (`resolve_ref`), no adapter this slice
- [ ] 3.2 RED: write `tests/cli/test_validate.py::test_valid_manifest_exits_zero`
- [ ] 3.3 RED: write `test_validate.py::test_malformed_manifest_single_cause_error_nonzero_exit`
- [ ] 3.4 RED: write `test_validate.py::test_reports_manifest_lock_drift_when_lock_exists`
- [ ] 3.5 GREEN: implement `src/odoo_forge_cli/__init__.py` + `main.py` Typer app `forge validate [--manifest project.yaml]` delegating to core (parse → compose → drift → print)
- [ ] 3.6 Add `[tool.importlinter]` contracts to `pyproject.toml` (core-is-pure: forbid docker/boto3/kubernetes/git/typer/subprocess/requests/httpx; core-ignores-cli: forbid `odoo_forge_cli`)
- [ ] 3.7 Verify `uv run lint-imports` passes with zero violations
- [ ] 3.8 Create `.github/workflows/quality.yml` (paths filter `src/**, tests/**, pyproject.toml, .github/workflows/**`; steps: setup-uv → uv sync → lint-imports (blocking) → pytest)

## Phase 4: Verification

- [ ] 4.1 Run full suite `uv run pytest` — confirm all RED tests now GREEN, no skips
- [ ] 4.2 Run `uv run lint-imports` locally to confirm the CI gate mirrors local result
- [ ] 4.3 Manual smoke: `forge validate --manifest tests/fixtures/odoo-idp.project.yaml` exits 0
