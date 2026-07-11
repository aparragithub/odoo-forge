# Proposal: Managed Data Environments

## Intent and Outcome

Developers, QA, and automation need provisioned, cloned, randomized non-production, and pre-production environments. The local Docker backend embeds PostgreSQL; provider-neutral lifecycle, coordinated copy, lineage, and anonymization do not exist. The outcome keeps each environment's database and filestore traceable.

## Scope

### In Scope
- Define the managed-environment outcome and acceptance handoffs.
- Require safe provision, clone, randomize, retry, cleanup, reference, and lineage behavior.
- Integrate delivered prerequisites without absorbing their scope.

### Non-Goals
- Additional provider selection, backup/restore, retention, scheduling, request UI, CI/CD orchestration, onboarding, or production governance.
- Resurrecting historical SP-2 or implementing its provider, adapter, workflow, and control-plane concerns monolithically.

## Product Rules and Safety Defaults

- Database and filestore form one logical environment; partial snapshots or mismatched lineage MUST NOT become usable.
- Non-production data is anonymized by default. Exceptions require actor, reason, source, destination, approval, and durable result evidence.
- Retries are idempotent. Failure removes only invocation-owned targets, preserves sources and pre-existing volumes, and records residual cleanup.
- The control plane stores references and lineage, never database or filestore bytes.

## Capabilities

### New Capabilities
- `managed-data-environments`: safe lifecycle, coherent data/filestore identity, audit evidence, and actor-visible outcomes.

### Modified Capabilities
- None. Prerequisite changes own specification deltas, including any `local-backend` runtime-ownership cutover.

## Dependency and Acceptance Handoffs

Full acceptance requires `CHG-FIRST-DATABASE-ADAPTER`, `WF-DATA-COPY`, and `SP-CONTROL-PLANE-AUTHORITY`. Their gates include `PORT-DATABASE-PROVIDER`, `CAP-CREDENTIALS`, `CAP-DATA-ARTIFACTS`, `INT-DATABASE-RUNTIME-CUTOVER`, `CAP-DURABLE-OPERATIONS`, and `CAP-RESOURCE-OWNERSHIP`. Each handoff must provide approved contracts and acceptance evidence before integration.

`DPROV-DB` is decided: Docker PostgreSQL is the exactly one first database adapter because it reuses the existing tested local backend and minimizes initial delivery risk. This decision resolves adapter selection only; implementation remains blocked until the three prerequisite handoffs above provide accepted evidence.

## Approach and Delivery

Deliver dependency-first, then integrate the outcome. Delivery is forced-chained: one autonomous work unit per PR, tests/docs included, and at most 400 authored changed lines per PR.

## Implications and Edge Cases

Provider-native snapshots versus logical copy affect consistency, portability, anonymization, cost, and testability. Crash recovery must prevent torn audit, cleanup, or lineage commits. Empty sources, partial artifacts, denied exceptions, retries, and unavailable providers must fail closed without exposing targets.

## Unresolved Product Decisions

- First `CAP-DATA-ARTIFACTS` capture/reference contract.
- Anonymization rule ownership/transformations; approval authority/audit store.
- Smallest control-plane handoff for a usable first environment.

## Risks, Rollback, and Success

| Risk | Mitigation |
|---|---|
| Hidden monolith or provider leakage | Enforce gates, capability ownership, and chained review boundaries. |
| Data loss or incoherent copies | Fail closed; preserve sources; bind database, filestore, audit, and lineage. |

Rollback each chain slice independently; disable incomplete integration and retain existing local Docker behavior and data. Success means all handoffs are accepted and users can create policy-compliant environments with coherent lineage, safe compensation, and auditable exceptions.
