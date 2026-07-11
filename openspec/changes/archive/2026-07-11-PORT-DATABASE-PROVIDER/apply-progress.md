# Apply Progress: PORT-DATABASE-PROVIDER

## Cumulative Completion

- [x] 1.1–1.4 Foundation / value model
- [x] 2.1–2.4 Contract / failures
- [x] 3.1 Full verification
- [x] 3.2 Evidence preservation
- [x] 3.3 Scope confirmation
- [ ] Phase 4 post-verification evidence acceptance — lifecycle action excluded from apply completion

## TDD Cycle Evidence

| Task | Test file | Layer | Safety net | RED | GREEN | Triangulation | Refactor |
|---|---|---|---|---|---|---|---|
| 1.1 | `tests/database/test_types.py` | Unit | N/A (new files) | Missing database package failed | 4 passed | Immutable handoff, mutation, extra-field, ownership cases | Shared frozen/forbid base |
| 1.2 | `tests/database/test_types.py` | Unit | N/A (new files) | Value API absent | 4 passed | Composition, mutation, extra-field, enum cases | `ResourceOwnership` uses `StrEnum` |
| 1.3 | `tests/database/test_types.py` | Unit | N/A (new files) | Missing credential handle failed | 5 passed | Credential and artifact re-exports | None needed |
| 1.4 | `tests/database/test_types.py` | Unit | N/A (new files) | Database public API absent | 5 passed | Public import plus invariants | Explicit `__all__` |
| 2.1 | `tests/database/test_errors.py` | Unit | 14 focused tests passed | Missing error module failed | 14 passed | Nine typed errors plus secret/artifact diagnostics | Safe public details only |
| 2.2 | `tests/database/test_errors.py` | Unit | 14 focused tests passed | Error API absent | 14 passed | Typed family and redacted diagnostics | Raw diagnostics discarded |
| 2.3 | `tests/ports/test_database_provider.py` | Contract | 14 focused tests passed | Missing port failed | 14 passed | Conforming and missing-method providers | Type-only imports |
| 2.4 | `tests/ports/test_database_provider.py` | Contract | 14 focused tests passed | Protocol absent | 14 passed | Exact signatures, kinds, defaults, annotations, returns | None needed |
| 2.1 corrective retry | `tests/database/test_errors.py` | Unit | 14 focused tests passed | Sensitive residual tests failed | 19 passed | Sensitive strings/bytes rejected; safe IDs accepted | Safe-label validation |
| 2.3 corrective retry | `tests/ports/test_database_provider.py` | Contract | 14 focused tests passed | Runtime Protocol accepted bad signature shape | 19 passed | Explicit signature mismatch for missing `credentials` | Independent fake avoids override suppression |
| Approved remediation | `tests/database/test_types.py`, `tests/database/test_errors.py` | Unit | 24/25 required tests passed before repair; one known regression | `b"database-42"` was coerced and accepted | 25 passed | Reject raw bytes while preserving safe `network-42` and `database-42` IDs | Before-validator inspects raw sequence values before Pydantic coercion |
| 3.1 | Full repository suite | Architecture | N/A — verification-only task | N/A — no production change | `uv run pytest -q && uv run lint-imports && uv run mypy` passed: 336 passed, 1 deselected; 6 import contracts kept; mypy clean for 79 source files | Triangulation skipped: deterministic verification outputs, no behavior branch | None needed |
| 3.2 | OpenSpec evidence artifact | Architecture | N/A — evidence-preservation task | N/A — no production change | Cumulative runtime shape, signatures, immutability, redaction, ownership, and remediation evidence preserved and reconciled to `tasks.md` | Triangulation skipped: artifact reconciliation has no behavior branch | None needed |
| 3.3 | Source and artifact scope | Architecture | N/A — scope-only task | N/A — no production change | Confirmed no adapter, CLI, Docker, runtime cutover, or portfolio gate changes were added | Triangulation skipped: inspection-only scope check | None needed |

## Remediation Details

`CleanupReport.residual_failures` validates raw inputs before coercion. It accepts only safe opaque string identifiers, rejects byte values even when their decoded value would be valid, and rejects unsafe, sensitive, or freeform text. The Work Unit 1 frozen-value test now uses the valid opaque identifier `network-42`.

The protocol test retains the incompatible-signature fake and explicit `inspect.signature` mismatch evidence; runtime `Protocol` conformance alone remains insufficient because it checks attribute presence.

## Work Unit Evidence

| Evidence | Result |
|---|---|
| Focused test command and exact result | `uv run pytest tests/database/test_types.py tests/database/test_errors.py tests/ports/test_database_provider.py -q` → exit 0, 25 passed in 0.29s. |
| Focused Ruff command and exact result | `uv run ruff check tests/database/test_types.py tests/database/test_errors.py tests/ports/test_database_provider.py src/odoo_forge/database/types.py` → exit 0. |
| Focused mypy command and exact result | `uv run mypy tests/database/test_types.py tests/database/test_errors.py tests/ports/test_database_provider.py src/odoo_forge/database/types.py` → exit 0, 4 source files checked. |
| Runtime harness command/scenario and exact result | N/A — pure contract/conformance boundary with no live provider execution. The slice defines no runtime adapter or integration path. |
| Rollback boundary | Revert the raw-input validator in `src/odoo_forge/database/types.py`, the safe residual replacement in `tests/database/test_types.py`, and the raw-byte test in `tests/database/test_errors.py`; no Phase 3 or unrelated behavior is affected. |

