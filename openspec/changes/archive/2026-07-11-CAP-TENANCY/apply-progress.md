# Apply Progress: CAP-TENANCY

## Status

Completed all four approved documentation-alignment tasks. This change remains contract-first and contains no runtime, persistence, provider, auth, or control-plane implementation.

## Completed Tasks

- [x] Normalize the CAP-TENANCY source contract — source proposal, specification, and design already expressed every approved decision; verified them without adding scope.
- [x] Align portfolio dependency and readiness metadata — made `CAP-TENANCY` the prerequisite for the renamed SP-3/SP-4/SP-8 portfolio entries, aligned the tenancy decision to customer/client, and added required readiness handoffs.
- [x] Normalize downstream consumer briefs to consume CAP-TENANCY — SP-3, SP-4, and SP-8 now explicitly consume tenant identity, project scope, isolation expectations, ownership composition, and quota authority.
- [x] Final consistency sweep for readiness evidence — confirmed `AC-CAP-TENANCY-READY` is documentary readiness evidence only and does not introduce runtime work.

Persisted task checkbox updates: all four implementation task headings in `tasks.md` are marked `- [x]`.

## Files Changed

- `docs/specs/platform/portfolio.json`
- `docs/specs/platform/SP-3-remote-backend-providers.md`
- `docs/specs/platform/SP-4-control-plane-core.md`
- `docs/specs/platform/SP-8-instance-lifecycle-requests.md`
- `openspec/changes/CAP-TENANCY/tasks.md`
- `openspec/changes/CAP-TENANCY/apply-progress.md`

## Verification Evidence

- `python -m json.tool docs/specs/platform/portfolio.json` — passed.
- Focused Python portfolio assertions — passed: `CAP-TENANCY` has no predecessors, the three consumer entries depend on it, decision `DT` chooses `customer/client tenant`, and the required handoff edges exist.
- Focused `rg` contract search across CAP-TENANCY artifacts and SP-3/SP-4/SP-8 — confirmed `tenant_id`, customer/client, `environment_family` rejection, ownership composition, quota authority, and `CAP-TENANCY` consumption language.
- Focused legacy-authority search — no results for SP-4-owned tenancy, SP-3 tenancy ownership, SP-8 local quota authority, or the superseded organization-tenant wording.
- `git diff --check` — passed.
- `uv run pytest` — not run: this approved documentation/spec alignment has no runtime behavior and the task explicitly requires focused search/consistency evidence instead of invented runtime tests.

## TDD Cycle Evidence

| Task | Layer | Safety Net | RED | GREEN | TRIANGULATE | REFACTOR |
|---|---|---|---|---|---|---|
| Normalize source contract | Documentation contract | N/A — no production code | N/A — no runtime behavior | Focused contract search passed | N/A — documentary invariant review | N/A |
| Align portfolio metadata | Documentation/JSON | JSON parser passed | N/A — no runtime behavior | Dependency/readiness assertions passed | N/A — structural metadata only | N/A |
| Align downstream briefs | Documentation contract | N/A — no production code | N/A — no runtime behavior | Focused consumer-boundary searches passed | N/A — documentary invariant review | N/A |
| Final consistency sweep | Documentation contract | N/A — no production code | N/A — no runtime behavior | Legacy-authority search and whitespace check passed | N/A — no runtime behavior | N/A |

## Design Deviations

None. The source contract was already normalized; implementation limited changes to portfolio and downstream-consumer alignment plus persisted task progress.

## Workload / PR Boundary

Single documentation-only work unit. The task forecast is low risk, no chained PR, and `single-pr`; no commit was created.

## Structured Status Consumed

- `artifactStore`: `openspec`
- `applyState`: `ready`
- `nextRecommended`: `apply`
- `actionContext.mode`: `repo-local`
- `workspaceRoot` / allowed edit root: `/home/aparra/Desarrollo/odoo-forge-cap-tenancy`
- Warning: no action-context violations; all edits stayed inside the approved worktree.

## Remaining Tasks

None. All implementation task headings are checked.

## Next Step

Run `sdd-verify CAP-TENANCY` to independently validate the completed contract against the acceptance criteria.
