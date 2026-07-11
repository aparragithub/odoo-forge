# Proposal: Platform Database Runtime Integration

## Intent

Extract PostgreSQL ownership from the Docker backend without breaking existing instances or intermediate `forge run/status/stop/logs/exec` releases.

## Scope

### In Scope
- Make `BackendProvider` Odoo-only and add PostgreSQL runtime control consuming provider-core refs, receipts, and errors.
- Route composite commands exactly: run coordinates network→database→Odoo; status merges Odoo and PostgreSQL roles; stop orders Odoo→PostgreSQL→network; logs dispatches by role; exec remains Odoo-only.
- Make the Odoo backend own the pre-start reachability probe, with a configurable default timeout of at least 180 seconds.
- Give the shared-network creator atomic receipts; release only creator-owned networks after both runtimes stop.
- Deterministically adopt legacy Slice 4b resources as `created=False`, preserving absent behavior, naming, and typed CLI errors.
- Close `GATE-016`; deliver runtime `INT-CLI-01` and final CLI handoffs.

### Out of Scope
- Provider-core implementation; governance/audit; DB/filestore capture or copy coordination; copy CLI.
- Compensation, persistence, or coordinated-copy terminal states.

## Capabilities

### New Capabilities
- `database-runtime-integration`: Composite Odoo/PostgreSQL runtime routing, reachability, network ownership, and legacy compatibility.

### Modified Capabilities
- None.

Umbrella reconciliation: this capability delegates the parent `local-backend` ownership and resilient-command requirements, owns `GATE-016`, and contributes only the runtime half of `INT-CLI-01`.

## Approach

Use a forced PR chain, each slice under 400 changed lines: (1) additive runtime/status/error contracts, (2) PostgreSQL runtime and network receipts, (3) composite routing plus legacy adoption, (4) atomic ownership cutover last. Every prior slice keeps current commands operational.

## Affected Areas

| Area | Impact | Description |
|---|---|---|
| `src/odoo_forge/{backend,ports}/` | Modified/New | Odoo-only and composite contracts |
| `src/odoo_forge_docker/provider.py` | Modified | Remove PostgreSQL ownership last |
| `src/odoo_forge_postgres_docker/` | Modified | Runtime operations |
| `src/odoo_forge_cli/main.py` | Modified | Compatible composition/routing |
| `tests/{backend,adapters,cli}/` | Modified/New | Cutover and legacy proof |

## Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| Dual ownership or broken intermediate CLI | High | Additive seams; atomic final cutover |
| Legacy data/network deletion | Med | Deterministic discovery; `created=False` receipts |
| Composite partial stop ambiguity | Med | Ordered typed outcome; release network only after both stops |

## Rollback Plan

Before cutover, revert any additive slice. After cutover, revert the final routing/removal slice together, restoring `DockerBackendProvider` ownership; never delete preserved resources.

## Dependencies and Relationships

- Depends on `platform-database-provider-core` (#6314) and completed Slice 4b.
- Supplies handoffs to `platform-coordinated-data-copy` and final umbrella CLI acceptance; imports neither.

## Success Criteria

- [ ] `GATE-016` proves exact merged status, probe ownership/timeout, and typed errors.
- [ ] Legacy and new instances pass run/status/stop/logs/exec compatibility tests.
- [ ] Every autonomous chained slice stays below 400 changed lines and keeps commands working.
