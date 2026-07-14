# Design: Durable Operations Record Integrity Fix

## Technical Approach

Two integrity holes share one root cause: **terminal authority is not bound to durable evidence**.
`DurableOperationRecord.__post_init__` drops the terminal commit when residual cleanup resolves, and
`advance_lifecycle` mints `SUCCEEDED`/`FAILED` with no evidence at all. Both are fixed by moving the
same rule into two guards, in the pure core only — no adapter, no new module, no port signature
change.

The lifecycle enum keeps its meaning; only the *reachability* of terminal states changes:

- **Terminal authority is created exactly once**, by `build_terminal_commit` → `commit_terminal`.
- **`CLOSED` is a resolution state of a residual obligation**, not a generic end state — so it can
  only be reached from a terminal commit that carried residual cleanup, and it **retains** that
  commit (outcome + redacted evidence) forever.

`terminal_commit.residual_cleanup` is the *historical record of obligations recorded at commit time*
(audit evidence, immutable). `lifecycle` is the *authority on whether those obligations are still
open* (`CLEANUP_REQUIRED`) or resolved (`CLOSED`). Separating those two roles is the whole fix.

## Architecture Decisions

| # | Decision | Rejected alternative | Rationale |
|---|---|---|---|
| 1 | Residual branch admits `{CLEANUP_REQUIRED, CLOSED}`; empty-residual branch unchanged (`lifecycle == outcome`) | `CLOSED` as a universal escape hatch bypassing all matching (exploration Option B) | Option B permits incoherent `CLOSED` + arbitrary outcome/residual combinations — it hides the defect instead of fixing it. Keeping the empty-residual branch strict means `CLOSED` is *only* reachable through a residual path, so a `CLOSED` record always carries the commit that explains why it exists. |
| 2 | `resolve_residual` on a record with no open residual obligation is an **error** (`InvalidLifecycleTransitionError`), not a no-op | Silent no-op returning the record unchanged | A no-op would report "closed" while nothing closed — a lying success, the same class of defect we are fixing. It also cannot construct a valid record (Decision 1 rejects `CLOSED` + empty residual), so the alternative failure mode is a raw `ValueError` from a dataclass, not a typed contract failure. Reuse the existing error; do **not** add a new class (`errors.py` already carries one unraised class). |
| 3 | `advance_lifecycle` rejects any transition **into** a terminal outcome from a non-terminal state (option (a): terminal states reachable only via terminal commit) | (b) Add an `evidence` parameter to `advance_lifecycle` | Spec: *"the system MUST NOT expose success or failure as authoritative by itself."* Option (b) duplicates the evidence rule already owned by `build_terminal_commit`, gives two places to keep in sync, and **still does not fix the hole** — a caller could pass synthetic evidence without ever producing a bundle or passing the CAS. Option (a) makes the bundle the single door to terminal authority. |
| 3b | Carve-out: idempotent re-advance `SUCCEEDED→SUCCEEDED` / `FAILED→FAILED` stays legal | Blanket rejection of every terminal target | Authority is *created* only when a non-terminal record becomes terminal. Re-asserting a state that already has a committed bundle creates no new authority, and preserving it keeps the monotonic "same or later" rule uniform across all states. Without the carve-out, `test_lifecycle_keeps_terminal_outcomes_re_advanceable_towards_cleanup_and_closure` breaks for no integrity gain. |
| 4 | Correct the archived design drift with an **append-only correction note**; leave the original line byte-intact | Rewrite `archive/2026-07-12-CAP-DURABLE-OPERATIONS/design.md:110` in place | `skills/_shared/openspec-convention.md:120`: *"The archive is an AUDIT TRAIL — never delete or modify archived changes."* Rewriting the line would make the archive claim it always said three actions — falsifying the record of the very drift that misled the Judgment Day reviewer. An adjacent, labelled note removes the trap **and** preserves the evidence. |
| 5 | Reference fake gains one instance slot, nothing more | Full in-memory adapter keyed by `operation_id` | The Protocol test only needs `commit_terminal` → `resolve_residual` continuity. Anything more is a second implementation to maintain and risks the `runtime_checkable` structural-typing test. |

## Interfaces / Contracts

### 1. `src/odoo_forge/ports/durable_operation_store.py` — exact predicate

