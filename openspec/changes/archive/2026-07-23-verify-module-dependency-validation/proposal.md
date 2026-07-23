# Proposal: Verify & Formalize Module Dependency Validation

## Intent

The `module-dependency-validation` capability is already implemented
(`src/odoo_forge/manifest/module_deps.py`) with an accepted spec and a test
suite. This is a VERIFICATION-FIRST change: confirm the implementation fully
satisfies the accepted spec at the core-module surface, close concrete
test-coverage gaps for behaviors that are implemented but unverified, and
formalize the verified state. No product behavior changes.

Finding after reading spec + code + tests: the four spec requirements owned by
this module (dependency resolution, `ast.literal_eval`-only parsing, guarded
I/O, non-installable exclusion) are all implemented and mostly tested. Several
guarded/edge behaviors are exercised in code but have NO test asserting them.

## Scope

### In Scope
- Characterization tests (no production change expected) for implemented but
  untested behaviors in `module_deps.py`:
  - `OSError` guard on `manifest_path.is_file()` names the offending path
  - `OSError` guard on `read_text()` names the offending path
  - `OSError` guard on root `is_dir()` names the offending root
  - multi-root first-match-wins precedence (earlier root wins)
  - non-existent / non-dir root is skipped, not an error
  - an uninstallable module's own `depends` is never evaluated
- Confirm the full suite passes via `uv run pytest`.

### Out of Scope
- `docs/specs/platform/portfolio.json` — owned by a PARALLEL change; MUST NOT
  be touched, and nothing marked "achieved" here.
- CLI-wiring requirements ("attached to every command", "hard error reporting
  all at once") — those live in `src/odoo_forge_cli/` and their tests, outside
  this change's file surface.
- Any new production behavior, new capability, or spec requirement change.

## Capabilities

### New Capabilities
- None

### Modified Capabilities
- None (spec requirements unchanged; this change verifies conformance only)

## Approach

Under strict TDD, add tests that assert existing behavior. If a test fails, it
reveals a real gap and only then does a minimal fix to `module_deps.py` enter
scope. Expected outcome: tests pass green against current code (pure
characterization), proving conformance.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `tests/manifest/test_module_deps.py` | Modified | Add characterization tests for untested edge cases |
| `src/odoo_forge/manifest/module_deps.py` | Modified (contingent) | Only if a characterization test surfaces a real gap |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| A "verify" test surfaces a real bug, expanding scope | Low | Keep any fix minimal and confined to `module_deps.py`; report as risk |
| Accidental portfolio/CLI edits | Low | Hard file-surface constraint; review diff before commit |

## Rollback Plan

Revert the change folder and the test additions (`git revert` / drop the
commit). Since production code is untouched (or minimally touched), rollback is
low-risk and isolated to `tests/manifest/test_module_deps.py`.

## Dependencies

- None. Parallel-safe with the portfolio-refresh change (disjoint file surface).

## Success Criteria

- [x] Each of the six listed behaviors has an asserting test
- [x] `uv run pytest` passes green
- [x] `module_deps.py` unchanged, OR any change is minimal and gap-justified
- [x] `docs/specs/platform/portfolio.json` untouched
