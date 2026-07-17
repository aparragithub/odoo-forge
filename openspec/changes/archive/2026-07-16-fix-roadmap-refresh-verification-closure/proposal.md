# Proposal: Fix Roadmap Refresh Verification Closure

## Intent

Close seven blockers in `refresh-platform-roadmap-after-stabilization`. This child amends the parent PR3 candidate with a bounded corrective delta; the combined candidate requires new review authority and verification.

## Scope

### In Scope
1. Accept canonical `Apply Complete — Ready for sdd-verify` status.
2. Run fixed-renderer `--check`; reject Mermaid/SVG drift.
3. Require the exact repository-contained current-guide HTML link.
4. Preserve valid S62; in isolated fixtures, remove unverifiable evidence references and persist explicit `gap_catalog` entries.
5. Require validated HTML metadata for hand-authored ownership and current/target scope; refuse unverified ownership.
6. Validate ≤400 authored lines and Unit4 exclusion from parent tasks/progress, not global policy.
7. Pass Ruff lint and format in both validator files.
- Snapshot the exact uncommitted failed parent report and SHA-256 as immutable child evidence; leave the original unchanged.

### Out of Scope
- Gentle AI, Unit4 runtime-risk work, other docs, or global policy.
- Editing original failed evidence, protected history, or unrelated chronology.

## Capabilities

### New Capabilities
None.

### Modified Capabilities
- `platform-portfolio-documentation-integrity`: enforce status, derivation, link, gap, ownership, and slice requirements.

## Approach

Force chained delivery. Keep implementation correction within one focused ≤400-authored-line slice; planning/evidence baseline MAY be a separate bounded slice. Use strict RED/GREEN/REFACTOR per blocker, including fixtures proving removal plus gap reporting only when evidence is unverifiable. Production runs fixed-renderer `--check`; unit tests use an injectable seam. Copy the failed report byte-for-byte to `evidence/parent-verify-fail.md` and record its SHA-256.

Lifecycle: implement child → review child → child `sdd-verify` → incorporate correction into parent candidate → create, approve, and bind a **new compact parent lineage** to the combined candidate → parent `sdd-verify`.

## Affected Areas

| Area | Impact | Description |
|---|---|---|
| `docs/tools/platform_portfolio/{validate,test_validate}.py` | Modified | Enforcement and TDD coverage |
| `docs/specs/platform/portfolio.json` | Conditional | Change only if current evidence becomes invalid; current valid S62 remains |
| `docs/specs/platform/platform-architecture.html` | Modified | Ownership/scope metadata |
| `evidence/parent-verify-fail.md` | New | Exact failed evidence snapshot |

## Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| Environment-dependent tests | Medium | Inject execution; retain live `--check` |
| Failed evidence loss | Medium | Snapshot and hash before incorporation |

## Rollback Plan

Revert child slices and remove the new parent binding before final verification. Keep the failed snapshot immutable.

## Dependencies

- Blocked parent, failed report, and task/progress evidence.

## Success Criteria

- [ ] Focused tests preserve valid S62 and prove removal plus `gap_catalog` reporting for unverifiable fixture evidence; Ruff passes.
- [ ] Implementation correction is ≤400 authored lines; child review/verify pass.
- [ ] Failed snapshot matches its recorded SHA-256.
- [ ] New lineage is approved/bound before successful parent reverification.
