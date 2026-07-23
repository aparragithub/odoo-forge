# Tasks: Verify & Formalize Module Dependency Validation

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~120-160 (test-only additions to one file) |
| 400-line budget risk | Low |
| Chained PRs recommended | No |
| Suggested split | Single PR |
| Delivery strategy | auto-forecast |
| Chain strategy | pending |

Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: pending
400-line budget risk: Low

### Suggested Work Units

| Unit | Goal | Likely PR | Focused test command | Runtime harness | Rollback boundary |
|------|------|-----------|----------------------|-----------------|-------------------|
| 1 | Add all 6 characterization tests to `tests/manifest/test_module_deps.py` | PR 1 | `uv run pytest tests/manifest/test_module_deps.py -v` | N/A — pure filesystem/unit tests via `tmp_path`, no external service | Revert the test-file diff only; `module_deps.py` untouched (or minimally patched, revert separately) |

## Phase 1: OSError Guard Characterization Tests

- [x] 1.1 Add `test_build_module_index_wraps_root_is_dir_os_error` in `tests/manifest/test_module_deps.py`: monkeypatch `Path.is_dir` to raise `OSError` for the root path only, call `build_module_index([root])`, assert `ValueError` naming the root path. Covers spec scenario "A root that raises OSError on is_dir() fails clean, naming the root".
- [x] 1.2 Run `uv run pytest tests/manifest/test_module_deps.py::test_build_module_index_wraps_root_is_dir_os_error -v`; confirm PASS against existing `module_deps.py` (root `is_dir()` guard at line 88-91). If it fails, escalate to a minimal fix in `module_deps.py` only, then re-run.
- [x] 1.3 Add `test_build_module_index_wraps_manifest_is_file_os_error` in `tests/manifest/test_module_deps.py`: write a real module dir with `_write_manifest`, monkeypatch `Path.is_file` to raise `OSError` when called on the `__manifest__.py` path, call `build_module_index([root])`, assert `ValueError` naming the manifest path. Covers "A manifest path that raises OSError on is_file() fails clean, naming the path".
- [x] 1.4 Run `uv run pytest tests/manifest/test_module_deps.py::test_build_module_index_wraps_manifest_is_file_os_error -v`; confirm PASS against existing guard (line 107-110). Escalate to minimal fix only if it fails.
- [x] 1.5 Add `test_build_module_index_wraps_read_text_os_error` in `tests/manifest/test_module_deps.py`: write a real module dir with `_write_manifest`, monkeypatch `Path.read_text` to raise `OSError`, call `build_module_index([root])`, assert `ValueError` naming the manifest path. Covers "A manifest that raises OSError on read_text() fails clean, naming the path".
- [x] 1.6 Run `uv run pytest tests/manifest/test_module_deps.py::test_build_module_index_wraps_read_text_os_error -v`; confirm PASS against existing guard (line 116-118). Escalate to minimal fix only if it fails.

## Phase 2: Multi-Root Precedence Characterization Tests

- [x] 2.1 Add `test_build_module_index_multi_root_first_match_wins` in `tests/manifest/test_module_deps.py`: create `root_a` and `root_b`, each with a module of the same name but different `depends:`, call `build_module_index([root_a, root_b])`, assert the resulting entry matches `root_a`'s manifest. Covers "Earlier root wins on a name collision".
- [x] 2.2 Run `uv run pytest tests/manifest/test_module_deps.py::test_build_module_index_multi_root_first_match_wins -v`; confirm PASS against existing `if entry.name in index: continue` skip (line 112-113). Escalate to minimal fix only if it fails.
- [x] 2.3 Add `test_build_module_index_skips_nonexistent_root` in `tests/manifest/test_module_deps.py`: pass `[nonexistent_path, valid_root_with_one_module]` to `build_module_index`, assert it completes without raising and the index contains only the valid root's module. Covers "A non-existent or non-directory root is skipped, not an error".
- [x] 2.4 Run `uv run pytest tests/manifest/test_module_deps.py::test_build_module_index_skips_nonexistent_root -v`; confirm PASS against existing `is_dir()` check (line 88-89). Escalate to minimal fix only if it fails.

## Phase 3: Uninstallable-Self-Depends Characterization Test

- [x] 3.1 Add `test_find_missing_dependencies_uninstallable_module_own_depends_not_evaluated` in `tests/manifest/test_module_deps.py`: build an index with module `z` (`installable: False`, `depends: ['nonexistent']`), call `find_missing_dependencies(index)`, assert `z` is absent from the result. Covers "An uninstallable module's own depends is never evaluated".
- [x] 3.2 Run `uv run pytest tests/manifest/test_module_deps.py::test_find_missing_dependencies_uninstallable_module_own_depends_not_evaluated -v`; confirm PASS against existing `if not module.installable: continue` skip (line 140-141). Escalate to minimal fix only if it fails.

## Phase 4: Full-Suite Verification

- [x] 4.1 Run `uv run pytest tests/manifest/test_module_deps.py -v`; confirm all 6 new tests plus the existing suite pass green.
- [x] 4.2 Run `uv run pytest` (full suite) to confirm no regression elsewhere.
- [x] 4.3 `git diff --stat` to confirm only `tests/manifest/test_module_deps.py` (and, contingently, `src/odoo_forge/manifest/module_deps.py`) changed — `docs/specs/platform/portfolio.json` MUST be untouched.
- [x] 4.4 Update this change's success-criteria checklist in `proposal.md` (mark the four boxes done) once 4.1-4.3 pass.