```python
_RESIDUAL_LIFECYCLES = frozenset({LifecycleState.CLEANUP_REQUIRED, LifecycleState.CLOSED})

def __post_init__(self) -> None:
    """Keep terminal lifecycle visibility aligned with authoritative cleanup facts."""
    if self.terminal_commit is None:
        return

    if self.terminal_commit.residual_cleanup:
        if self.lifecycle not in _RESIDUAL_LIFECYCLES:
            raise ValueError(
                "terminal commits with residual cleanup must surface cleanup_required lifecycle "
                "until the obligation is resolved as closed"
            )
        return

    if self.lifecycle is not self.terminal_commit.outcome:
        raise ValueError(
            "terminal commits without residual cleanup must expose "
            "their terminal outcome lifecycle"
        )
```

Message note: the first message deliberately still contains the substring `cleanup_required lifecycle`
so the existing regression test (`test_record_rejects_terminal_outcome_lifecycle_when_residual_cleanup_exists`,
`match="cleanup_required lifecycle"`) stays green **unchanged**. The second message is untouched and is
what now rejects `CLOSED` + empty residual.

Truth table:

| `terminal_commit` | `residual_cleanup` | lifecycle | Result |
|---|---|---|---|
| `None` | — | any | accept (unconstrained) |
| set | non-empty | `CLEANUP_REQUIRED` | accept — obligation open |
| set | non-empty | `CLOSED` | **accept (NEW)** — obligation resolved, outcome + evidence retained |
| set | non-empty | anything else (incl. `SUCCEEDED`) | reject |
| set | empty | `== outcome` | accept |
| set | empty | anything else (incl. `CLOSED`) | reject |

### 2. `resolve_residual` docstring (port contract)

```python
def resolve_residual(
    self, operation_id: str, expected_revision: OperationRevision
) -> DurableOperationRecord:
    """Close a recorded cleanup obligation only when its revision still matches.

    Closing resolves the obligation; it MUST NOT erase the authoritative terminal
    commit. The returned record has ``lifecycle=CLOSED`` and RETAINS its
    ``terminal_commit`` — outcome, redacted evidence, and the residual entries that
    were recorded, so the operation stays auditable after cleanup.

    Raise ``InvalidLifecycleTransitionError`` when the record carries no open residual
    obligation; closing is not a no-op and MUST NOT report a resolution that never happened.
    Raise ``RevisionConflictError`` when ``expected_revision`` no longer matches the
    durable record.
    """
```

### 3. `src/odoo_forge/durable_operations/service.py` — `advance_lifecycle` gate

Insert a **third** guard, after the existing two (order is load-bearing — the flip guard must keep
owning `SUCCEEDED→FAILED` so its message and its test survive):

```python
    if target in _TERMINAL_OUTCOMES and current not in _TERMINAL_OUTCOMES:
        raise InvalidLifecycleTransitionError(
            f"cannot reach terminal outcome {target} without an authoritative terminal commit"
        )
    return target, _next_revision(revision)
```

Terminal-target matrix after the change:

| current | target | Result |
|---|---|---|
| `ACCEPTED` / `IN_PROGRESS` / `RECONCILIATION_REQUIRED` / `TERMINAL_PENDING` | `SUCCEEDED` / `FAILED` | **reject (NEW)** — no evidence, no bundle |
| `SUCCEEDED` | `FAILED` (and inverse) | reject (existing flip guard, message unchanged) |
| `SUCCEEDED` | `SUCCEEDED` | accept (carve-out, Decision 3b) |
| `SUCCEEDED` / `FAILED` | `CLEANUP_REQUIRED` / `CLOSED` | accept (unchanged) |

**Existing-test impact — verified, not assumed.** Every `advance_lifecycle` call site in
`tests/durable_operations/test_service.py` was enumerated:

| Test | Calls | Verdict |
|---|---|---|
| `test_lifecycle_progression_is_forward_only_and_increments_revision` (:46) | `ACCEPTED→IN_PROGRESS`, regression | unaffected |
| `test_lifecycle_allows_same_or_later_states_but_never_reuses_the_revision` (:59) | `IN_PROGRESS→IN_PROGRESS` | unaffected |
| `test_lifecycle_rejects_flipping_a_published_terminal_outcome` (:70) | `SUCCEEDED→FAILED`, `FAILED→SUCCEEDED` | unaffected — guard 2 fires first |
| `test_lifecycle_keeps_terminal_outcomes_re_advanceable_towards_cleanup_and_closure` (:86) | `SUCCEEDED→SUCCEEDED`, `FAILED→CLEANUP_REQUIRED` | unaffected **only because of Decision 3b** |

