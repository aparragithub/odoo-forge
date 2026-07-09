## Verification Report

**Change**: platform-image-registry-provider
**Version**: N/A
**Mode**: Strict TDD

### Review Scope
- Verified the real current mixed-workspace state after cleanup/docs/traceability completion.
- Per explicit workspace instruction, mixed-workspace status was not treated as a blocker by itself.
- Artifacts reviewed: proposal, spec, design, tasks, apply-progress, prior verify report, source SP-1 doc, and matching Engram topics.
- Strict TDD remained authoritative with `uv run pytest` as the required runner.

### Completeness
| Metric | Value |
|--------|-------|
| Tasks total | 12 |
| Tasks complete | 12 |
| Tasks incomplete | 0 |
| Core implementation/testing tasks complete | 10 / 10 (`1.1`-`3.3`) |
| Cleanup/documentation tasks complete | 2 / 2 (`4.1`, `4.2`) |

### Build & Tests Execution
**Tests**: ✅ 57 passed / ❌ 0 failed / ⚠️ 0 skipped
```text
uv run pytest tests/ports/test_image_registry_provider.py tests/adapters/test_registry_provider.py tests/cli/test_image_registry.py tests/adapters/test_docker_provider.py::test_run_pulls_exact_digest_image_ref_before_odoo_start tests/adapters/test_docker_provider.py::test_non_run_paths_do_not_pull_images --cov=odoo_forge --cov=odoo_forge_cli --cov=odoo_forge_registry --cov=odoo_forge_docker --cov-report=term-missing --cov-branch
57 passed in 0.66s
```

**Quality**:
```text
uv run ruff check src/odoo_forge/image_registry/__init__.py src/odoo_forge/image_registry/errors.py src/odoo_forge/image_registry/reference.py src/odoo_forge/image_registry/types.py src/odoo_forge/ports/image_registry_provider.py src/odoo_forge_cli/main.py src/odoo_forge_docker/provider.py src/odoo_forge_registry/provider.py tests/ports/test_image_registry_provider.py tests/adapters/test_registry_provider.py tests/cli/test_image_registry.py tests/adapters/test_docker_provider.py
All checks passed!

uv run mypy src tests
Success: no issues found in 68 source files

uv build
Successfully built dist/odoo_forge-0.1.0.tar.gz
Successfully built dist/odoo_forge-0.1.0-py3-none-any.whl
```

**Coverage**: 55% total on the targeted verification run → ➖ informational only; changed-file detail below is the relevant signal for this slice.

### TDD Compliance
| Check | Result | Details |
|-------|--------|---------|
| TDD Evidence reported | ⚠️ | `apply-progress.md` now contains a whole-change evidence table, but it is area-granular rather than 12 explicit task rows |
| All changed behaviors have test files | ✅ | Port, adapter, CLI, and backend-boundary tests exist and reran |
| RED confirmed (tests exist) | ✅ | Referenced test files exist on disk |
| GREEN confirmed (tests pass) | ✅ | 57 targeted tests passed at runtime |
| Triangulation adequate | ✅ | Publish success/rejection, resolve success/fail-fast, exists present/absent, backend boundary, and `project.lock` invariants are all covered |
| Safety Net for modified files | ✅ | Recorded safety-net reruns align with the current green suite |

**TDD Compliance**: 5 / 6 checks fully green

---

### Test Layer Distribution
| Layer | Tests | Files | Tools |
|-------|-------|-------|-------|
| Unit | 23 | 1 | pytest |
| Integration | 34 | 3 | pytest + monkeypatch + Typer `CliRunner` |
| E2E | 0 | 0 | not installed |
| **Total** | **57** | **4** | |

---

