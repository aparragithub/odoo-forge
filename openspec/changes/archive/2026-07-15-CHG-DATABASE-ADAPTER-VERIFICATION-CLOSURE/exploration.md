## Exploration: CHG-DATABASE-ADAPTER-VERIFICATION-CLOSURE

### Current State
`CHG-FIRST-DATABASE-ADAPTER` adds an isolated Docker PostgreSQL provider and preserves the provider-neutral `DatabaseProvider` contract. Its `provision` path materializes a target credential file, provisions the container, and on failure retries unlinking the file before rolling back receipt-owned containers. A failed unlink is recorded as `credential-file`, but `_raise_after_rollback` raises `RollbackIncompleteError` only when container rollback has residuals. If container rollback succeeds, the original redacted provider error is re-raised and the credential-file residual is hidden.

The existing rollback error already carries receipt, resource residuals, and cleanup failures, so the smallest contract-preserving correction is to treat credential-target cleanup as a first-class residual in that same rollback outcome. The residual identifier must remain the existing opaque safe token (`credential-file`); no path, handle, descriptor, or secret may enter the exception, receipt, report, or diagnostic.

The parent also has pure `evaluate_gate_readiness` logic requiring proposal, specification, design, and verification identifiers. It already returns `is_ready=False` and names missing identifiers. Its tests prove incomplete identifiers are detected, but they do not explicitly represent simulated/incomplete real-Docker acceptance evidence. The cheapest runtime closure is one focused acceptance-policy test (or the smallest existing readiness test extension) that supplies otherwise complete evidence while omitting the real-Docker/ownership evidence marker and asserts acceptance remains false. This tests policy, not portfolio state transitions or a new control-plane capability.

### Affected Areas
- `src/odoo_forge_postgres_docker/provider.py` — propagate credential-file cleanup residuals through the existing rollback-incomplete error path even when container rollback succeeds.
- `src/odoo_forge_postgres_docker/errors.py` or the provider’s existing error definition location — only if needed to make the existing rollback error’s residual fields explicitly support opaque cleanup residuals; avoid a new error family unless current typing requires it.
- `tests/adapters/test_postgres_docker_provider.py` — add the regression oracle for persistent target-file unlink failure, asserting an opaque residual and absence of path/secret material.
- `src/odoo_forge/database/readiness.py` — likely unchanged; reuse the existing pure evaluator unless the acceptance evidence model cannot express the missing real-Docker marker.
- `tests/database/test_readiness.py` — add the minimal negative acceptance-policy runtime test for incomplete/simulated evidence.
- `openspec/changes/CHG-FIRST-DATABASE-ADAPTER/verify-report.md` — read-only evidence only; parent artifact must not be edited by this change.
- `openspec/changes/CHG-FIRST-DATABASE-ADAPTER/specs/docker-postgresql-database-adapter/spec.md` and `openspec/specs/database-provider/spec.md` — source contracts to preserve; no provider-neutral signature changes are indicated.

### Approaches
1. **Extend existing rollback residual propagation** — merge `cleanup_failures` with container residuals and raise the existing `RollbackIncompleteError` whenever either set is non-empty.
   - Pros: smallest behavioral change; preserves rollback receipt/residual semantics; keeps the opaque identifier allow-list and redaction boundary; directly fixes the reported branch.
   - Cons: callers must already handle the existing rollback-incomplete typed error for this failure mode.
   - Effort: Low

2. **Return a cleanup report or introduce a separate credential-cleanup error** — expose the file residual through `CleanupReport` or a new typed error independently of rollback failure.
   - Pros: can distinguish target-file cleanup from resource rollback at the API level.
   - Cons: expands the provider-neutral or adapter error surface; risks losing the receipt that proves rollback scope; requires more tests and contract decisions; unnecessary for a single hidden residual.
   - Effort: Medium/High

3. **Acceptance test through portfolio validation** — invoke the portfolio validator with a deliberately incomplete acceptance record and assert it remains unaccepted.
   - Pros: exercises the most literal portfolio acceptance representation.
   - Cons: couples this adapter closure to portfolio governance and a script-level plan format; broader and slower than the existing pure readiness evaluator; risks absorbing excluded control-plane scope.
   - Effort: Medium

4. **Acceptance test at the existing pure readiness boundary** — construct complete approval identifiers but omit the real-Docker/ownership evidence required by the acceptance policy, then assert `is_ready` is false and the missing evidence is reported.
   - Pros: cheapest runtime proof; deterministic and fast; no new control-plane capability; directly establishes fail-closed policy.
   - Cons: requires the current evidence model to represent the missing acceptance marker without changing unrelated contracts.
   - Effort: Low

### Recommendation
Use Approach 1 for credential cleanup and Approach 4 for acceptance evidence. Make `_raise_after_rollback` consider both container residuals and cleanup residuals, preserving the existing receipt and typed rollback-incomplete outcome. Keep `credential-file` as the only public residual token and assert that exception text contains neither the temporary path nor the credential value. Add one focused negative readiness test using the smallest evidence omission that corresponds to incomplete/simulated real-Docker acceptance; do not add portfolio mutation, control-plane state, or provider selection.

The change must remain additive and provider-neutral: no edits to `DatabaseProvider`, credential/data-artifact value contracts, local backend routing, adjacent capabilities, or portfolio governance. The parent PR4 implementation is a prerequisite because the regression test targets its current provider behavior. Safe integration order is: land/merge the parent PR chain through PR4 (without treating its failed verification as acceptance), branch this follow-up from the parent’s final integrated commit, implement the two focused closures, run focused tests plus the default/static/build gates, then rerun independent strict verification before archive. Do not integrate this follow-up before the parent implementation it closes.

### Risks
- The residual identifier must pass `CleanupReport`’s safe-opaque validation; exposing a path or secret would violate both redaction and credential-lifetime contracts.
- Raising rollback-incomplete for a credential-file-only residual changes the observable typed error on a failure path; tests and callers must preserve the original exception as its cause while exposing only the safe residual.
- A test that only checks missing proposal/design/verification identifiers would duplicate existing readiness coverage and would not close the specific simulated/incomplete acceptance gap.
- Portfolio validator changes could unintentionally absorb governance scope; keep this closure at the existing runtime acceptance-policy boundary.
- This follow-up depends on parent PR4’s exact error and test seam; if PR4 changes before integration, rebase and revalidate the targeted symbols rather than copying implementation assumptions.

### Ready for Proposal
Yes. The closure is bounded to one existing rollback error path and one deterministic fail-closed acceptance-policy test. The proposal should explicitly state the dependency on `CHG-FIRST-DATABASE-ADAPTER`/PR4, preserve all exclusions, require opaque `credential-file` residual reporting, and require runtime proof that incomplete or simulated evidence cannot produce acceptance.

## Result Contract

```yaml
status: ready
summary: "Exploration identified the smallest additive closure for both independent verification findings."
artifacts:
  - "openspec/changes/CHG-DATABASE-ADAPTER-VERIFICATION-CLOSURE/exploration.md"
evidence:
  - "Read-only parent verification report: CHG-FIRST-DATABASE-ADAPTER/verify-report.md"
  - "Parent adapter provider, database-provider contracts, readiness evaluator, and relevant tests"
next_recommended: propose
risks:
  - "Parent PR4 implementation must be integrated before this follow-up can be applied."
  - "Credential cleanup residuals must remain opaque and preserve rollback receipt semantics."
skill_resolution: paths-injected
```
