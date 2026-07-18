# Tasks: Workspace Partial Clone

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | 150-220 |
| 400-line budget risk | Low |
| Chained PRs recommended | No |
| Suggested split | Single PR |
| Delivery strategy | auto-chain |
| Chain strategy | pending |

Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: pending
400-line budget risk: Low

### Suggested Work Units

| Unit | Goal | Likely PR | Focused test command | Runtime harness | Rollback boundary |
|------|------|-----------|----------------------|-----------------|-------------------|
| 1 | Partial-clone argv + fallback in `provider.py`, unit + integration coverage | PR 1 | `pytest tests/adapters/test_workspace_provider.py tests/adapters/test_workspace_provider_integration.py -m "not integration or integration"` | Real-git hermetic fixture (`tests/adapters/test_workspace_provider_integration.py`, `pytest -m integration`) | Revert `_clone_and_replace`/`_clone` in `provider.py` to drop `--filter=blob:none` and the fallback branch; delete the new test file |

## Phase 1: Unit Tests — RED (argv assertions)

- [x] 1.1 In `tests/adapters/test_workspace_provider.py`, extend the `_fake_run_factory`-based fixture to capture all `run` argv calls in order.
- [x] 1.2 Add test asserting the first clone argv contains `--filter=blob:none` before `--` and before `<url>`/`<tmp>` positionals (RED — fails against current code).
- [x] 1.3 Add test where the fake `run` returns non-zero only for the `--filter=blob:none` clone argv, and assert a second clone argv is issued without `--filter` (RED — fails, no fallback exists yet).
- [x] 1.4 Run `pytest tests/adapters/test_workspace_provider.py` and confirm both new tests fail for the expected reason (missing flag / missing fallback), not an unrelated error.

## Phase 2: Implementation — GREEN

- [x] 2.1 In `src/odoo_forge_workspace/provider.py`, extract a private `_clone(url, tmp)` helper containing today's `git clone --no-checkout -- <url> <tmp>` argv.
- [x] 2.2 Change `_clone`'s primary attempt to `git clone --filter=blob:none --no-checkout -- <url> <tmp>`.
- [x] 2.3 On a `CheckoutError` from the partial clone, `rmtree(tmp)` and retry once with the full-clone argv (no `--filter`); let a second failure propagate unchanged.
- [x] 2.4 Update `_clone_and_replace` to call `_clone(url, tmp)` in place of the inline clone call; keep `checkout --detach <commit>` and `_atomic_swap` invocations byte-identical.
- [x] 2.5 Run `pytest tests/adapters/test_workspace_provider.py` and confirm all tests (existing + new from Phase 1) pass.

## Phase 3: Integration Tests — RED then GREEN (real git)

- [x] 3.1 Create `tests/adapters/test_workspace_provider_integration.py` with `pytestmark = pytest.mark.integration` and a skip guard for missing `git` or version `< 2.19`.
- [x] 3.2 Add Fixture A: build a bare repo in `tmp_path` with one real commit, run `git config uploadpack.allowFilter true`, clone via `file://` URL through `GitWorkspaceProvider.checkout`; assert the tree at the pinned SHA is correct after `checkout`.
- [x] 3.3 Extend Fixture A to call `promote` (worktree add) and assert the resulting worktree materializes the correct file contents with no network access required.
- [x] 3.4 Add Fixture B: identical bare repo WITHOUT `allowFilter`; assert `checkout` still succeeds via the full-clone fallback and the resulting tree is correct.
- [x] 3.5 Run `pytest -m integration tests/adapters/test_workspace_provider_integration.py` and confirm both fixtures pass against the Phase 2 implementation.

## Phase 4: Regression and Cleanup

- [x] 4.1 Run the full existing `tests/adapters/test_workspace_provider.py` suite (idempotency, dirty/linked-worktree refusal, atomic swap) and confirm zero behavior changes.
- [x] 4.2 Confirm `-- <url> <tmp>` end-of-options guard is present identically on both the partial and fallback clone argv (matches design threat-matrix row).
- [x] 4.3 Re-check `_run`'s stderr-suppression guarantee is untouched — no new logging/propagation of clone output was introduced in `_clone`.