### Changed File Coverage
| File | Line % | Branch % | Uncovered Lines | Rating |
|------|--------|----------|-----------------|--------|
| `src/odoo_forge/image_registry/__init__.py` | 100% | 100% | — | ✅ Excellent |
| `src/odoo_forge/image_registry/errors.py` | 100% | 100% | — | ✅ Excellent |
| `src/odoo_forge/image_registry/types.py` | 100% | 100% | — | ✅ Excellent |
| `src/odoo_forge/ports/image_registry_provider.py` | 100% | 100% | — | ✅ Excellent |
| `src/odoo_forge/image_registry/reference.py` | 85% | partial gaps | `40, 63, 66, 73, 75, 78` | ⚠️ Acceptable |
| `src/odoo_forge_registry/provider.py` | 80% | partial gaps | `52-53, 60-61, 94-95, 99, 129, 142, 149, 155-158` | ⚠️ Acceptable |
| `src/odoo_forge_docker/provider.py` | 68% | partial gaps | non-registry Docker lifecycle paths outside this focused slice remain uncovered | ⚠️ Low |
| `src/odoo_forge_cli/main.py` | 26% | partial gaps | many non-registry CLI paths remain outside this focused rerun | ⚠️ Low |

**Average changed file coverage**: mixed; the registry contract and adapter files are well covered, while shared entrypoints remain low because the verification run intentionally stayed scoped to the registry slice.

---

### Assertion Quality
**Assertion quality**: ✅ All assertions verify real behavior

---

### Quality Metrics
**Linter**: ✅ No errors
**Type Checker**: ✅ No errors
**Build**: ✅ `uv build` passed

### Spec Compliance Matrix
| Requirement | Scenario | Status | Runtime Evidence | Notes |
|-------------|----------|--------|------------------|-------|
| Publish built images as immutable digests | Publish returns a digest | ✅ COMPLIANT | `tests/adapters/test_registry_provider.py::test_publish_pushes_then_returns_canonical_digest_ref`, `tests/cli/test_image_registry.py::test_image_publish_prints_digest_ref` | Publish returns canonical digest refs |
| Publish built images as immutable digests | Publish input is not publishable | ✅ COMPLIANT | `tests/ports/test_image_registry_provider.py::test_normalize_publishable_image_reference_rejects_digest_refs`, `tests/cli/test_image_registry.py::test_image_publish_rejects_digest_refs_before_provider_call` | Digest refs are rejected before provider dispatch |
| Pull digest references as a registry concern only | Pull returns a local handle | ✅ COMPLIANT | `tests/adapters/test_registry_provider.py::test_pull_prefetches_digest_and_returns_local_handle`, `tests/cli/test_image_registry.py::test_image_pull_prints_local_handle` | Returns `LocalImageRef` on success |
| Pull digest references as a registry concern only | Pull does not trigger backend runtime execution | ✅ COMPLIANT | `tests/cli/test_image_registry.py::test_registry_commands_do_not_invoke_backend_provider`, `tests/adapters/test_docker_provider.py::test_non_run_paths_do_not_pull_images` | Registry commands stay outside backend runtime execution |
| Check digest existence without transfer | Existing digest reports present | ✅ COMPLIANT | `tests/adapters/test_registry_provider.py::test_exists_reports_present_digest`, `tests/cli/test_image_registry.py::test_image_exists_reports_present_digest` | Present path covered end-to-end |
| Check digest existence without transfer | Missing digest reports absent | ✅ COMPLIANT | `tests/adapters/test_registry_provider.py::test_exists_reports_absent_digest_without_pulling_layers`, `tests/cli/test_image_registry.py::test_image_exists_prints_boolean` | Missing digest stays no-transfer and returns `false` |
| Resolve GHCR image references to immutable digests | Resolve a mutable tag | ✅ COMPLIANT | `tests/adapters/test_registry_provider.py::test_resolve_digest_returns_canonical_digest_ref`, `tests/cli/test_image_registry.py::test_image_resolve_prints_canonical_digest_ref` | Tag → digest behavior verified |
| Resolve GHCR image references to immutable digests | Reject an unsupported registry reference | ✅ COMPLIANT | `tests/cli/test_image_registry.py::test_image_commands_fail_fast_on_usage_boundary_errors` | Unsupported registry is rejected before adapter work |
| Surface fail-fast diagnostics | Registry authentication fails | ✅ COMPLIANT | `tests/cli/test_image_registry.py::test_image_commands_render_single_cause_registry_errors`, `tests/adapters/test_registry_provider.py::test_resolve_digest_maps_auth_failure_to_typed_error` | Auth failures remain single-cause and distinct |
| Surface fail-fast diagnostics | Image reference is not found | ✅ COMPLIANT | `tests/cli/test_image_registry.py::test_image_commands_render_single_cause_registry_errors`, `tests/adapters/test_registry_provider.py::test_exists_reports_absent_digest_without_pulling_layers` | Not-found/absent diagnostics remain distinct from auth and format errors |
| Preserve SP1-A scope boundaries | Operator uses the platform registry CLI foundation | ✅ COMPLIANT | `tests/cli/test_image_registry.py::test_registry_commands_do_not_invoke_backend_provider` | CLI surface stays in registry scope |
| Preserve SP1-A scope boundaries | Successful registry command completes | ✅ COMPLIANT | `tests/cli/test_image_registry.py::test_successful_registry_commands_leave_project_lock_untouched` | Successful registry commands do not create or modify `project.lock` |

