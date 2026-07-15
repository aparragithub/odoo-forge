# Proposal: Decide Manifest Layer and Override Semantics

## Intent

Complete `PublishedLayer` and `Override` behavior instead of silently omitting or ignoring declarations. Unit 1 is complete through issue #55 / PR #62.

## Scope

### In Scope
- Resolve every `PublishedLayer` to its declared version plus immutable artifact digest; fail when the registry cannot supply a digest.
- Apply each valid `Override` before source/ref resolution and record the effective fork/ref in the lock.
- Add lock schema v2 for published entries; the updated reader accepts v1/v2 and rejects unknown versions.
- Reject duplicate overrides, unknown targets, PublishedLayer/core targets, and ambiguous or invalid combinations.

### Out of Scope
- Deprecating or removing either manifest feature.
- Canonicalizing repository identities: `Override.repo` exactly matches the target additional `GitLayer` repository URL; this coupling is accepted.
- Changing portfolio status/dependencies or revisiting Unit 1. Historical roadmaps remain evidence only; `docs/specs/platform/portfolio.json` remains authoritative.
- Modifying or advancing `CHG-FIRST-DATABASE-ADAPTER` or `sp-data-environments`.

## Capabilities

### New Capabilities
None.

### Modified Capabilities
- `manifest`: Define published resolution, Git-only override application, effective-source locking, and lock compatibility.

## Approach

Keep composition and locks in the pure core, with artifact and Git resolution behind injected ports. Validate overrides before I/O and replace the declared Git source/ref before resolution. Give published locks a distinct version-and-digest shape. Preserve deterministic serialization and v1 reads. Pre-v2 binary behavior is unsupported. Use chained PR units within the 400-line budget.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `openspec/specs/manifest/spec.md` | Modified | Resolution, validation, and compatibility contract |
| `src/odoo_forge/manifest/` | Modified | Validation, resolution, and lock models |
| `src/odoo_forge/ports/` and registry/Git adapters | Modified | Injected resolution boundaries |
| `tests/manifest/`, `tests/cli/` | Modified | Contract and failure evidence |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Unsupported locks are misread | Medium | Validate the supported version set in updated readers |
| Mutable artifacts or wrong override sources are pinned | Medium | Require digests; apply overrides before resolution |
| Existing Git-only workflows regress | Low | Preserve legacy reads and add compatibility coverage |

## Rollback Plan

Revert the resolver, override application, and v2 writer. Restore prior v1 locks for Git-only manifests; retain v2 locks for forward recovery and never downgrade by dropping published entries.

## Dependencies

- Registry support for immutable published-artifact digests.

## Success Criteria

- [ ] Locks pin each published layer by version and digest and each override by effective source/ref.
- [ ] Invalid targets/combinations and missing digests fail before writing a lock.
- [ ] Updated readers accept v1/v2 locks and reject unknown versions.
- [ ] Git-only manifests remain deterministic and compatible.
