# Design: Database Adapter Verification Closure

## Technical Approach

After parent PR4 is integrated and this branch is rebased, close both verification gaps at their existing seams. Make `_raise_after_rollback` raise the existing `RollbackIncompleteError` when resource residuals **or** opaque cleanup residuals remain. Extend the pure readiness evidence model only enough to distinguish runtime-proven, missing, and simulated real-Docker/ownership evidence; do not add routing, portfolio, or control-plane behavior.

## Architecture Decisions

| Option | Tradeoff | Decision |
|---|---|---|
| Reuse `RollbackIncompleteError` and its receipt/resource/cleanup fields | Changes the typed outcome for credential-cleanup-only residuals, but preserves reconciliation and caller handling | Chosen; raise when `residuals or cleanup_failures`, chaining from the original redacted failure |
| Add a credential-specific error or provider-neutral report field | More explicit but expands contracts and can lose rollback context | Rejected |
| Add nullable runtime-proof flags to `GateReadinessEvidence` | Small internal model change; represents `None` (missing), `False` (simulated), and `True` (runtime-proven) without governance state | Chosen: `real_docker_verified` and `ownership_safety_verified`; only literal `True` satisfies readiness |
| Infer runtime proof from a non-null verification receipt | No model change, but simulated evidence would incorrectly pass | Rejected |

## Data Flow

    provision failure
      -> credential target exit/unlink retry
      -> cleanup_failures = ("credential-file",)
      -> receipt-owned container rollback
      -> RollbackIncompleteError(receipt, resource residuals, cleanup failures)
           from original redacted failure

    GateReadinessEvidence
      -> identifiers present AND both runtime-proof flags are True
      -> GateReadiness(is_ready, missing_identifiers)

## File Changes

| File | Action | Description |
|---|---|---|
| `src/odoo_forge_postgres_docker/provider.py` | Modify | Raise rollback-incomplete for either residual category; keep receipt, cause, and separate tuples unchanged. |
| `tests/adapters/test_postgres_docker_provider.py` | Modify | Turn the persistent-unlink oracle RED, then assert rollback, empty resource residuals, `credential-file`, cause, and redaction. |
| `src/odoo_forge/database/readiness.py` | Modify | Add the two nullable proof flags and fail closed unless each is `True`, reporting unsatisfied field names. |
| `tests/database/test_readiness.py` | Modify | Supply true flags for complete evidence and add parameterized missing/simulated negative policy coverage. |

## Interfaces / Contracts

`DatabaseProvider`, `CleanupReport`, and public error families remain unchanged. `RollbackIncompleteError` continues to expose `receipt`, `residual_failures`, and `cleanup_failures`; its message remains the redacted inherited detail. Readiness treats `None` and `False` as unsatisfied evidence and includes the corresponding flag name in `missing_identifiers`.

## Testing Strategy

| Layer | What to Test | Approach |
|---|---|---|
| Unit (RED first) | Persistent unlink failure with successful owned-container rollback | Expect `RollbackIncompleteError`; assert receipt, `residual_failures == ()`, `cleanup_failures == ("credential-file",)`, redacted chained cause, exact rollback, and no path/secret/handle/descriptor. |
| Unit policy (RED first) | Missing and simulated real-Docker/ownership proof | Parameterize each flag as `None` and `False` with all other evidence complete; assert not ready and the exact blocker. |
| Regression | Existing adapter/readiness behavior | Run focused tests, then `uv run pytest`, Ruff, mypy, import-linter, and build. No new real-Docker execution is needed for this pure policy closure. |
| E2E | N/A | No routing or control-plane expansion. |

## Threat Matrix

| Boundary | Applicability | Safe / failure behavior | Planned RED test |
|---|---|---|---|
| Docker subprocess/ownership process boundary | Applicable | Keep argv-only `shell=False`; rollback mutates only receipt-owned, live-label-proven containers; refusal becomes a resource residual | Persistent-unlink regression asserts inspect/remove flow and exact owned container only |
| Credential target lifetime/diagnostics | Applicable | Retry unlink; any residual fails closed as opaque `credential-file`; never expose path, secret, handle, or descriptor | Persistent-unlink regression asserts typed residual, cause, and negative observability |
| Documentation-like paths | N/A: no classification/execution change | — | — |
| Git repository selection | N/A: no Git automation | — | — |
| Commit state | N/A: no commit automation | — | — |
| Push state | N/A: no push automation | — | — |
| PR commands | N/A: no PR automation | — | — |

## Migration / Rollout

No data migration or feature flag. Parent PR4 integration is a hard prerequisite; rebase before implementation and revert this follow-up as one bounded unit if needed.

## Open Questions

None.
