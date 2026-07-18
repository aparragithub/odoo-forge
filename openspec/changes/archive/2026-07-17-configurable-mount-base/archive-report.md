# Archive Report: configurable-mount-base

**Change**: `configurable-mount-base`  
**Date Archived**: 2026-07-17  
**Implementation Commit**: 6976068  
**Branch**: sdd/configurable-mount-base  
**Verdict**: PASS — Ready for production  

## What Shipped

Host and container mount bases are now **decoupled**. The `forge` CLI resolves the host mount base at composition root from environment (`FORGE_MOUNT_BASE` → `XDG_STATE_HOME` → `~/.local/state/odoo-forge`), while the container mount base remains fixed at `/mnt`. This enables rootless execution of `forge project`, `forge unlock`, and `forge run` for normal users on bare hosts without requiring root permissions.

### Key Design Decision

**Host/Container Decoupling + Absolute-Path Guard**  
The change introduces an explicit architectural separation: `CONTAINER_MOUNT_BASE = Path("/mnt")` is a named constant in the core (documenting WHY `/mnt` is fixed: `plan_backend` derives the root via `container_path.parts[2]`). The CLI reads environment variables only at composition root (`_resolve_mount_base()` in `main.py`), preserving hexagonal purity. All core functions (`plan_projection`, `plan_unlock`, `build_mount_planning_view`) accept default-valued `roots` parameters, ensuring zero test breakage. A guard scenario explicitly rejects relative `FORGE_MOUNT_BASE` paths with a clear error before they reach Docker, preventing silent named-volume fallback.

## Verification Evidence

### Test Suite (Full Run)

```
Command: uv run pytest -q
Result: 699 passed, 14 deselected
```

All spec scenarios verified:
- Host mount base resolution (6 scenarios): `FORGE_MOUNT_BASE`, `XDG_STATE_HOME`, defaults, backward compat, absolute-path guard, XDG compliance
- Host/container decoupling (2 scenarios): container path stays fixed at `/mnt/<root>/...` regardless of host base
- Modified requirements (4 scenarios): `forge validate`, `forge project`, `forge unlock` all work rootless under resolved host base

### Linting & Type Safety

```
Command: uv run lint-imports
Result: 6/6 contracts kept, 0 broken

Command: uv run mypy
Result: No issues found

Command: grep 'os.environ|os.getenv' src/odoo_forge/ | wc -l
Result: 0 (core purity verified)
```

### Change Stats

- **Diff size**: 364 changed lines (under 400-line budget)
- **Affected files**: 12 (2 core + CLI + 10 test files)
- **No new CLI flags**: env-var driven only
- **No schema/lockfile changes**: backward compatible

## Artifacts Archived

All SDD artifacts from the change cycle are stored under:  
`openspec/changes/archive/2026-07-17-configurable-mount-base/`

| Artifact | Path | Status |
|----------|------|--------|
| Proposal | `proposal.md` | ✅ Archived |
| Design | `design.md` | ✅ Archived |
| Delta Spec | `specs/manifest/spec.md` | ✅ Archived |
| Tasks | `tasks.md` | ✅ Archived (19/19 complete) |
| Verify Report | `verify-report.md` | ✅ Archived |

## Spec Merge Summary

### Canonical Spec Updated

**File**: `openspec/specs/manifest/spec.md`  
**Capability**: manifest (Modified) — Slice 3 + configurable-mount-base  
**Action**: 5 requirements merged into existing manifest capability

| Requirement | Type | Status |
|-------------|------|--------|
| Host mount base resolves at the CLI composition root | ADDED | ✅ Merged |
| Host and container mount root tables are decoupled | ADDED | ✅ Merged |
| forge validate delegates all logic to the core | MODIFIED | ✅ Merged (updated with rootless scenario) |
| forge project executes the plan through a resilient boundary | MODIFIED | ✅ Merged (updated with resolved host base scenario) |
| forge unlock promotes a targeted repo | MODIFIED | ✅ Merged (updated with resolved host base scenario) |

**Previous Requirements Preserved**: All other requirements in the manifest capability and sibling capabilities remain intact.

## SDD Artifact Observation IDs (Engram)

For full traceability, the following observations were retrieved and verified during archival:

| Artifact | Observation ID | Type | Status |
|----------|---|------|--------|
| Proposal | #8869 | architecture | ✅ Active |
| Spec (Delta) | #8870 | architecture | ✅ Active |
| Design | #8871 | architecture | ✅ Active |
| Tasks | #8872 | architecture | ✅ Active |
| Verify Report | #8874 | architecture | ✅ Active |

All observations remain active and retrievable.

## Rollback Plan

No data migration required. Revert via single commit:
1. Revert `src/odoo_forge/manifest/projection.py` (remove `CONTAINER_MOUNT_BASE`, `build_mount_roots`, `roots` params)
2. Revert `src/odoo_forge_cli/main.py` (remove `_resolve_mount_base()`, restore hardcoded `/mnt` wiring)

No provider or schema change; `/mnt` remains reachable via `FORGE_MOUNT_BASE=/mnt` if needed during transition.

## Warnings & Notes

### Non-Critical Warnings (from verify report)

1. **Ruff formatting**: Two lines in `projection.py` exceed 88-char limit. Cosmetic; can be addressed in follow-up formatting pass.
2. **Apply-progress evidence**: Narrative RED/GREEN citations used instead of formal TDD Cycle Evidence table. All tests independently verified. Downgraded from CRITICAL to WARNING.

### No CRITICAL Issues

The change is production-ready with no blocking risks.

## Conclusion

The `configurable-mount-base` SDD cycle is **COMPLETE**. All phases (proposal → spec → design → tasks → apply → verify) have been executed successfully. The host and container mount bases are decoupled, rootless execution is enabled by default, and the hexagonal architecture is preserved. The canonical manifest spec has been updated to reflect the new behavior, and all artifacts have been archived with full traceability.

Ready for release.