**Zero existing tests break.** Drop the 3b carve-out and `:86` breaks. No other test file calls
`advance_lifecycle`.

### 4. Reference fake — minimal statefulness

`_ConformingDurableOperationStore` in `tests/ports/test_durable_operation_store.py`:

- **State added**: exactly one slot, `self._record: DurableOperationRecord | None = None`.
- **Writes it**: `commit_terminal` only (stores the record it returns).
- **Reads it**: `resolve_residual` only.
- **Untouched, still stateless literals**: `create_or_load`, `save_checkpoint`,
  `mark_reconciliation_required`, `list_recoverable`, `_guard_revision`.

`resolve_residual` becomes:

```python
    def resolve_residual(
        self, operation_id: str, expected_revision: OperationRevision
    ) -> DurableOperationRecord:
        self._guard_revision(operation_id, expected_revision)
        committed = self._record
        if committed is None or committed.terminal_commit is None:
            raise InvalidLifecycleTransitionError(
                f"operation '{operation_id}' has no authoritative terminal commit to close"
            )
        if not committed.terminal_commit.residual_cleanup:
            raise InvalidLifecycleTransitionError(
                f"operation '{operation_id}' has no open residual cleanup obligation"
            )
        return DurableOperationRecord(
            identity=committed.identity,
            revision=OperationRevision(value=expected_revision.value + 1),
            lifecycle=LifecycleState.CLOSED,
            checkpoint=committed.checkpoint,
            terminal_commit=committed.terminal_commit,   # <- retained: the whole point
        )
```

Protocol safety: `runtime_checkable` structural typing checks *method presence* only, and
`test_store_contract_exposes_...` inspects `DurableOperationStore` (the Protocol class), never the
fake. Adding one `__init__` attribute cannot affect either. `test_record_keeps_checkpoint_and_terminal_visibility_distinct`
constructs fresh store instances per assertion, so per-instance state does not leak between tests.

### 5. Archived-design correction (append-only)

`openspec/changes/archive/2026-07-12-CAP-DURABLE-OPERATIONS/design.md` — **do not edit line 110**.
Insert immediately after the Interfaces/Contracts table (after line 111, before `Provider alignment:`):

```markdown
> **Correction — CAP-DURABLE-OPERATIONS-RECORD-FIX (2026-07-12)**: the `RecoveryPlan` row above
> lists four actions. That is drift. `RecoveryAction` shipped with exactly three — `resume`,
> `reconcile`, `surface_residual` — matching `openspec/specs/durable-operations/spec.md`.
> `compensate` was never a recovery action: compensation is a workflow-invoked primitive
> (`ensure_compensation_target` / `CompensationScope`) applied after `surface_residual`, and
> `plan_recovery` has no ownership input with which to decide it. The original line is left intact
> because the archive is an append-only audit trail.
```

## Data Flow

```text
build_terminal_commit(outcome, evidence≠∅, residual)   <- the ONLY door to terminal authority
        │  IncompleteTerminalCommitError if evidence is empty
        ▼
   TerminalCommitBundle ──► store.commit_terminal(op_id, bundle)   [CAS on expected_revision]
        │
        ├─ residual == ()  ─────────────────► record(lifecycle = outcome, terminal_commit=bundle)
        │                                       └─ terminal; CLOSED unreachable. END.
        │
        └─ residual != ()  ─────────────────► record(CLEANUP_REQUIRED, terminal_commit=bundle)
                                                │
                                  store.resolve_residual(op_id, rev)   [CAS]
                                                │
                                                ▼
                                    record(CLOSED, terminal_commit=bundle)
                                              ^^^^^^^^^^^^^^^^^^^^^^^^^^ RETAINED

advance_lifecycle(current, rev, target)
        └─ target ∈ {SUCCEEDED, FAILED} and current ∉ {SUCCEEDED, FAILED}
                └─► InvalidLifecycleTransitionError   (no evidence-free terminal authority)
```

## File Changes

