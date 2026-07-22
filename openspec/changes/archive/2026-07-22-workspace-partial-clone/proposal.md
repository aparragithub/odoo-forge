# Proposal: Workspace Partial Clone

## Intent

`GitWorkspaceProvider._clone_and_replace` full-clones every source repo (Odoo
core carries >1GB of history) only to materialize a read-only working tree at
one pinned commit. `--no-checkout` skips the temp tree but not the download.
Switch to a **partial clone** (`--filter=blob:none --no-checkout`) so git fetches
the commit/tree graph and defers blobs, cutting the download substantially while
preserving the `checkout`/`promote`/`unlock` contract.

## Scope

### In Scope
- Change `_clone_and_replace` to `git clone --filter=blob:none --no-checkout`.
- Keep `checkout()`, `promote()`, `_atomic_swap`, and the `WorkspaceProvider`
  port contract unchanged in behavior.
- Transparent full-clone fallback when the remote does not advertise
  `uploadpack.allowFilter`.
- New hermetic integration test spawning real git against a local fixture with
  `uploadpack.allowFilter=true`, exercising clone → checkout → promote →
  worktree-add.

### Out of Scope
- Shallow single-commit fetch (`--depth 1` / fetch-by-SHA) — possible future work.
- No manifest schema changes; no per-repo opt-out surface.
- No change to lockfile format, resolution, or the port signature.

## Capabilities

### New Capabilities
None.

### Modified Capabilities
None. Observable behavior (a read-only tree pinned at the locked commit) is
unchanged; this is an internal clone-strategy optimization.

## Approach

Replace the clone command's flags. The existing follow-up
`checkout --detach <commit>` triggers on-demand blob fetch for that commit;
`promote`'s `worktree add` targets the same already-checked-out commit, so its
blobs are locally cached and it stays offline-safe. **Fallback:** attempt the
partial clone; on failure caused by an unadvertised `allowFilter`, retry once
with a full clone (no `--filter`). Bias toward robustness — a materialization
that works on every remote beats one that fails on some. No manifest surface:
keep it transparent and simple; revisit configurability only if a concrete need
appears.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `src/odoo_forge_workspace/provider.py` | Modified | `_clone_and_replace` flags + fallback |
| `tests/adapters/test_workspace_provider_integration.py` | New | Real-git hermetic test |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Existing unit tests mock `subprocess.run` → false confidence | High | New real-git integration test is mandatory |
| Remote lacks `uploadpack.allowFilter` | Med | Transparent full-clone fallback |
| `worktree add` on partial clone needs network | Low | Same-commit blobs cached; verified by integration test |

## Rollback Plan

Revert `_clone_and_replace` to `git clone --no-checkout` (drop `--filter` and the
fallback branch). Single-function change, no data/state migration.

## Dependencies

- git ≥ 2.19 (partial clone + worktree support) in the runtime environment.

## Success Criteria

- [ ] `_clone_and_replace` uses `--filter=blob:none` with transparent full-clone fallback.
- [ ] Integration test proves clone → checkout → promote → worktree-add against a real `allowFilter` fixture.
- [ ] Measurable download reduction on the Odoo core repo.
- [ ] `checkout`/`promote`/port behavior unchanged.