## Phase 3 Evidence

### Phase 4 Gate Evidence Status

`AC-PORT-DATABASE-PROVIDER-READY` remains `proposed` with an empty `evidence` list and gap `G3` in `docs/specs/platform/portfolio.json`. The portfolio has no authoritative approved proposal, specification, design, or verification receipt identifiers for this change. No portfolio field was changed and the gate did not advance.

**Required lifecycle step**: obtain and record authoritative approval and verification receipt identifiers through the post-verification evidence-acceptance workflow, then attach those existing IDs. IDs MUST NOT be invented or predeclared.

### Full Verification (3.1)

- `uv run pytest -q` → exit 0, 336 passed, 1 deselected.
- `uv run lint-imports` → exit 0, 6 contracts kept, 0 broken.
- `uv run mypy` → exit 0, no issues in 79 source files.

### Scope Confirmation (3.3)

No temporary helpers remain. The slice contains provider values, typed failures, opaque references, a type-only protocol, and the minimal pure `database.readiness` evaluator plus tests. It excludes Docker, runtime adapters, CLI, artifact/credential materialization, and portfolio gate changes.

### Evidence Preservation (3.2)

This artifact preserves and reconciles the cumulative evidence for Phase 1, Phase 2, remediation, full verification, and scope confirmation with the authoritative completed task numbering in `tasks.md`.

### Phase 3 Work Unit Evidence

| Evidence | Result |
|---|---|
| Focused test command and exact result | `uv run pytest -q && uv run lint-imports && uv run mypy` → exit 0; 336 passed, 1 deselected; 6 import contracts kept; no mypy issues in 79 source files. |
| Runtime harness command/scenario and exact result | N/A — evidence and verification only, with no product runtime path or live provider execution in this slice. |
| Rollback boundary | Revert only the 3.1–3.3 checkboxes plus the Phase 3 entries in this apply-progress artifact; no production or portfolio behavior changed. |

## Post-Verification Approved Remediation

| Blocker | Test file | Layer | Safety net | RED | GREEN | Triangulation | Refactor |
|---|---|---|---|---|---|---|---|
| Sensitive Pydantic diagnostics | `tests/database/test_errors.py` | Unit | 25 focused tests passed | Rejected secret/artifact values appeared in rendered `ValidationError` diagnostics | 34 passed after `hide_input_in_errors=True` | Tests cover extra credential/artifact fields and unsafe cleanup residual content | Shared value-model config keeps diagnostics redacted without changing accepted values |
| Receipt-owned deletion | `tests/ports/test_database_provider.py` | Contract | 25 focused tests passed | No fake exercised receipt ownership authority | 34 passed with a creator-proof fake | Created receipt deletes one owned ID; adopted/external values take refusal paths | One provider-neutral fake centralizes authority behavior |
| Adopted/external refusal and cleanup residuals | `tests/ports/test_database_provider.py` | Contract | 25 focused tests passed | No destructive-refusal or cleanup-residual behavior existed | 34 passed | Both adopted/external ownerships refuse; cleanup returns a safe residual and a typed redacted incomplete-cleanup error is asserted | None needed |
| Readiness evaluation | `tests/database/test_readiness.py` | Unit | N/A (new file) | Missing `odoo_forge.database.readiness` import failed | 34 passed after pure evaluator creation | Complete evidence is ready; incomplete evidence returns exact missing identifiers | Frozen dataclasses keep evaluation deterministic and portfolio-free |

The remediation does not update `docs/specs/platform/portfolio.json`; it evaluates supplied evidence values only. `AC-PORT-DATABASE-PROVIDER-READY` remains proposed, with empty portfolio evidence and gap `G3`.

### Remediation Work Unit Evidence

| Evidence | Result |
|---|---|
| Focused test command and exact result | `uv run pytest tests/database/test_types.py tests/database/test_errors.py tests/ports/test_database_provider.py tests/database/test_readiness.py -q` → exit 0, 34 passed in 0.32s. |
| Focused Ruff command and exact result | `uv run ruff check tests/database/test_errors.py tests/ports/test_database_provider.py tests/database/test_readiness.py src/odoo_forge/database/types.py src/odoo_forge/database/readiness.py` → exit 0. |
| Import boundary command and exact result | `uv run lint-imports` → exit 0, 6 contracts kept, 0 broken. |
| Type checker command and exact result | `uv run mypy` → exit 0, no issues in 81 source files. |
| Runtime harness command/scenario and exact result | N/A — pure contract and evidence-evaluation boundary with no live provider, adapter, or product runtime path. |
| Rollback boundary | Revert `src/odoo_forge/database/readiness.py`, the Pydantic diagnostic configuration in `src/odoo_forge/database/types.py`, the new focused tests, and this remediation evidence section; no portfolio, adapter, CLI, Docker, or archive state changes. |

## Delivery Boundary

- Strategy: auto-chain, stacked-to-main.
- Current slice: PR 3 evidence wiring, approved remediation.
- Scope: verified contract and evidence-evaluation blockers only; Phase 4 evidence acceptance remains deferred. No fabricated portfolio evidence, adapters, CLI, Docker, runtime cutover, or archive changes.
- Review budget: remains below the 400 authored changed-line limit.
