# Apply Progress: CAP-RESOURCE-OWNERSHIP

**Mode**: Strict TDD
**Branch**: `cap-resource-ownership`

## Status

18/18 tasks complete. 1 CRITICAL remediation applied after `sdd-verify` FAIL. Ready for re-verify.

## Task Completion

All tasks in `tasks.md` are marked `[x]` (Slice 1: relocate + shim, Slice 2: port, Slice 3: docs/portfolio, Final cross-slice validation).

## Remediation — Operation Identity Composition (post sdd-verify FAIL)

**Verdict received**: FAIL, 1 CRITICAL. `OwnershipReceipt.operation` was typed as the legacy `OperationIdentity{value: str}` (the Docker-token type moved unchanged from `database/types.py`) instead of composing with `CAP-DURABLE-OPERATIONS`' real stable identity `DurableOperationIdentity{operation_id, request_digest}` (`src/odoo_forge/durable_operations/types.py:34-42`). This was a parallel operation-identity model, violating the spec requirement "Operation Identity Composes With CAP-DURABLE-OPERATIONS Without Duplication" (both of its scenarios were untested/failing).

### TDD Cycle Evidence (Remediation)

| Step | File | Result |
|------|------|--------|
| RED | `tests/resource_ownership/test_types.py` | Added `test_ownership_receipt_reuses_durable_operation_identity` and `test_ownership_receipt_rejects_a_parallel_operation_identity_model`; updated `_receipt()` helper to build a `DurableOperationIdentity`. Ran `uv run pytest tests/resource_ownership/test_types.py --no-cov -q` → 4 failed / 6 passed (existing tests broke on the new helper as intended, new "reuses" test failed with `ValidationError: Input should be a valid dictionary or instance of OperationIdentity`, new "rejects parallel model" test failed with `DID NOT RAISE ValidationError`). |
| GREEN | `src/odoo_forge/resource_ownership/types.py` | Imported `DurableOperationIdentity` from `odoo_forge.durable_operations.types`; changed `OwnershipReceipt.operation: OperationIdentity` → `OwnershipReceipt.operation: DurableOperationIdentity`. Ran `uv run pytest tests/resource_ownership/test_types.py --no-cov -q` → 10/10 passed. |
| Dependent fixture fix | `tests/ports/test_resource_ownership.py` | `_receipt()` helper also built `OwnershipReceipt` with the legacy `OperationIdentity`; updated to `DurableOperationIdentity`. Ran `uv run pytest tests/ports/test_resource_ownership.py tests/resource_ownership/ --no-cov -q` → 23/23 passed. |
| REFACTOR | `tests/resource_ownership/test_types.py` | mypy flagged the deliberately-wrong-type test (`test_ownership_receipt_rejects_a_parallel_operation_identity_model`) as a static type error — expected, since the test proves *runtime* rejection of a case the type checker already forbids statically. Wrapped the deliberate mismatch in `cast(Any, ...)` with an explanatory comment. Re-ran `uv run mypy` → 0 errors. |

### Verification (full suite re-run after remediation)

```text
$ uv run pytest --no-cov -q
764 passed, 17 deselected in 5.14s

$ uv run mypy
Success: no issues found in 129 source files

$ uv run ruff check
All checks passed!

$ uv run lint-imports
Analyzed 95 files, 268 dependencies.
Core never imports infrastructure or framework KEPT
Core never imports the CLI KEPT
Core never imports the git adapter KEPT
Core never imports the workspace adapter KEPT
Core never imports the docker adapter KEPT
Core never imports the registry adapter KEPT
Contracts: 6 kept, 0 broken.
```

- `resource_ownership` importing from `durable_operations` (both core packages under `odoo_forge`) does not violate any import-linter contract — contracts only forbid core importing infrastructure/CLI/adapters, not core-to-core imports. Direction confirmed one-way (no cycle): `resource_ownership -> durable_operations`.
- Docker adapter (`src/odoo_forge_postgres_docker/`) confirmed zero-diff (`git status --porcelain -- src/odoo_forge_postgres_docker/` empty).
- `database/types.py::__all__` confirmed unaffected by this remediation (unchanged since the original apply — byte-identical to pre-change value).
- Legacy `OperationIdentity{value: str}` and `CreationReceipt` are untouched and still re-exported through `database/types.py` for the database domain's own historical use (`DatabaseCreation.receipt: CreationReceipt`, `CreationReceipt.operation: OperationIdentity`) — only `OwnershipReceipt.operation` was changed to stop using them.

### Portfolio.json — Gate Claim Correction

Reviewed `docs/specs/platform/portfolio.json`'s `CAP-RESOURCE-OWNERSHIP` / `AC-CAP-RESOURCE-OWNERSHIP-READY` entries after the fix. The `achieved` status with `evidence=[S63..S67]` and `gaps=[]` set during the original apply is **now accurate**: the previously-failing "Operation Identity Composes With CAP-DURABLE-OPERATIONS Without Duplication" requirement is genuinely implemented and both its spec scenarios are covered by passing tests (`test_ownership_receipt_reuses_durable_operation_identity`, `test_ownership_receipt_rejects_a_parallel_operation_identity_model`). The existing `evidence_catalog` entries S63-S67 already point at the corrected file paths (`resource_ownership/types.py`, `tests/resource_ownership/test_types.py`, `tests/ports/test_resource_ownership.py`), so **no JSON edit was needed** — the file was left as-is after re-verifying it re-parses as valid JSON and no other item/edge changed.

### Files Changed (this remediation)

| File | Action | What Changed |
|------|--------|---------------|
| `src/odoo_forge/resource_ownership/types.py` | Modified | `OwnershipReceipt.operation` now typed `DurableOperationIdentity` (imported from `odoo_forge.durable_operations.types`) instead of the legacy `OperationIdentity` |
| `tests/resource_ownership/test_types.py` | Modified | Added 2 new tests for the two spec scenarios; updated `_receipt()` helper; added `_durable_identity()` helper; deliberate-mismatch test uses `cast(Any, ...)` |
| `tests/ports/test_resource_ownership.py` | Modified | Updated `_receipt()` helper to build `OwnershipReceipt` with `DurableOperationIdentity` instead of legacy `OperationIdentity` |
| `docs/specs/platform/portfolio.json` | Reviewed, unchanged | Confirmed the existing `achieved`/`gaps: []` claim is now truthful; no edit needed |

### Non-Goals Re-confirmed Intact

- Port stays read/attest-only — no verbs added.
- No new ownership states.
- No control-plane/lifecycle/workflow scope introduced.
- Docker adapter untouched (zero diff).

## Prior History (original apply, before sdd-verify)

See Engram `sdd/CAP-RESOURCE-OWNERSHIP/apply-progress` for the full original 3-slice TDD history (Slice 1 relocate+shim, Slice 2 port, Slice 3 docs/portfolio) — summarized here for continuity:

- Created `src/odoo_forge/resource_ownership/types.py` + `__init__.py`.
- Reduced `src/odoo_forge/database/types.py` to a re-export shim; `__all__` byte-identical.
- Created `src/odoo_forge/ports/resource_ownership.py` (`ResourceOwnershipPort`).
- Created `tests/resource_ownership/test_types.py`, `tests/ports/test_resource_ownership.py`.
- Updated `docs/03-src-core-map.md`, `docs/13-src-ports-map.md`, `docs/specs/platform/portfolio.json`.
