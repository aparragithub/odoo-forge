# Tasks: Managed Data Environments

## Review Workload Forecast

| Field | Value |
|---|---|
| Estimated changed lines | 450–650 authored |
| 400-line budget risk | High |
| Chained PRs recommended | Yes |
| Suggested split | PR 1 → PR 2 → PR 3 |
| Delivery strategy | force-chained |
| Chain strategy | feature-branch-chain |

Decision needed before apply: No — chain topology resolved; prerequisite gates remain blocked
Chained PRs recommended: Yes
Chain strategy: feature-branch-chain
400-line budget risk: High

### Suggested Work Units

| Unit | Goal | Likely PR | Focused test command | Runtime harness | Rollback boundary |
|---|---|---:|---|---|---|
| 1 | Record the resolved `DPROV-DB` choice and verify prerequisite evidence before any implementation | Gate PR | N/A — planning/evidence gate only | N/A — blocked until upstream handoffs are accepted | Gate notes only; no code files |
| 2 | Deliver pure core models + fail-closed service transitions | PR 1 | `uv run pytest tests/data_environments/test_models.py tests/data_environments/test_service.py -q` | N/A — pure-core slice | `src/odoo_forge/data_environments/models.py`, `src/odoo_forge/data_environments/service.py` |
| 3 | Add ports, orchestrator replay, control-plane adapter, and recovery wiring | PR 2 → PR 3 | `uv run pytest tests/data_environments/test_orchestrator.py tests/data_environments/test_adapter.py -q` | N/A — depends on accepted control-plane authority and selected adapter | `src/odoo_forge/ports/data_environment_dependencies.py`, orchestrator/adapter wiring, outbox and reconciliation paths |

## Phase 1: Blockers and Handoffs

- [x] 1.1 Record Docker PostgreSQL as the exactly one first database adapter selected by `DPROV-DB`, reusing the existing tested local backend to minimize initial delivery risk.
- [ ] 1.2 Capture accepted evidence for `CHG-FIRST-DATABASE-ADAPTER`, `WF-DATA-COPY`, and `SP-CONTROL-PLANE-AUTHORITY`; do not begin implementation before all three are accepted.
- [x] 1.3 Record `feature-branch-chain` as the selected chain topology before `sdd-apply` starts.

## Phase 2: Core Domain Slice

- [ ] 2.1 Create `src/odoo_forge/data_environments/models.py` with immutable request, pair, lineage, evidence, outcome, and state models.
- [ ] 2.2 Create `src/odoo_forge/data_environments/service.py` for coherent identity, anonymization exception gating, idempotent transitions, and publication eligibility.
- [ ] 2.3 Add RED/GREEN tests in `tests/data_environments/test_models.py` and `tests/data_environments/test_service.py` for usable-only-when-complete, mismatch rejection, exception evidence, and retry idempotency.

## Phase 3: Ports and Orchestration

- [ ] 3.1 Add `src/odoo_forge/ports/data_environment_dependencies.py` as opaque facades only.
- [ ] 3.2 Implement replay/invoke/persist/reconcile flow in the application orchestrator through provider-neutral contracts, with Docker PostgreSQL supplied by the accepted first-adapter handoff.
- [ ] 3.3 Add `tests/data_environments/test_orchestrator.py` for conflicting digest rejection, hidden-before-commit, and deterministic replay.

## Phase 4: Adapter, Recovery, and Cleanup

- [ ] 4.1 Implement the control-plane adapter atomic commit for outcome, references, lineage, evidence, visibility, cleanup obligations, and outbox records.
- [ ] 4.2 Add `tests/data_environments/test_adapter.py` for partial-commit rollback, duplicate outbox delivery, and residual cleanup.
- [ ] 4.3 Update docs/comments only if needed to restate blocked prerequisites and rollback boundaries.
