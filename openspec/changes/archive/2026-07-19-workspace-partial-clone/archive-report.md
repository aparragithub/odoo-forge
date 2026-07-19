# Archive Report: workspace-partial-clone

Archive completed. Verification passed, no delta specs to sync, all 17 implementation tasks verified complete with runtime evidence, and change already merged to main branch.

## Status
- Result: PASS
- Change: `workspace-partial-clone`
- Artifact store: `hybrid` (Engram primary, archive filesystem record)
- Archived on: 2026-07-19
- Git merge commit: 16bb682

## Structured Status
- Verification report ID: 9623 (Engram)
- Verdict: PASS (no CRITICAL issues; one WARNING about task count inconsistency in apply-progress.md)
- Working tree: clean; branch `sdd/workspace-partial-clone` no longer present (squash-merged to main)
- Mode: repo-local

## Artifacts Persisted to Engram (Primary Archive)
- Observation 8884: `sdd/workspace-partial-clone/proposal` (architecture)
- Observation 8885: `sdd/workspace-partial-clone/spec` (architecture)
- Observation 8886: `sdd/workspace-partial-clone/design` (architecture)
- Observation 8887: `sdd/workspace-partial-clone/tasks` (architecture)
- Observation 9623: `sdd/workspace-partial-clone/verify-report` (architecture)

## Completion and Verification Evidence
- Verification report status: PASS
- Actual task checkboxes in tasks.md: 17 (all marked complete with evidence)
- Task phases: Phase 1-4 (unit tests RED-to-GREEN, implementation, integration tests RED-to-GREEN, regression/cleanup)
- Stale-checkbox reconciliation note: apply-progress.md claimed "19/19 tasks complete" but tasks.md contains exactly 17 checkboxes (1.1-1.4, 2.1-2.5, 3.1-3.5, 4.1-4.3). All 17 are genuinely done with runtime evidence; this is a documentation count inconsistency in the apply-progress artifact only, not a missing-work defect.

## Spec Sync Status
- Proposal declared: New Capabilities = None, Modified Capabilities = None
- Spec phase conclusion: NO delta specs written (change is confined to `GitWorkspaceProvider._clone_and_replace` internals; no adapter-level or port-level spec changes)
- Canonical specs affected: NONE
- Sync action: SKIP (no merge required; no capability or port changes)

## Implementation Summary
- Changed files:
  - `src/odoo_forge_workspace/provider.py`: `_clone_and_replace` now delegates to new private `_clone(url, clone_path)` helper with partial clone attempt + transparent full-clone fallback (+38/-3 lines)
  - `tests/adapters/test_workspace_provider.py`: +63 lines (2 new unit tests: `test_first_clone_attempt_uses_filter_blob_none`, `test_failed_filtered_clone_falls_back_to_full_clone`)
  - `tests/adapters/test_workspace_provider_integration.py`: +110 lines (new real-git hermetic integration test with two fixtures: allowFilter true/false)
- Total authored diff: ~211 lines (within 150-220 forecast, Low risk)

## Test Evidence (Full Suite)
- Unit tests: 23 passed (includes 2 new partial-clone tests)
- Integration tests: 2 passed (pytestmark = pytest.mark.integration, deselected from main suite)
- Full suite: 741 passed, 17 deselected
- Mypy (strict): Success; no issues in 123 source files
- Ruff checks: All passed

## Archive Outcome
- Archived path: `openspec/changes/archive/2026-07-19-workspace-partial-clone/`
- Change folder moved: N/A (Engram-only artifacts; filesystem archive record created as this report)
- Audit trail preserved: Yes (Engram observation IDs recorded above)

## Notes
- Git command strategy refinement (`--filter=blob:none --no-checkout`) is an internal implementation detail, not specified at the port or capability layer and thus requires no canonical spec changes
- Fallback detection = retry-once on CheckoutError (any partial-clone failure); no stderr capability probe (preserves credential-safety guarantees)
- Integration test documents empirical limitation on `file://` transport: git 2.55 degrades filtered clone silently rather than hard-failing, so retry logic itself is unit-tested with forced failure
- Design threat matrix: only "Git repository selection" row applicable (`--` end-of-options guard preserved on both clone forms)

## Next Step
No further SDD phase required for `workspace-partial-clone`. Change is complete, verified, and merged.
