```yaml
schema: gentle-ai.verify-result/v1
evidence_revision: sha256:826129c62e25e100f59b72920e83c62729cf6a4c
verdict: pass_with_warnings
blockers: 0
critical_findings: 0
requirements: 8/8
scenarios: 15/15
test_command: uv run pytest -q
test_exit_code: 0
test_output_hash: sha256:afd008915dfa95cc64a4be8d5f6326e4093c2127ae55c4f025f65adc27fb4c49
build_command: uv run mypy
build_exit_code: 0
build_output_hash: sha256:1d912ad9a40019f54ac8367f16d41aba6b15eb6127b2941995717ddcb8606bbe
lint_command: uv run ruff check .
lint_exit_code: 0
lint_output_hash: sha256:82b3e6a6c090a57601d22943bd23fca9218d1031dbe5a7b754092f9a156b4f18
format_command: uv run ruff format --check .
format_exit_code: 0
format_output_hash: sha256:35ff24d8a92c0ac97b235b057e7a009fcd264bc97ab856d529326a06c0fee756
```

## Verification Report

**Change**: `onboard-catalog-adapter`
**Version**: N/A
**Mode**: Strict TDD
**Action context**: post-merge verify — both chained PRs merged to `main` (PR1 #139, PR2 #143)
**Apply-progress source**: Engram topic `sdd/onboard-catalog-adapter/apply-progress` (id #10048) — covers PR1/Unit 1 only. No PR2/Unit 2 apply-progress artifact was found in Engram (searched broadly); PR2 completion is corroborated instead via `tasks.md`'s checked Phase 5-7 boxes and git history (`28d7669 feat(cli): wire forge onboard dual-mode dispatch to catalog adapter`, merged via PR #143 / commit `48c8b7e`).
**HEAD verified**: `826129c` (`main`, fully up to date with origin)

### Completeness

| Metric | Value |
|---|---:|
| Requirements total (catalog-index-adapter + manifest deltas) | 8 |
| Requirements fully compliant | 8 |
| Scenarios total | 15 |
| Scenarios compliant | 15 |
| Tasks total (checkbox items in tasks.md) | 53 |
| Tasks complete | 49 |
| Tasks incomplete | 4 (R.1–R.4 reconciliation-decision checkboxes) |

`tasks.md` Phases 1–7 (all numbered execution tasks, 1.1 through 7.7) are checked `[x]`. The only unchecked items are reconciliation decisions **R.1, R.2, R.3, R.4** in the "Reconciliation Decisions" section — R.5 is checked. Cross-referencing: the numbered tasks that *implement* each of R.1–R.4 (6.2 for R.1, 6.6 for R.2, 6.4 for R.3, 6.8 for R.4) are all checked and the corresponding behavior is verified below by passing tests (`test_onboard_rejects_both_manifest_and_client_supplied`, `test_onboard_catalog_source_error`, `test_onboard_catalog_driven_success` request construction, `test_onboard_catalog_pass_through_defaults_not_actioned`). This reads as a tracking/checkbox oversight in the decision log, not incomplete implementation — flagged as WARNING, not CRITICAL, since all corresponding functional tasks and their covering tests are complete and green.

### Build & Tests Execution

| Check | Exact command | Exit | Output hash | Result |
|---|---|---:|---|---|
| Full suite | `uv run pytest -q` | 0 | `sha256:afd008915dfa95cc64a4be8d5f6326e4093c2127ae55c4f025f65adc27fb4c49` | `945 passed, 17 deselected` |
| Focused change tests | `uv run pytest tests/adapters/test_catalog_index_provider.py tests/adapters/test_catalog_composition.py tests/cli/test_onboard.py -q` | 0 | (see terminal evidence above) | `33 passed` |
| Type checker | `uv run mypy` | 0 | `sha256:1d912ad9a40019f54ac8367f16d41aba6b15eb6127b2941995717ddcb8606bbe` | `Success: no issues found in 166 source files` |
| Linter | `uv run ruff check .` | 0 | `sha256:82b3e6a6c090a57601d22943bd23fca9218d1031dbe5a7b754092f9a156b4f18` | `All checks passed!` |
| Formatter | `uv run ruff format --check .` | 0 | `sha256:35ff24d8a92c0ac97b235b057e7a009fcd264bc97ab856d529326a06c0fee756` | `169 files already formatted` |

Note: apply-progress (PR1) reported one pre-existing unrelated mypy error in `tests/cli/test_backend.py`. That error is **not present** in the current clean `uv run mypy` run on `main` — either resolved by an intervening merge or specific to a different mypy invocation scope; current `main` is fully clean.

### Spec Compliance Matrix

| # | Capability | Requirement | Scenario | Runtime evidence | Result |
|---:|---|---|---|---|---|
| 1 | catalog-index-adapter | Concrete CatalogIndex Adapter | Structural conformance via isinstance | `tests/adapters/test_catalog_index_provider.py::test_yaml_catalog_index_is_structurally_a_catalog_index` | ✅ COMPLIANT |
| 2 | catalog-index-adapter | Concrete CatalogIndex Adapter | Matching request returns matching records | `tests/adapters/test_catalog_index_provider.py::test_find_matches_returns_matching_record` | ✅ COMPLIANT |
| 3 | catalog-index-adapter | Concrete CatalogIndex Adapter | Non-matching request returns an empty list | `tests/adapters/test_catalog_index_provider.py::test_find_matches_returns_empty_list_when_no_match` | ✅ COMPLIANT |
| 4 | catalog-index-adapter | Concrete CatalogIndex Adapter | Ambiguous match passes through unresolved | `tests/adapters/test_catalog_index_provider.py::test_find_matches_returns_all_ambiguous_matches` | ✅ COMPLIANT |
| 5 | catalog-index-adapter | Composition-Root Factory | Factory returns a protocol-conforming instance | `tests/adapters/test_catalog_composition.py::test_make_catalog_index_returns_protocol_conforming_instance` | ✅ COMPLIANT |
| 6 | catalog-index-adapter | Import Boundary Isolation | import-linter enforces purity | `uv run lint-imports` — 7 contracts kept (per apply-progress task 7.4; re-verified via `pyproject.toml` contract present, no core→adapter import found in diff) | ✅ COMPLIANT |
| 7 | manifest | Mutually exclusive dispatch modes | Both manifest and client supplied | `tests/cli/test_onboard.py::test_onboard_rejects_both_manifest_and_client_supplied` | ✅ COMPLIANT |
| 7b | manifest | Mutually exclusive dispatch modes | Neither manifest nor client supplied | `tests/cli/test_onboard.py::test_onboard_rejects_neither_manifest_nor_client_supplied` | ✅ COMPLIANT |
| 8 | manifest | `--manifest` local-input behavior unchanged | Local-input mode behaves as before | `tests/cli/test_onboard.py::test_onboard_projects_valid_local_inputs_and_prints_next_step` (+ 8 sibling pre-existing manifest-mode cases, all still passing unmodified) | ✅ COMPLIANT |
| 9 | manifest | `<cliente>` resolves/materializes/starts instance | Successful catalog-driven onboarding | `tests/cli/test_onboard.py::test_onboard_catalog_driven_success` | ✅ COMPLIANT |
| 10 | manifest | `<cliente>` resolves/materializes/starts instance | Backend failure leaves no orphaned instance | `tests/cli/test_onboard.py::test_onboard_catalog_driven_backend_failure_no_orphan` | ✅ COMPLIANT |
| 11 | manifest | Distinguishable resolution failure errors | Catalog record not found | `tests/cli/test_onboard.py::test_onboard_catalog_not_found` | ✅ COMPLIANT |
| 12 | manifest | Distinguishable resolution failure errors | Ambiguous client identifier | `tests/cli/test_onboard.py::test_onboard_catalog_ambiguous` | ✅ COMPLIANT |
| 13 | manifest | Distinguishable resolution failure errors | Invalid catalog record | `tests/cli/test_onboard.py::test_onboard_catalog_invalid_record` | ✅ COMPLIANT |
| 14 | manifest | Pass-through-only catalog fields | Resolved defaults are not actioned | `tests/cli/test_onboard.py::test_onboard_catalog_pass_through_defaults_not_actioned` | ✅ COMPLIANT |
| 15 | manifest | (adapter-level `CatalogSourceError` distinguishability, cross-cutting R.2) | Catalog source error rendered distinctly from resolver failures | `tests/cli/test_onboard.py::test_onboard_catalog_source_error` | ✅ COMPLIANT |

**Compliance summary**: 15/15 scenarios compliant (8/8 requirements across both spec deltas).

### Correctness (Static Evidence)

| Requirement | Status | Notes |
|---|---|---|
| Concrete CatalogIndex Adapter | ✅ Implemented | `src/odoo_forge_catalog/provider.py`'s `YamlCatalogIndex.find_matches` reads `catalog.yaml`, does no tie-breaking/defaulting, filters purely on `request.supplied_dimensions()`. |
| Composition-Root Factory | ✅ Implemented | `_make_catalog_index()` in `src/odoo_forge_cli/_composition.py`, same shape as `_make_backend_provider`/`_make_workspace_provider`. |
| Import Boundary Isolation | ✅ Implemented | `pyproject.toml` registers `odoo_forge_catalog` in wheel packages, importlinter root_packages, and a new "Core never imports the catalog adapter" contract. |
| Mutually exclusive dispatch modes | ✅ Implemented | `onboard`'s signature uses `client: str \| None` / `manifest: Path \| None` sentinels; both-given/neither-given guarded before any I/O, raising `ManifestError` per R.1 wording. |
| `--manifest` unchanged behavior | ✅ Implemented | Legacy branch (`_onboard_manifest_mode`) preserved byte-identical; regression gate (`test_onboard_manifest_mode_unchanged`-equivalent pre-existing cases) all pass. |
| `<cliente>` resolve/materialize/start | ✅ Implemented | Catalog branch (`_onboard_catalog_mode`) calls `_make_catalog_index()` → `ProjectCatalogResolver(...).resolve(request)` → reuses `plan_projection`/`project_workspace`/`plan_backend`/`DockerBackendProvider.run` verbatim. |
| Distinguishable resolution failure errors | ✅ Implemented | `ProjectCatalogResolutionFailure.type` rendered directly in the single `error:` line (`catalog-not-found`/`ambiguous-resolution`/`invalid-catalog`); `CatalogSourceError` caught in its own clause per R.2, producing a fourth, distinguishable message class. |
| Pass-through-only catalog fields | ✅ Implemented | `resolved.data_policy_default`/`resolved.target_default` are not referenced anywhere in the new branch (confirmed via task 6.10 self-check and by inspecting the diff — no reads of those attributes beyond the model itself). |

### Coherence (Design)

| Decision | Followed? | Notes |
|---|---|---|
| Single YAML catalog file (`records:` key, default `catalog.yaml`) | ✅ Yes | `YamlCatalogIndex.__init__(catalog_path: Path = Path("catalog.yaml"))`, `provider.py` reads top-level `records:` list. |
| Record shape mirrors `CatalogRecord` 1:1, no translation layer | ✅ Yes | `CatalogRecord.model_validate(raw_record)` per entry, same pattern as `Manifest.model_validate(data)`. |
| Adapter raises `CatalogSourceError` only for source-level failures, never for no-match/ambiguous | ✅ Yes | Confirmed by `test_find_matches_returns_empty_list_when_no_match` (returns `[]`, no raise) vs. `test_find_matches_raises_catalog_source_error_when_file_missing`/malformed-yaml/malformed-record (raises). |
| Onboard CLI signature uses `None` sentinels, not `Path("project.yaml")` literal default | ✅ Yes | `client: str \| None = typer.Argument(None)`, `manifest: Path \| None = typer.Option(None, "--manifest")`, confirmed via diff of `commands/manifest.py`. |
| `source_context`/defaults transported but never fed into `plan_projection`/`plan_backend` | ✅ Yes | Confirmed no reads of those fields outside the `ResolvedCatalogResult` model; `test_onboard_catalog_pass_through_defaults_not_actioned` exercises this. |
| No changes to `CatalogIndex`, `CatalogRecord`, `ProjectCatalogResolver`, `plan_backend`, `plan_projection`, `project_workspace`, `DockerBackendProvider.run` (frozen-symbol constraint) | ✅ Yes | See "Frozen-Symbol Constraint" section below — verified via full-diff grep and per-file `git diff`, zero changes. |

### Frozen-Symbol Constraint (proposal.md "Out of Scope" / design.md "Interfaces / Contracts")

Verified via `git diff 56ce564^ 826129c` (pre-PR1 base → post-PR2 merge) restricted to the five frozen files:

| File | Symbol | Diff |
|---|---|---|
| `src/odoo_forge/project_catalog/resolver.py` | `ProjectCatalogResolver` | No changes (empty diff) |
| `src/odoo_forge/backend/plan.py` | `plan_backend` | No changes (empty diff) |
| `src/odoo_forge_docker/provider.py` | `DockerBackendProvider.run` | No changes (empty diff) |
| `src/odoo_forge/manifest/projection.py` | `plan_projection`, `project_workspace` | No changes (empty diff) |

A full-diff grep for these five symbol names surfaces only: (a) proposal/design/tasks.md prose describing reuse, and (b) new import/call sites in `src/odoo_forge_cli/commands/manifest.py` (`from odoo_forge.backend.plan import plan_backend`, `from odoo_forge.project_catalog.resolver import ProjectCatalogResolver`, calls to `plan_projection(...)`/`project_workspace(...)`/`plan_backend(...)`). No definition of any frozen symbol was touched. Constraint **held**.

One in-scope core change occurred, explicitly called out and justified in `tasks.md` R.5: `@runtime_checkable` added to `CatalogIndex` in `src/odoo_forge/project_catalog/interfaces.py` (3-line diff) — this is not one of the five frozen symbols and was required for the `isinstance` scenarios to pass without raising `TypeError`.

### TDD Compliance

| Check | Result | Details |
|---|---|---|
| TDD evidence reported | ⚠️ Partial | PR1's TDD Cycle Evidence is documented in Engram (`sdd/onboard-catalog-adapter/apply-progress`, id #10048): RED written first (`tests/adapters/test_catalog_index_provider.py` — 7 cases confirmed failing with ImportError/AttributeError before implementation), GREEN confirmed. No equivalent apply-progress artifact was retrievable for PR2 (Phase 5–7, `onboard` dispatch); `tasks.md` narrates the RED→GREEN sequence in-line (5.12 "confirm... fail", 6.11 "confirm... passes") but this is not a separately persisted apply-progress record. |
| All tasks have tests | ✅ | Every checked numbered task (1.x–7.x) maps to an existing, passing test file. |
| RED confirmed (tests exist) | ✅ | `tests/adapters/test_catalog_index_provider.py`, `tests/adapters/test_catalog_composition.py`, `tests/cli/test_onboard.py` all exist and were inspected directly. |
| GREEN confirmed (tests pass) | ✅ | Full suite (945 passed) and focused re-run (33 passed) both green on current `main`. |
| Triangulation adequate | ✅ | Adapter tests cover match/no-match/ambiguous/missing-file/malformed-yaml/malformed-record/isinstance/alias-matching (12 cases); CLI tests cover both-given/neither-given/success/backend-failure/not-found/ambiguous/invalid/source-error/pass-through/enterprise-credential (21 cases) — distinct expected values and exit codes per case, no repeated trivial assertions. |
| Safety Net for modified files | ✅ | `tests/cli/test_onboard.py`'s pre-existing manifest-mode cases (`test_onboard_projects_valid_local_inputs_and_prints_next_step` and 7 siblings) all still pass unmodified — confirms no regression to the modified `commands/manifest.py`. |

**TDD Compliance**: 5/6 checks fully passed, 1 partial (missing persisted PR2 apply-progress record; functionally uncompromised since tasks.md + live tests corroborate the same claims).

### Test Layer Distribution

| Layer | Tests | Files | Tools |
|---|---:|---:|---|
| Unit | 12 | 2 | pytest |
| Integration (CLI) | 21 | 1 | pytest, Typer `CliRunner` (includes 2 cases from one `@pytest.mark.parametrize`) |
| E2E | 0 | 0 | not installed / not used |
| **Total** | **33** | **3** | |

### Assertion Quality

Sampled `tests/adapters/test_catalog_index_provider.py` and `tests/cli/test_onboard.py` in full. All assertions check concrete return values (`matches[0].record_id == "rec-acme"`), exception types/messages (`pytest.raises(CatalogSourceError, match="rec-broken")`), exit codes, exact `error:` line counts, and fake-provider call counts (`len(provider.checkout_calls) == 2`) — no tautologies, no ghost loops over possibly-empty collections, no ungrounded `toBeDefined()`-equivalents, no ratio of mocks far exceeding assertions.

**Assertion quality**: ✅ All assertions verify real behavior.

### Quality Metrics

**Linter**: ✅ No errors (`uv run ruff check .` clean).
**Formatter**: ✅ No diffs (`uv run ruff format --check .` clean, 169 files already formatted).
**Type Checker**: ✅ No errors (`uv run mypy` clean, 166 source files) — the pre-existing unrelated error noted in PR1's apply-progress is not present in the current run.
**Import Linter**: ✅ 7 contracts kept per apply-progress task 7.4 (not independently re-run this session; corroborated by static absence of any `odoo_forge_catalog` import inside `src/odoo_forge/`).

### Issues Found

#### CRITICAL

None.

#### WARNING

1. `tasks.md`'s Reconciliation Decisions R.1–R.4 remain unchecked (`- [ ]`) even though the numbered execution tasks that implement each decision (6.2, 6.6, 6.4, 6.8) are checked and covered by passing tests. This is a tracking-consistency gap in the artifact, not a functional gap — recommend ticking R.1–R.4 before archive for an accurate historical record.
2. No PR2-specific apply-progress artifact was found in Engram (searched `sdd/onboard-catalog-adapter/apply-progress`, `PR2 dispatch apply` broadly) — only the PR1/Unit-1 record (#10048) exists. PR2's TDD narrative lives only inline in `tasks.md`'s task descriptions (5.12/6.11/7.6/7.7), not as a separately persisted structured apply-progress record. Recommend persisting a PR2 apply-progress artifact retroactively if the pipeline requires one per-PR, or explicitly note in the archive that PR1+PR2 share one combined apply-progress record going forward.

#### SUGGESTION

None.

### Verdict

**PASS WITH WARNINGS**

Both requirement deltas (`catalog-index-adapter`, `manifest`) are fully implemented, all 15 scenarios have passing covering tests on current `main` (HEAD `826129c`), the frozen-symbol constraint held with zero diff to `ProjectCatalogResolver`/`plan_backend`/`DockerBackendProvider.run`/`plan_projection`/`project_workspace`, and `pytest`/`ruff check`/`ruff format --check`/`mypy` are all clean. The only findings are two tracking/documentation WARNINGs (unchecked reconciliation-decision checkboxes; missing PR2 apply-progress artifact) — neither blocks archive.
