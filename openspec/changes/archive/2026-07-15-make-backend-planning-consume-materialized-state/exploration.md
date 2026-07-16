## Exploration: make-backend-planning-consume-materialized-state

### Current State
`plan_backend(manifest, state, ...)` still discards `MaterializedState` (`del state`) and hardcodes mounts from `MOUNT_ROOTS` (`src/odoo_forge/backend/plan.py`, `tests/backend/test_plan.py`). The CLI only materializes workspace state for `run` and `validate`; `status`, `stop`, `logs`, and `exec` intentionally call `plan_backend(..., MaterializedState())` because they only need deterministic instance identity (`src/odoo_forge_cli/main.py`, memory #7550).

`MaterializedState` is thin by design today: it stores only `layers -> repos(url, commit)` and no path/root authority (`src/odoo_forge/manifest/state.py`). `materialize_state()` keeps scan-path authority one level lower, deriving layer names from `/mnt/<root>/<layer>/...`, preferring worktrees over read-only entries, and raising `ScanError` for malformed paths (`src/odoo_forge/manifest/projection.py`, `tests/manifest/test_projection.py`). `detect_drift()` then uses that thin state only for `not_materialized` / `commit_mismatch` reporting (`src/odoo_forge/manifest/drift.py`, `tests/manifest/test_drift.py`).

Roadmap evidence is aligned: Unit 3 is the next bounded change, `portfolio.json` remains the product authority, and the roadmap explicitly keeps `CHG-FIRST-DATABASE-ADAPTER` and `sp-data-environments` outside this change (`docs/specs/2026-07-14-stabilization-roadmap.md`, `docs/specs/platform/portfolio.json`).

#### State failure modes
| Mode | Observable case | Current behavior | Candidate behavior if mounts become state-authoritative | Error ownership / boundary | Open product decision |
|---|---|---|---|---|---|
| Absent | no scan results; caller passes `MaterializedState()`; workspace roots absent | empty state is allowed; identity commands keep working; `validate` just reports drift against an empty state | `run` should fail closed, or explicitly degrade; silent static fallback would reintroduce the current bug | CLI `run` boundary; likely `WorkspaceError`/`ScanError`-class error | Is empty state a hard failure or an explicit no-op? |
| Incomplete | some roots present, others absent; locked repo missing from materialized data | state is partial; drift emits `not_materialized` for missing locked items | include only evidence-backed mounts; missing evidence should exclude/reject that mount rather than invent it | core planner or scanner/projection boundary | May provisioning proceed with a partial mount set? |
| Incoherent | path outside `/mnt/<root>/<layer>/...`; missing layer segment; impossible root/layer pairing | `materialize_state()` raises `ScanError` naming the bad path | reject before planning; this is a scan/projection contract violation, not a backend failure | workspace scan/materialization boundary | none; this boundary is already clear |
| Stale | valid path/root but commit differs from lock; worktree promotion supersedes read-only entry | drift reports `commit_mismatch`; state itself is not rejected | mount planning may still include the repo only if the path/root evidence is valid, but stale content should not be silently trusted for release semantics | drift/reporting or planner policy boundary | Does stale materialization block `run`, or only warn? |

#### What "authoritative for mounts" can mean today
`MaterializedState` cannot be the full authority for mount placement because it no longer remembers filesystem paths. The strongest meaning it can support today is: **repo identity/commit facts may gate inclusion of a predeclared mount root, but the root/path table itself still comes from the scan/projection layer**.

| Current root | What evidence is needed to include it | What excludes it | What rejects it | Identity vs path authority |
|---|---|---|---|---|
| `community` | a scanned repo under `/mnt/community/<layer>/...` with matching repo URL/commit | no scanned repo for that layer | malformed path or wrong layout => `ScanError` | URL/commit identify the repo; path asserts the root |
| `custom` | same, but under `/mnt/custom/<layer>/...` | no scanned repo for that layer | malformed path / impossible layer mapping => `ScanError` | repo identity and filesystem authority are separate |
| `localization` | same, but under `/mnt/localization/<layer>/...` | no scanned repo for that layer | malformed path / impossible layer mapping => `ScanError` | state only preserves repo facts after the scan chooses the root |
| `enterprise` | same, but under `/mnt/enterprise/<layer>/...` | no scanned repo for that layer | malformed path / impossible layer mapping => `ScanError` | root authority is not derivable from `MaterializedState` alone |
| `worktrees` | a promoted writable scan entry under `/mnt/worktrees/<layer>/<repo>` | not promoted / not scanned | a writable entry that does not belong to the expected layer/repo contract | special writable path authority, not repo identity | `worktrees` is a promotion artifact, not a normal read-only mount root |

#### Operations and call paths
**Require materialized workspace state**
- `run` → `_make_workspace_provider().scan(MOUNT_ROOTS.values())` → `materialize_state()` → `plan_backend()` → `backend_provider.run()`.
- `validate` → `compose()` → load `project.lock` → scan roots → `materialize_state()` → `detect_drift()`.

**Must remain state-independent**
- `status` → `plan_backend(parsed, MaterializedState())` → `instance_ref()` → `backend_provider.status()`.
- `stop`, `logs`, `exec` → `_derive_ref()` → `plan_backend(parsed, MaterializedState())` → `instance_ref()` → backend adapter call.

**Relevant but not state-derived**
- `lock` → `build_lock()`; no `MaterializedState`.
- `project` → `plan_projection()` then `project_workspace()`; uses lock/projection, not materialized state.
- `unlock` → `plan_unlock()` then `provider.promote()`; uses lock/projection, not materialized state.

### Affected Areas
- `src/odoo_forge/backend/plan.py` — today's mount construction ignores `state`; any mount authority change lands here or in a new planning view.
- `src/odoo_forge_cli/main.py` — `run`/`validate` are the state-consuming entry points; identity commands must stay empty-state paths.
- `src/odoo_forge/manifest/state.py` — current shape is too thin for path/root authority.
- `src/odoo_forge/manifest/projection.py` — defines the scan-path contract, `MOUNT_ROOTS`, and worktree precedence.
- `src/odoo_forge/manifest/drift.py` — proves current state is still identity/commit evidence, not mount authority.
- `src/odoo_forge/ports/backend_provider.py` / `src/odoo_forge_docker/provider.py` — adapter boundary stays on `BackendPlan`/`InstanceRef`.
- `tests/backend/test_plan.py`, `tests/backend/test_status.py`, `tests/manifest/test_projection.py`, `tests/manifest/test_drift.py`, `tests/cli/test_backend.py` — encode the current behavior and the migration guardrails.
- `docs/specs/2026-07-14-stabilization-roadmap.md`, `docs/specs/platform/portfolio.json` — portfolio constraints and Unit 3 scope.

### Approaches
1. **Enrich `MaterializedState`** — add root/path/provenance fields so `plan_backend` can make mount decisions directly from the state object.
   - Pros: one state object; the `run` pipeline can keep a single handoff from scan to plan; simple to explain at the call site.
   - Cons: overloads a drift-oriented model with path authority; widens serialization/compatibility surface; pushes filesystem concerns into code that currently only needs repo identity.
   - Effort: Medium/High

2. **Introduce a mount-planning view** — keep `MaterializedState` as identity/commit evidence and derive a separate `MountPlanningState` (or similar) from scan data for `plan_backend`.
   - Pros: clean separation between repo identity drift and filesystem mount authority; preserves identity-only callers and existing drift semantics; clearer failure ownership for absent/incoherent state.
   - Cons: one extra model/transformation; more code paths to test; a little more up-front plumbing.
   - Effort: Medium

### Recommendation
Prefer the **mount-planning view**. The evidence says `MaterializedState` is already doing one job well (identity/commit drift), while the scan layer still owns path/root authority. Mixing both into `MaterializedState` would blur the boundary and make compatibility harder to reason about.

Keep `BackendProvider` unchanged: it already consumes `BackendPlan`, and nothing in the adapter needs to know whether mount authority came from enriched state or a derived planning view. The change belongs in core planning and CLI wiring, not in the provider port.

### Risks
- Silent fallback to static mounts would violate the claim that mounts are authoritative.
- Thin `MaterializedState` cannot represent path/root authority without either schema growth or a separate planning view.
- Partial / stale scans need a product decision or the new planner will either under-provision or fail too aggressively.
- `run` is the only backend path that legitimately depends on workspace scans; identity commands must not regress into scanning again.

### Decision Ledger
**Supported by evidence**
- `plan_backend` currently ignores `MaterializedState` and must be changed for Unit 3.
- `status` / `stop` / `logs` / `exec` should remain state-independent identity operations.
- `BackendProvider` remains the adapter boundary; no provider API change is required by the current evidence.
- `ScanError` is the correct boundary for malformed scan paths.

**Still needing product judgment**
- Whether absent or incomplete materialization blocks `run` or produces a degraded warning.
- Whether stale materialization is a hard error or a warning-only condition.
- Whether the mount authority should be encoded by enriching `MaterializedState` or by introducing a dedicated planning view.
- Whether `worktrees` may be implicitly mounted or only when promoted.

**Non-goals**
- Do not absorb `CHG-FIRST-DATABASE-ADAPTER`.
- Do not absorb `sp-data-environments`.
- Do not change `project`, `unlock`, or `lock` semantics.
- Do not change Docker runtime behavior in the adapter.

**Proposal acceptance criteria**
- `run` and `validate` consume state-derived mount evidence.
- Identity commands keep their empty-state path.
- Mount/path validation errors originate once and are rendered once at the CLI boundary.
- No silent fallback to static mounts.
- `BackendProvider` stays on `BackendPlan` unless a later proposal explicitly justifies a contract change.

### Ready for Proposal
Yes — the proposal can proceed with the mount-planning-view recommendation, but it must still settle the absent/incomplete/stale policy and the exact shape of mount authority.
