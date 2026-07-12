# Verification Report: CAP-DURABLE-OPERATIONS-RECORD-FIX

**Mode**: Full artifacts (proposal, design, delta spec, tasks, apply-progress all present)
**Verdict**: **PASS**

## Completeness

- Tasks: 6/6 slices, all checkboxes `[x]` in `tasks.md`. Cross-checked against actual diff —
  every claimed edit exists in the working tree and matches design.md's exact interfaces.
- Files changed matches design's "File Changes" table exactly (verified via `git status
  --porcelain` + `git diff --stat`): `ports/durable_operation_store.py`,
  `durable_operations/service.py`, `tests/ports/test_durable_operation_store.py`,
  `tests/durable_operations/test_service.py`, archived `design.md` (append-only),
  `tasks.md` (checkboxes).

## Requirement -> Test Traceability

| Requirement | Scenario | Covering test | Result |
|---|---|---|---|
| Residual Cleanup Visibility | Cleanup failure becomes residual work | `test_terminal_commit_with_residual_cleanup_surfaces_cleanup_required_lifecycle` (pre-existing, unaffected) | PASS |
| Residual Cleanup Visibility | Cleanup obligation stays visible while unresolved | `test_record_accepts_cleanup_required_lifecycle_for_residual_terminal_commit` (pre-existing, unaffected) | PASS |
| Residual Cleanup Visibility | **Resolved cleanup retains the terminal outcome and evidence** (the CRITICAL fix) | `test_record_retains_terminal_commit_when_residual_cleanup_is_closed` + `test_resolving_residual_cleanup_preserves_the_authoritative_terminal_outcome` | PASS (behavioral, proven to fail pre-fix — see below) |
| Residual Cleanup Visibility | A closed record with no terminal work is still valid | No dedicated test; structurally guaranteed by the unconditional `if self.terminal_commit is None: return` early exit in `__post_init__`, unchanged by this fix and unconditional on `lifecycle` | GAP (WARNING, see below) |
| Residual Cleanup Visibility | Closed records without residual cleanup keep the unchanged invariant | `test_record_rejects_closed_lifecycle_without_residual_cleanup` | PASS |
| Authoritative Terminal Commit | Successful terminal publication | `test_terminal_bundle_rejects_partial_authoritative_publication` (inverse) + `test_store_protocol_requires_atomic_lifecycle_operations` (pre-existing, unaffected) | PASS |
| Authoritative Terminal Commit | Partial terminal publication is prevented | `test_terminal_bundle_rejects_partial_authoritative_publication` (pre-existing, unaffected) | PASS |
| Authoritative Terminal Commit | **Evidence-free terminal transition is rejected** | `test_lifecycle_rejects_evidence_free_terminal_outcomes` (8-way parametrized: 4 non-terminal states x {SUCCEEDED, FAILED}) | PASS (behavioral, proven to fail pre-fix — see below) |
| Workflow-Level Recovery and Reconciliation | Recovery of an interrupted workflow | `test_reconciliation_required_recovery_never_resumes_even_with_checkpoint`, `test_checkpoint_records_resume_safe_progress_for_recovery` (pre-existing, unaffected) | PASS |
| Workflow-Level Recovery and Reconciliation | Provider reconciliation remains a separate concern | `test_recovery_port_records_redacted_workflow_outcomes`, `test_recovery_port_requires_revision_bound_attempts` (pre-existing, unaffected) | PASS |
| Workflow-Level Recovery and Reconciliation | Recovery actions are limited to three | `RecoveryAction(StrEnum)` in `service.py` has exactly `RESUME`, `RECONCILE`, `SURFACE_RESIDUAL` — inspected directly (pre-existing, no `COMPENSATE` member); documented by the append-only archive correction, not a code change | PASS (code was already correct; this slice only fixed drifted documentation) |

**One traceability gap** (WARNING, not CRITICAL): the "closed record with no terminal work" scenario
has no test with `lifecycle=CLOSED, terminal_commit=None`. It is provably true by code inspection
(the early-return guard in `__post_init__` is unconditional on `lifecycle`), and this code path was
NOT touched by this change (pre-existing), so it does not affect the fix's correctness — but the
scenario itself is spec-declared and untested. Recommend adding one assertion test before archive,
or accept as a pre-existing/no-behavior-change gap.

## The CRITICAL Defect — Proven Fixed, Behaviorally

Claim to verify: a `DurableOperationRecord` with `lifecycle=CLOSED` can carry a `terminal_commit`
with its outcome AND its redacted evidence.

- `test_record_retains_terminal_commit_when_residual_cleanup_is_closed`
  (`tests/ports/test_durable_operation_store.py:319`) constructs exactly that record directly and
  asserts `record.terminal_commit.outcome is LifecycleState.SUCCEEDED` and
  `record.terminal_commit.evidence == bundle.evidence`.
- `test_resolving_residual_cleanup_preserves_the_authoritative_terminal_outcome`
  (`:300`) proves it end-to-end through the port contract: `commit_terminal(...)` then
  `resolve_residual(...)` on the SAME store instance, and asserts
  `resolved.terminal_commit == bundle` (full bundle equality, not a signature check).

**Adversarial proof — reverted the two production files, kept the new tests, reran:**

```
FAILED tests/ports/test_durable_operation_store.py::test_resolving_residual_cleanup_preserves_the_authoritative_terminal_outcome
FAILED tests/ports/test_durable_operation_store.py::test_record_retains_terminal_commit_when_residual_cleanup_is_closed
FAILED tests/durable_operations/test_service.py::test_lifecycle_rejects_evidence_free_terminal_outcomes[succeeded-accepted]
FAILED tests/durable_operations/test_service.py::test_lifecycle_rejects_evidence_free_terminal_outcomes[succeeded-in_progress]
FAILED tests/durable_operations/test_service.py::test_lifecycle_rejects_evidence_free_terminal_outcomes[succeeded-reconciliation_required]
FAILED tests/durable_operations/test_service.py::test_lifecycle_rejects_evidence_free_terminal_outcomes[succeeded-terminal_pending]
FAILED tests/durable_operations/test_service.py::test_lifecycle_rejects_evidence_free_terminal_outcomes[failed-accepted]
FAILED tests/durable_operations/test_service.py::test_lifecycle_rejects_evidence_free_terminal_outcomes[failed-in_progress]
FAILED tests/durable_operations/test_service.py::test_lifecycle_rejects_evidence_free_terminal_outcomes[failed-reconciliation_required]
FAILED tests/durable_operations/test_service.py::test_lifecycle_rejects_evidence_free_terminal_outcomes[failed-terminal_pending]
10 failed, 32 passed in 0.60s
```

All 10 new behavioral tests fail against the pre-fix implementation, confirmed against real
production code — not `inspect.signature`, not mocks. Re-applied the fix; full suite returns to
460 passed, 1 deselected.

## Unchanged Branch Still Guarded

Claim: `CLOSED` + terminal_commit with EMPTY `residual_cleanup` must still be REJECTED.

- `test_record_rejects_closed_lifecycle_without_residual_cleanup` (`:336`) constructs exactly this
  record and asserts `pytest.raises(ValueError, match="terminal outcome lifecycle")`. PASS.
- The pre-existing regression test
  `test_record_rejects_terminal_outcome_lifecycle_when_residual_cleanup_exists` (`:263`,
  `match="cleanup_required lifecycle"`) is untouched and still green — confirms the FIRST error
  message (residual non-empty, wrong lifecycle) still fires and its substring survived the
  message edit (`"...cleanup_required lifecycle until the obligation is resolved as closed"`
  still contains `cleanup_required lifecycle`).

## Evidence Gate

Claim: `advance_lifecycle` rejects evidence-free transitions to SUCCEEDED/FAILED, while the
idempotent `SUCCEEDED->SUCCEEDED` carve-out still works.

- Rejection: `test_lifecycle_rejects_evidence_free_terminal_outcomes` — 8-way parametrized over
  `{ACCEPTED, IN_PROGRESS, RECONCILIATION_REQUIRED, TERMINAL_PENDING} x {SUCCEEDED, FAILED}`, all
  assert `InvalidLifecycleTransitionError`. PASS, all 8 cases.
- Carve-out preserved: pre-existing
  `test_lifecycle_keeps_terminal_outcomes_re_advanceable_towards_cleanup_and_closure` (`:86`)
  exercises `SUCCEEDED->SUCCEEDED` and `FAILED->CLEANUP_REQUIRED` and still passes unmodified.
  Design explicitly notes this test breaks without the 3b carve-out — confirmed by inspection of
  the new guard's placement (inserted AFTER the flip guard, so `target is not current` in the
  flip guard still intercepts same-state re-advances before the new guard runs).

## Fake Behavioral Round-Trip

`_ConformingDurableOperationStore` gained exactly one state slot:
`self._record: DurableOperationRecord | None = None` (`tests/ports/test_durable_operation_store.py:53`).
Grep-verified: written only in `commit_terminal` (`:104`), read only in `resolve_residual` (`:111`).
No other method touches it. `commit_terminal -> resolve_residual` round-trips the SAME bundle
object (`resolved.terminal_commit == bundle`, asserted by equality, not signature inspection) —
this is a real behavioral proof, not a structural-typing check.
`test_store_contract_exposes_replay_checkpoint_cas_residual_and_recovery_queries` inspects the
`Protocol` class itself, never the fake instance, so the new attribute cannot affect it — confirmed
by reading the test (`:166`) and re-running it (still passes).
`test_resolving_residual_without_an_open_obligation_is_rejected` (`:312`) proves the fake is not a
silent no-op: a fresh instance with no `commit_terminal` call raises
`InvalidLifecycleTransitionError` on `resolve_residual`. PASS.

## Design Fidelity

| Check | Result |
|---|---|
| Archive `design.md:110` byte-intact | CONFIRMED — `git diff --numstat` shows `8 insertions, 0 deletions`; line 110 content unchanged (`RecoveryPlan` row still lists `resume, reconcile, compensate, surface_residual` as the original drifted text, preserved verbatim as required — this is intentional per Design Decision 4: an audit trail, not a fix in place) |
| Correction note is append-only, placed after the Interfaces table | CONFIRMED — inserted after line 111, before `Provider alignment:` |
| Fake has exactly ONE state slot | CONFIRMED — `rg` shows only `self._record`, no other new instance attribute |
| No new error class | CONFIRMED — `InvalidLifecycleTransitionError` reused throughout; `errors.py` unmodified; `UnknownOperationOutcomeError` remains defined but unraised, untouched |
| `_RESIDUAL_LIFECYCLES` predicate matches design.md:37-58 exactly | CONFIRMED — diff matches verbatim, including the required substring `cleanup_required lifecycle` preserved in the first error message |
| Guard order in `advance_lifecycle` (regress -> flip -> new terminal-target check) | CONFIRMED — new guard inserted after the existing flip guard (`git diff` shows insertion point directly above `return target, _next_revision(revision)`) |

## Non-Goals Untouched

- `COMPENSATE` / `CompensationScope` / `ensure_compensation_target`: zero diff hits (`rg` search on
  the diff for `compensate` case-insensitive: no matches in changed source files).
- `TERMINAL_PENDING`: zero diff hits; remains a dead lifecycle target as documented in design's
  Open Questions.
- `UnknownOperationOutcomeError`: unmodified, still unraised.
- No adapter or workflow module imports `DurableOperationStore`/`DurableOperationRecord` outside
  `src/odoo_forge/ports/` — confirmed via `rg -l` excluding `tests/` and `ports/`: zero hits.

## Quality Gates — Actual Output

| Gate | Command | Result |
|---|---|---|
| Import boundaries | `uv run lint-imports` | PASS — Contracts: 6 kept, 0 broken |
| Lint | `uv run ruff check .` | PASS — All checks passed! |
| Format | `uv run ruff format --check .` | PASS — 107 files already formatted |
| Type check | `uv run mypy` (strict) | PASS — Success: no issues found in 104 source files |
| Tests | `uv run pytest` | PASS — 460 passed, 1 deselected |

All five gates executed directly in this verification session (not taken from apply's report) and
all pass with zero failures, zero new warnings.

## Test Quality Audit (Strict TDD)

- New assertions call real production code paths (`DurableOperationRecord.__post_init__` via direct
  construction, `advance_lifecycle(...)` directly, `commit_terminal`/`resolve_residual` on a live
  fake instance) — no tautologies, no `inspect.signature` checks, no mock-heavy patterns.
- Triangulation: the evidence-gate scenario is triangulated across 8 parameter combinations (4
  states x 2 outcomes), not a single case. The CLOSED-retention scenario is triangulated across two
  tests at different layers (direct dataclass construction + full port round-trip).
- **Adversarial validation performed** (see "CRITICAL Defect" section above): all 10 new tests
  provably fail against the pre-fix code when isolated from the fix — this is the strongest
  available evidence that these are real regression tests, not tests that mirror the
  implementation.
- No banned assertion patterns found (no `expect(true).toBe(true)` equivalents, no ghost loops, no
  smoke-test-only patterns) in the reviewed diff.

**Assertion quality**: All assertions verify real behavior.

## Issues

### CRITICAL
None.

### WARNING
1. **Untested scenario**: "A closed record with no terminal work is still valid" (delta spec,
   Residual Cleanup Visibility) has no dedicated test with `lifecycle=CLOSED, terminal_commit=None`.
   Structurally guaranteed by unconditional early-return, unaffected by this change's edits, but
   the scenario is spec-declared and currently relies on code inspection rather than a named test.

### SUGGESTION
1. Consider adding `test_closed_record_without_terminal_commit_is_valid` for full 1:1 spec-scenario
   traceability, even though the behavior is already provably correct and pre-existing.

## Final Verdict

**PASS WITH WARNINGS** — one traceability gap (WARNING, non-blocking, pre-existing behavior, not
a defect in this change). The CRITICAL defect this change targets is fixed and proven behaviorally
adversarial-tested. All quality gates pass. Design fidelity is verbatim. Non-goals are untouched.
Recommend proceeding to `sdd-archive`; the WARNING may be resolved before or after archive at the
user's discretion since it does not indicate incorrect behavior.
