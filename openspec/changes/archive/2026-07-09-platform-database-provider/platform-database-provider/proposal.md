# Proposal: Platform Database Provider

## Intent

Provide a lifecycle boundary whose first value flow creates a consistent production-to-QA Odoo database and filestore copy.

## Scope

### In Scope
- Add a runtime-checkable `DatabaseProvider` port, references, lineage, typed errors, and lifecycle policy.
- Deliver one Dockerized PostgreSQL adapter supporting provision, clone, randomize, and drop.
- Coordinate PostgreSQL and Odoo filestore copies; this explicitly expands database-only SP-2 scope to prevent inconsistent targets.
- Require destination-specific anonymization, production-data authorization, and local audit fields: actor, reason, source, destination, result.
- Extract PostgreSQL ownership from the Docker backend while preserving readiness, created-only cleanup, and all pre-existing resources.

### Out of Scope
- AWS RDS/VPS adapters or runtime provider mixing.
- Odoo schema ownership, approval/control-plane workflows, or complete SP-10 audit infrastructure.
- Scheduling, retention, backup orchestration, restore drills, or universal anonymization policy.

## Capabilities

### New Capabilities
- `database-provider-lifecycle`: Dockerized PostgreSQL lifecycle, coordinated database/filestore copies, destination policy, authorization, lineage, and local audit records.

### Modified Capabilities
- `local-backend`: Transfer PostgreSQL provisioning ownership while preserving runtime readiness and named-volume rollback/preservation guarantees.

## Approach

Keep policy and contracts in the pure core; compose one Dockerized PostgreSQL executor in the CLI. Each destination declares anonymization policy. One copy operation coordinates database/filestore creation, validation, cleanup, and reporting. Cleanup removes only invocation-created resources. Delivery is forced through chained PRs within the 400-line review budget.

## Affected Areas

| Area | Impact | Description |
|---|---|---|
| `src/odoo_forge/ports/` | New | Provider contract |
| `src/odoo_forge/backend/plan.py` | Modified | Database ownership seam |
| `src/odoo_forge_docker/provider.py` | Modified | Safe PostgreSQL extraction |
| `src/odoo_forge_cli/main.py` | Modified | Composition and lifecycle CLI |
| `tests/{ports,backend,adapters,cli}/` | New/Modified | Contract and safety coverage |

## Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| Partial database/filestore target | Med | Validate one coordinated operation; never report partial success |
| Preserved data deletion | Med | Track creation ownership and test pre-existing volumes |
| Unsafe production data | Med | Enforce destination policy, authorization, and audit entry |

## Rollback Plan

Revert CLI composition and adapter extraction, restoring Docker backend ownership. Failed copies remove only resources created by that invocation; sources and pre-existing resources remain untouched.

## Dependencies

- Slice 4b local Docker backend and named PostgreSQL/filestore volumes.
- SP-10 for complete audit infrastructure; this change supplies only the local minimum.

## Success Criteria

- [ ] A production-to-QA flow creates a validated database and filestore target with Dockerized PostgreSQL.
- [ ] Every destination has explicit anonymization policy; production data requires authorization and records all five audit fields.
- [ ] Failure cleanup removes only newly created resources; readiness and pre-existing PG/filestore volumes remain verified and preserved.
