# Tasks for CAP-RESOURCE-OWNERSHIP

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | 480-650 additions + deletions |
| 400-line budget risk | High |
| Chained PRs recommended | Yes |
| Suggested split | PR 1 -> PR 2 -> PR 3 |
| Delivery strategy | auto-chain |
| Chain strategy | feature-branch-chain |

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: feature-branch-chain
400-line budget risk: High

### Suggested Work Units

| Unit | Goal | Likely PR | Focused test command | Runtime harness | Rollback boundary |
|------|------|-----------|----------------------|-----------------|-------------------|
| 1 | Relocate ownership value types to `resource_ownership/` + shim `database/types.py` | PR 1 (base: feature/tracker) | `uv run pytest tests/resource_ownership/test_types.py tests/database/` | N/A — pure value types, no runtime process | Delete `src/odoo_forge/resource_ownership/`, `tests/resource_ownership/test_types.py`; revert `database/types.py` |
| 2 | Add `PORT-RESOURCE-OWNERSHIP` read/attest contract | PR 2 (base: PR 1 branch) | `uv run pytest tests/ports/test_resource_ownership.py` | N/A — Protocol + fake-adapter test only | Delete `src/odoo_forge/ports/resource_ownership.py`, `tests/ports/test_resource_ownership.py` |
| 3 | Portfolio/docs alignment + readiness gate | PR 3 (base: PR 2 branch) | N/A (doc-only diff review) | N/A — documentary change | Revert `docs/specs/platform/portfolio.json`, `docs/13-src-ports-map.md`, `docs/03-src-core-map.md` |

## 1. Slice 1 — Canonical `resource_ownership/` package and re-export shim

- [x] RED: Add failing tests in `tests/resource_ownership/test_types.py` for the three-state `ResourceOwnership` enum (`created`/`adopted`/`external`, no others), frozen/opaque `ResourceRef` (identifier + resource_kind + ownership), `OwnershipReceipt` (operation proof + owned_resource_ids + live_proof_expected), `OwnershipRecord` (ref + optional `TenantAttribution` + optional receipt), and `OwnershipAttestation`.
- [x] GREEN: Implement `src/odoo_forge/resource_ownership/types.py` with `ResourceOwnership`, `ResourceRef`, `OwnershipReceipt`, `OwnershipRecord`, `OwnershipAttestation`, `TenantAttribution`, plus relocated `OperationIdentity`/`CreationReceipt`; add `src/odoo_forge/resource_ownership/__init__.py` exporting all of them.
- [x] GREEN: Reduce `src/odoo_forge/database/types.py` to re-export `ResourceOwnership`, `OperationIdentity`, `CreationReceipt` from `odoo_forge.resource_ownership.types`; keep `DatabaseSpec`, `DatabaseRef`, `DatabaseCreation`, `CleanupReport` defined locally with unchanged `__all__`.
- [x] TRIANGULATE: Run `uv run pytest tests/resource_ownership/test_types.py`, then the full suite `uv run pytest` to prove all 28+ existing `database.types` callers and the Docker adapter tests stay green through the shim.
- [x] REFACTOR: Tighten naming/typing in `resource_ownership/types.py` only; no behavioral drift; confirm `database/types.py` has zero new symbols beyond the re-export.
- [x] Rollback boundary: delete `src/odoo_forge/resource_ownership/` and `tests/resource_ownership/test_types.py`; revert `database/types.py` to its pre-shim definitions.

## 2. Slice 2 — `PORT-RESOURCE-OWNERSHIP` read/attest contract