| File | Action | Description |
|---|---|---|
| `src/odoo_forge/ports/durable_operation_store.py` | Modify | `_RESIDUAL_LIFECYCLES` frozenset; `__post_init__` residual branch; `resolve_residual` docstring |
| `src/odoo_forge/durable_operations/service.py` | Modify | Third guard in `advance_lifecycle` |
| `tests/ports/test_durable_operation_store.py` | Modify | One state slot in the fake; stateful `commit_terminal`/`resolve_residual`; new regression tests |
| `tests/durable_operations/test_service.py` | Modify | New RED tests for the evidence gate |
| `openspec/changes/CAP-DURABLE-OPERATIONS-RECORD-FIX/specs/durable-operations/spec.md` | Create | Delta spec (owned by `sdd-spec`, not this design) |
| `openspec/changes/archive/2026-07-12-CAP-DURABLE-OPERATIONS/design.md` | Modify (append-only) | Correction note after the Interfaces table |

No new files in `src/`. No port signature changes. No `__init__.py` export changes — every symbol the
fix needs (`InvalidLifecycleTransitionError`, `LifecycleState`) is already exported.

## Testing Strategy (Strict TDD — RED first)

| Layer | RED test | Proves |
|---|---|---|
| Unit — record | `test_record_retains_terminal_commit_when_residual_cleanup_is_closed` | `CLOSED` + non-empty residual is constructible and keeps `outcome` + `evidence` |
| Unit — record | `test_record_rejects_closed_lifecycle_without_residual_cleanup` (`match="terminal outcome lifecycle"`) | `CLOSED` is unreachable on a clean terminal record |
| Unit — record | existing `test_record_rejects_terminal_outcome_lifecycle_when_residual_cleanup_exists` | regression guard, kept **verbatim** |
| Contract — fake | `test_resolving_residual_cleanup_preserves_the_authoritative_terminal_outcome` | `commit_terminal(residual) → resolve_residual` returns `CLOSED` **with** the same bundle — behavioral, not `inspect.signature` |
| Contract — fake | `test_resolving_residual_without_an_open_obligation_is_rejected` | Decision 2: error, not silent no-op |
| Unit — service | `test_lifecycle_rejects_evidence_free_terminal_outcomes` (parametrized `ACCEPTED`/`IN_PROGRESS`/`RECONCILIATION_REQUIRED`/`TERMINAL_PENDING` × `SUCCEEDED`/`FAILED`) | Terminal authority requires a terminal commit |
| Unit — service | existing `:70` and `:86` | Flip guard + idempotent carve-out survive |
| Architecture | `uv run lint-imports`, `uv run mypy` (strict) | Core stays adapter-free and provider-neutral; no boundary moves |

Quality gates: `uv run pytest`, `uv run lint-imports`, `uv run ruff check .`,
`uv run ruff format --check .`, `uv run mypy`.

## Threat Matrix

N/A — no routing, shell, subprocess, VCS/PR automation, executable-file classification, or
process-integration boundary. This change is pure-core invariants and test doubles.

## Migration / Rollout

No migration. Zero adapters implement `DurableOperationStore`/`DurableOperationRecovery`
(exploration, "Blast radius"), so the breaking-contract tightening has a nil present blast radius —
landing it before adoption is the entire point. Single PR; no feature flag. Rollback = revert the
branch.

## Changed-Line Forecast

| File | +/- (approx.) |
|---|---|
| `ports/durable_operation_store.py` | ~18 |
| `durable_operations/service.py` | ~6 |
| `tests/ports/test_durable_operation_store.py` | ~60 |
| `tests/durable_operations/test_service.py` | ~25 |
| `openspec/changes/.../specs/durable-operations/spec.md` (sdd-spec) | ~35 |
| archived `design.md` correction note | ~8 |
| **Total** | **~150** |

`400-line budget risk: Low` — single PR, no chaining needed.

## Open Questions

- None blocking. `TERMINAL_PENDING` remains a dead lifecycle target and `UnknownOperationOutcomeError`
  remains unraised — both explicitly deferred by the proposal, and neither is touched here. Note that
  Decision 3 makes `TERMINAL_PENDING → SUCCEEDED` an *error*, which further narrows what a future
  `TERMINAL_PENDING` wire-up may mean: it can only be a pre-commit staging marker, never a self-promoting
  state. That constraint is a design output, not an open question.
