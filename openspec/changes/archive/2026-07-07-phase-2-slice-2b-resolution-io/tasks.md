# Tasks: Phase 2 Slice 2b — Resolution I/O (Git Adapter + Forge Lock)

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | PR-1 ~250-350, PR-2 ~250-350 |
| 400-line budget risk | High (combined); Low-Medium per PR |
| Chained PRs recommended | Yes |
| Suggested split | PR 1 → PR 2 |
| Delivery strategy | ask-on-risk |
| Chain strategy | feature-branch-chain |

Decision needed before apply: Yes
Chained PRs recommended: Yes
Chain strategy: feature-branch-chain
400-line budget risk: High

### Suggested Work Units

| Unit | Goal | Likely PR | Notes |
|------|------|-----------|-------|
| 1 | `odoo_forge_git` adapter + `resolve_ref` + error taxonomy + 3rd import-linter contract | PR 1 | base = feature/tracker branch; no network in tests |
| 2 | `build_lock` use case + `forge lock` CLI + `_load_lock`→`from_json()` | PR 2 | base = PR 1 branch; depends on PR 1 merged/available |

Recommended review lenses: review-resilience + review-reliability (subprocess/network boundary, partial-failure modes).

## PR-1: Git Adapter, resolve_ref, Error Taxonomy, 3rd Contract — DONE (merged, PR #7)

### Phase 1: Foundation — Errors & Package Scaffold

- [x] 1.1 Create `src/odoo_forge_git/__init__.py` (new top-level package, sibling to `odoo_forge`)
- [x] 1.2 RED: `tests/manifest/test_errors.py::test_resolution_error_family` — `RefNotFoundError`/`AuthenticationError`/`NetworkError` are `ResolutionError` subclasses, separate from `ManifestError`
- [x] 1.3 GREEN: add `ResolutionError`, `RefNotFoundError(url, ref)`, `AuthenticationError(url)`, `NetworkError(url, detail)` to `src/odoo_forge/manifest/errors.py`

### Phase 2: Core — resolve_ref Behavior (Strict TDD, mocked subprocess only)

- [x] 2.1-2.16 all done (see PR-1 history)

### Phase 3: Integration — Import-Linter & Packaging

- [x] 3.1 Add `odoo_forge_git` to `pyproject.toml` root packages / wheel include
- [x] 3.2 Add 3rd `[[tool.importlinter.contracts]]`: forbidden, `source_modules = ["odoo_forge"]`, `forbidden_modules = ["odoo_forge_git"]`
- [x] 3.3 Verify `uv run lint-imports` reports 3 kept, 0 broken

**PR-1 Gate**: PASSED — merged to main via PR #7.

---

## PR-2: build_lock Use Case, forge lock CLI, from_json Wiring — DONE (this branch, not yet merged)

### Phase 4: Foundation — Pure build_lock Use Case

- [x] 4.1 Created `src/odoo_forge/manifest/locking.py`; `_FakeSourceProvider` test double in `tests/manifest/test_locking.py` (deterministic `resolve_ref` returning `f"sha-{ref}"`, no network)
- [x] 4.2 RED: `test_locking.py::test_core_ref_none_resolves_via_default_before_provider`
- [x] 4.3 GREEN: `build_lock(manifest, provider)` calls `resolve_default_ref` before `provider.resolve_ref` for core
- [x] 4.4 RED: `test_locking.py::test_git_layers_mapped_to_resolved_repos`
- [x] 4.5 GREEN: git-layer repo resolution loop implemented
- [x] 4.6 RED: `test_locking.py::test_published_layers_omitted_from_lock`
- [x] 4.7 GREEN: published-layer skip implemented (isinstance GitLayer gate)
- [x] 4.8 RED/GREEN: `test_locking.py::test_generated_from_matches_manifest_hash`
- [x] 4.9 RED/GREEN: `test_locking.py::test_composition_error_propagates_before_resolution` — `compose()` called before any `provider.resolve_ref`
- [x] 4.10 RED/GREEN: `test_locking.py::test_resolution_error_propagates_uncaught`
- [x] 4.11 GREEN: `compose(manifest)` gate + `generated_from` + error propagation all satisfied

Extra tests added beyond original list: `test_explicit_core_ref_used_directly` (explicit ref bypasses default-ref substitution).

### Phase 5: Integration — forge lock CLI Command

- [x] 5.1 RED: `tests/cli/test_lock.py::test_valid_manifest_writes_canonical_lock`
- [x] 5.2 GREEN: `_make_provider() -> SourceProvider` (returns `GitSourceProvider()`) + `forge lock [--manifest project.yaml]` command in `src/odoo_forge_cli/main.py`
- [x] 5.3 RED: `test_lock.py::test_resolution_error_exits_one_with_clean_message_no_traceback`
- [x] 5.4 GREEN: `try/except (ManifestError, ResolutionError)` around `build_lock` call in `lock` command
- [x] 5.5 RED: `test_lock.py::test_load_lock_uses_from_json_roundtrip`
- [x] 5.6 GREEN: `_load_lock` now calls `Lockfile.from_json(raw)` instead of `Lockfile.model_validate(json.loads(raw))`

Extra tests added: `test_core_ref_none_resolved_via_default_before_pinning`, `test_lock_then_validate_round_trip_no_drift`, `test_load_lock_rejects_invalid_json`.

### Phase 6: Verification

- [x] 6.1 Full suite `uv run pytest` — 79 passed, 0 failed, 0 skipped
- [x] 6.2 `uv run lint-imports` — 3 kept / 0 broken (no regression)
- [x] 6.3 Manual smoke: `forge --help` and `forge lock --help` both render correctly; unit-level CliRunner round-trip (`forge lock` → `forge validate`) covered in `test_lock_then_validate_round_trip_no_drift` (no real network — provider monkeypatched)

**PR-2 Gate**: PASSED. Diff vs main: 378 lines (< 400 budget). Commits on branch `sdd/phase-2-slice-2b-pr2-forge-lock`:
- fbe06cd feat(manifest): add build_lock use-case resolving refs via SourceProvider
- f4dffc9 feat(cli): add forge lock command; migrate _load_lock to from_json

## Scope Guardrails (respected, not violated)
- No override (fork/ref substitution) application during resolution — deferred, not implemented.
- Published layers are omitted from the lock, never recorded as empty `ResolvedLayer`.
- Single exit code 1 for all CLI errors — no differentiated codes.

## Overall Status
Both PR-1 and PR-2 complete. PR-1 merged to main (#7). PR-2 implemented on branch `sdd/phase-2-slice-2b-pr2-forge-lock`, not yet pushed/merged (per instructions — apply only implements, does not push/PR).
