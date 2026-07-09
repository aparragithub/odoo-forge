# Proposal: SP1-B — Runtime Digest Consumption for Local Docker

## Proposal question round

Assumes `forge run` accepts an operator-supplied canonical digest ref, only the local Docker backend pulls it, and digest persistence stays deferred.

## Intent

Close the gap left by `sp1-a`: operators can resolve/validate immutable GHCR refs, but `forge run` still boots the tag template. `sp1-b` makes the validated digest executable without pulling `project.lock` or registry-resolution work into scope.

## Scope

### In Scope
- Add runtime input for a canonical digest-backed Odoo image on `forge run`.
- Make backend planning prefer the supplied digest over `odoo-forge-odoo:{odoo_version}`.
- Make the local Docker adapter perform explicit `docker pull` before container start with clean pull-failure diagnostics.

### Out of Scope
- `project.lock` schema/storage changes or replay-from-lock behavior.
- `PublishedLayer` / `registry://` resolution, multi-registry routing, or non-Docker backend support.

## Capabilities

### New Capabilities
- None.

### Modified Capabilities
- `local-backend`: add digest-aware runtime image selection and explicit local-daemon pull behavior before `run()`.

## Approach

Use the bounded seam from exploration: thread an optional canonical digest ref from `src/odoo_forge_cli/main.py` into `plan_backend`, store the chosen image on `BackendPlan.odoo.image`, and keep pull side effects inside `src/odoo_forge_docker/provider.py` so the `BackendProvider` port changes only if tests prove it is unavoidable.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `src/odoo_forge_cli/main.py` | Modified | Accept and validate runtime digest input for `forge run` |
| `src/odoo_forge/backend/plan.py` | Modified | Prefer digest-backed image refs in the backend plan |
| `src/odoo_forge_docker/provider.py` | Modified | Pull the chosen image before `docker run` |
| `tests/backend/`, `tests/adapters/`, `tests/cli/` | Modified | Cover planner, Docker pull, and CLI failure boundaries |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Scope creeps into lockfile persistence | Med | Keep digest input ephemeral and exclude `project.lock` edits |
| Pull semantics leak beyond Docker | Med | Specify local-daemon-only behavior in the delta spec |
| Pull failures blur auth/not-found/runtime errors | Med | Add typed diagnostics at the Docker boundary |

## Rollback Plan

Revert the new `forge run` digest input, restore tag-only planning, and remove the explicit pull path/tests. No schema migration or persisted state rollback is required.

## Dependencies

- Existing GHCR digest normalization/validation from `sp1-a`
- Local Docker CLI/daemon availability

## Success Criteria

- [ ] An operator can start `forge run` against a canonical digest-backed Odoo image.
- [ ] Local Docker pulls that image before container startup and fails cleanly on pull errors.
- [ ] No `project.lock` schema change or `phase-2-slice-4a-registry-resolution` scope is introduced.