- [x] RED: Add failing contract tests in `tests/ports/test_resource_ownership.py` asserting `describe_ownership` is side-effect-free and returns state + optional tenant attribution, `attest_ownership` rejects non-owned/missing-live-proof receipts, and neither method exposes a transition verb (`reserve`/`bind`/`activate`/`retire`/`adopt`).
- [x] GREEN: Implement `src/odoo_forge/ports/resource_ownership.py` defining `ResourceOwnershipPort` as a `Protocol` with exactly `describe_ownership(resource: ResourceRef) -> OwnershipRecord` and `attest_ownership(receipt: OwnershipReceipt) -> OwnershipAttestation`.
- [x] TRIANGULATE: Run `uv run pytest tests/ports/test_resource_ownership.py`, then `uv run pytest`, `uv run lint-imports`, `uv run mypy`, `uv run ruff check` to confirm no architecture or typing boundary breaks.
- [x] REFACTOR: Normalize docstrings/method names only; confirm no transition-verb method exists on the Protocol.
- [x] Rollback boundary: delete `src/odoo_forge/ports/resource_ownership.py` and `tests/ports/test_resource_ownership.py`; slice 1 package stays intact.

## 3. Slice 3 — Readiness evidence and doc alignment

- [x] Populate `AC-CAP-RESOURCE-OWNERSHIP-READY` in `docs/specs/platform/portfolio.json` with evidence for: three-state model, reusable receipt shape, optional tenant attribution, operation-identity reuse from `CAP-DURABLE-OPERATIONS`, read/attest-only port v1, and `SP-CONTROL-PLANE-AUTHORITY`/`SP-RESOURCE-LIFECYCLE`/`WF-ENVIRONMENT-REQUEST`/`WF-DATA-COPY` positioned as consumers.
- [x] Register the new core package in `docs/03-src-core-map.md` and the new port in `docs/13-src-ports-map.md`.
- [x] Verify: targeted search confirms no doc redefines ownership states, receipt shape, or tenant-attribution composition outside `CAP-RESOURCE-OWNERSHIP`.
- [x] Rollback boundary: revert `docs/specs/platform/portfolio.json`, `docs/13-src-ports-map.md`, `docs/03-src-core-map.md` only; no source code affected.

## 4. Final cross-slice validation

- [x] Confirm `uv run pytest`, `uv run mypy`, `uv run ruff check`, and `uv run lint-imports` all pass on the combined branch.
- [x] Confirm `database.types.__all__` is byte-identical to its pre-change value and every relocated name resolves through the shim.
- [x] Confirm no control-plane service, lifecycle/retention logic, workflow orchestration, or umbrella merge was introduced (non-goals per decision `DG`).

## 5. Remediation — Operation Identity Composition (post sdd-verify FAIL, 1 CRITICAL)

- [x] RED: Add `test_ownership_receipt_reuses_durable_operation_identity` and `test_ownership_receipt_rejects_a_parallel_operation_identity_model` to `tests/resource_ownership/test_types.py`, asserting the two spec scenarios of "Operation Identity Composes With `CAP-DURABLE-OPERATIONS` Without Duplication"; confirm both fail against the pre-fix code (4 failures observed, including the pre-existing tests broken by the updated `_receipt()` helper).
- [x] GREEN: Change `OwnershipReceipt.operation` from the legacy `OperationIdentity{value: str}` to `DurableOperationIdentity{operation_id, request_digest}` (imported from `odoo_forge.durable_operations.types`) in `src/odoo_forge/resource_ownership/types.py`; update the dependent `_receipt()` helper in `tests/ports/test_resource_ownership.py`; confirm 10/10 and 23/23 tests pass.
- [x] REFACTOR: Resolve the resulting mypy error in the deliberate-mismatch test via `cast(Any, ...)` with an explanatory comment; keep legacy `OperationIdentity`/`CreationReceipt` untouched for the database domain's own use through the shim.
- [x] Verify: full suite (`uv run pytest`), `uv run mypy`, `uv run ruff check`, `uv run lint-imports` all green; `resource_ownership -> durable_operations` import confirmed one-directional with no import-linter violation; Docker adapter confirmed zero-diff; `database.types.__all__` confirmed still byte-identical.
- [x] Reviewed `docs/specs/platform/portfolio.json`'s `AC-CAP-RESOURCE-OWNERSHIP-READY` gate claim: `achieved`/`gaps: []` is now accurate given both spec scenarios are implemented and tested; no JSON edit required (existing evidence entries S63-S67 already point at the corrected files).
