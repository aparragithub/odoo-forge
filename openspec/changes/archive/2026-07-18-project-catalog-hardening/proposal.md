# Proposal: Harden catalog default validation against blank strings

## Intent

`validate_record` (`src/odoo_forge/project_catalog/validation.py`) only rejects `None`
for required fields. For `defaults.data_policy` and `defaults.target`, a blank or
whitespace-only string (`""`, `"   "`) currently passes as VALID and flows into
`ResolvedCatalogResult.data_policy_default` / `target_default` as empty data.
This is a materially different failure from `None` (silent bad data vs. absent data),
yet today both are handled identically — except blank strings are not caught at all.
The gap lets an unusable resolution reach downstream consumers instead of failing
deterministically at the validation boundary.

## Scope

### In Scope
- Treat blank/whitespace-only `data_policy` and `target` defaults as MISSING in
  `invalid_required_fields` / `validate_record`.
- Emit the existing deterministic `InvalidCatalogRecord` with the current
  `missing:field1+field2` reason-code convention.
- Preserve the fixed field order in `invalid_required_fields`
  (`manifest_ref`, `source_context`, `data_policy_default`, `target_default`).
- Additive tests in `tests/project_catalog/test_resolver.py` covering blank and
  whitespace-only defaults, singly and combined with existing `None` cases.

### Out of Scope
- Any change to `resolver.py`, `models.py`, `interfaces.py`.
- Signature changes, `InvalidCatalogRecord` shape or reason-code format changes,
  resolver control-flow changes.
- Blank-string handling for `manifest_ref` / `source_context` (typed refs, not strings).
- Workspace, manifest, database, or any other area.

## Capabilities

### New Capabilities
- None.

### Modified Capabilities
- None at the spec/requirement level. This tightens the existing validation
  invariant (required outputs must be materialized) to include blank strings;
  no external contract or reason-code format changes.

## Approach

In `invalid_required_fields`, extend the `data_policy` and `target` checks from
`is None` to also fail when the string is present but blank after `.strip()`.
Mirror the same condition in the `validate_record` short-circuit so both paths
agree. No new fields, no reason-code change: a blank `data_policy` yields the same
`missing:data_policy_default` classification a `None` would. Order is preserved
because the append sequence is unchanged.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `src/odoo_forge/project_catalog/validation.py` | Modified | Blank/whitespace defaults treated as missing |
| `tests/project_catalog/test_resolver.py` | Modified | Additive coverage for blank defaults |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Legitimately blank default was relied upon | Low | Empty policy/target was never usable; failing fast is the correct behavior |
| Reason-code drift breaking consumers | Low | Reuse exact `missing:` format and field order |

## Rollback Plan

Revert the single edit to `validation.py` (and its added tests). No migrations,
data, or interface state to unwind; behavior returns to `None`-only checks.

## Dependencies

- None.

## Success Criteria

- [ ] Blank/whitespace `data_policy` or `target` produces `InvalidCatalogRecord`.
- [ ] Reason code and `invalid_fields` order match existing `None`-case output.
- [ ] `resolver.py`, `models.py`, `interfaces.py` untouched; existing tests pass.
- [ ] Diff small enough to run in parallel with an unrelated worktree change.