**Compliance summary**: 12 / 12 scenarios compliant

### Correctness
| Check | Status | Notes |
|------|--------|-------|
| Port contract exposes `publish/pull/resolve_digest/exists` | ✅ | Matches proposal, spec, and design |
| GHCR adapter implements the required verb set | ✅ | Publish/pull/resolve/exists flows are implemented and rerun |
| Publish rejects non-publishable digest refs | ✅ | Normalizer and CLI boundary tests both passed |
| Legacy `resolve()` / `validate()` bridge is removed | ✅ | Adapter tests explicitly guard against bridge reintroduction |
| Runtime pull ownership remains in `DockerBackendProvider.run()` | ✅ | Docker boundary tests still prove runtime ownership stays in backend |
| CLI registry commands avoid backend orchestration | ✅ | Registry command tests prove no backend provider construction |
| SP-1 platform doc and delta spec match the implemented contract | ✅ | Current wording reflects `publish` / `pull` / `resolve_digest` / `exists` |

### Design Coherence
| Decision | Followed? | Notes |
|----------|-----------|-------|
| Publish ownership stays registry-only and does not call the build script | ✅ Yes | No build orchestration was added inside `publish()` |
| Publish accepts only already-built local image refs | ✅ Yes | Digest refs are rejected by the publish normalizer |
| Pull remains a registry prefetch and backend runtime pull stays in Docker backend | ✅ Yes | Ownership line is preserved |
| Named value types clarify the contract | ✅ Yes | `uv run mypy src tests` is clean |
| CLI renders a single `RegistryError` boundary | ✅ Yes | CLI tests confirm single-cause error output |
| Cleanup removed temporary compatibility glue | ✅ Yes | No legacy bridge remains in the adapter surface |

### Issues Found
**CRITICAL**: None.

**WARNING**:
- Strict-TDD evidence is present, but `apply-progress.md` still summarizes by area instead of giving one explicit RED/GREEN row per task.
- Changed-file coverage remains low in shared entrypoints (`src/odoo_forge_cli/main.py` at 26%, `src/odoo_forge_docker/provider.py` at 68%) because this verification run was intentionally scoped to the registry slice rather than the whole CLI/backend surface.
- The final 2-PR split still needs to isolate this verified slice cleanly from unrelated mixed-workspace changes.

**SUGGESTION**:
- Reuse this report as the verification evidence for both final PRs and keep the split aligned with the planned contract-first / adapter+CLI chain.

### Verdict
PASS WITH WARNINGS
The change satisfies the current spec, design, and task gate with passing runtime evidence; it is effectively ready, with only non-blocking traceability/coverage caveats and the final split into 2 PRs still pending.
