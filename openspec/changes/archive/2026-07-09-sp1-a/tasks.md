# Tasks: SP1-A — Immutable Image Identity Foundation

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~350–520 |
| 400-line budget risk | High |
| Chained PRs recommended | Yes |
| Suggested split | PR 1: core port + GHCR adapter + unit tests; PR 2: CLI wiring + boundary tests + docs |
| Delivery strategy | ask-on-risk |
| Chain strategy | pending |

Decision needed before apply: Yes
Chained PRs recommended: Yes
Chain strategy: pending
400-line budget risk: High

### Suggested Work Units

| Unit | Goal | Likely PR | Notes |
|------|------|-----------|-------|
| 1 | Add immutable-image port and GHCR-first adapter | PR 1 | Base on feature branch; include adapter/unit tests |
| 2 | Expose resolve/validate CLI flows and operator diagnostics | PR 2 | Base on PR 1; include CLI/integration tests and docs |

## Phase 1: Foundation / Infrastructure

- [x] 1.1 Create `src/odoo_forge/ports/image_registry_provider.py` with resolve/validate port types and registry error contracts.
- [x] 1.2 Create `src/odoo_forge_registry/` adapter package skeleton and import boundary rules in `pyproject.toml`.

## Phase 2: Core Implementation

- [x] 2.1 Implement GHCR-first digest resolve/validate adapter logic in `src/odoo_forge_registry/`.
- [x] 2.2 Map auth, not-found, unsupported-registry, and malformed-reference failures to typed, operator-readable errors.
- [x] 2.3 Keep `pull()`/backend/project.lock behavior out of scope; do not add persistence hooks.

## Phase 3: Integration / Wiring

- [x] 3.1 Wire first CLI commands into `src/odoo_forge_cli/main.py` for digest resolve and validate.
- [x] 3.2 Catch registry errors at the CLI boundary and print single-cause diagnostics for GHCR auth first.
- [x] 3.3 Update `pyproject.toml` packaging/import-linter config for the new adapter package.

## Phase 4: Testing / Verification

- [x] 4.1 Add port-conformance tests under `tests/ports/` for resolve/validate behavior and unsupported-registry rejection.
- [x] 4.2 Add adapter tests under `tests/adapters/` for GHCR auth failure, not-found, and malformed-reference cases.
- [x] 4.3 Add CLI tests under `tests/cli/` for exit codes and operator-readable output on success/failure paths.

## Phase 5: Cleanup / Documentation

- [x] 5.1 Update change docs in `openspec/changes/archive/2026-07-09-sp1-a/design.md` references if task names or boundaries need alignment.
- [x] 5.2 Remove any temporary scaffolding after CLI and adapter tests pass.
