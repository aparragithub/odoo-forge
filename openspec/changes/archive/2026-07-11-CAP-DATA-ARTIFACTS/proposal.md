# Proposal: CAP-DATA-ARTIFACTS

Define the prerequisite contract for data artifacts so downstream restore and managed-environment work can consume one accepted, opaque artifact reference without inventing incompatible integrity or coherence rules.

## Intent

`CAP-DATA-ARTIFACTS` exists to close a contract gap. The database-provider contract already requires `restore(DatabaseSpec, DataArtifactRef, CredentialHandle)`, and managed data environments already require database+filestore coherence with ref-only control-plane storage. Today the repository has only an opaque placeholder type and no accepted artifact capability that defines what the reference means, how integrity is checked, how database and filestore stay coherent, or how discard works.

This change proposes the missing prerequisite contract only. It does not implement adapters, workflow orchestration, anonymization policy, or control-plane ownership.

## Problem

Without a capability-owned artifact contract:

- `DatabaseProvider.restore(...)` can accept a `DataArtifactRef`, but no accepted rule explains what that reference identifies.
- Managed environments require coherent database+filestore behavior, but no prerequisite defines the consistency boundary that makes that outcome safe.
- Consumers would be forced to invent their own checksum, validation, availability, and cleanup semantics, breaking the portfolio dependency model and making downstream acceptance unverifiable.

## Scope

This proposal covers the prerequisite contract for:

- opaque `DataArtifactRef` semantics;
- capability-owned integrity metadata and pre-mutation validation outcomes;
- the coherence model that binds database and filestore capture artifacts into one usable restore input boundary;
- lifecycle handoff semantics for validation, availability, and discard;
- typed, redacted failure outcomes and readiness evidence for `AC-CAP-DATA-ARTIFACTS-READY`.

## Boundaries

This proposal explicitly excludes:

- database adapter implementation or restore execution details;
- artifact byte transport or storage implementation;
- credential materialization or secret-bearing values;
- anonymization transformations, approvals, or policy ownership;
- control-plane ownership beyond ref-only handoff compatibility;
- workflow or copy orchestration beyond the artifact contract later consumers will use.

## Affected Areas

- `openspec/changes/CAP-DATA-ARTIFACTS/` — new prerequisite artifact set.
- `openspec/specs/database-provider/spec.md` — downstream consumer that already depends on exactly one opaque `DataArtifactRef` in restore.
- `openspec/changes/sp-data-environments/specs/managed-data-environments/spec.md` — downstream outcome that requires coherent database+filestore behavior and ref-only control-plane storage.
- `docs/specs/platform/portfolio.json` — authoritative dependency path from this capability into `CHG-FIRST-DATABASE-ADAPTER`.
- `src/odoo_forge/data_artifacts/` — current placeholder-only capability surface to be specified later.

## Proposal

The platform should adopt a contract-first data-artifact capability that standardizes how consumers name, validate, relate, and discard restore inputs while keeping references opaque and policy-neutral.

The normative contract should require that:

1. A `DataArtifactRef` is an opaque external identifier suitable for provider restore and lineage storage, without embedding bytes, secrets, hostnames, or live-source connection details.
2. Artifact integrity is capability-owned, including identity metadata, checksum or digest rules, version or format markers, and typed validation results.
3. Validation happens before restore-side mutation. If integrity, availability, or coherence cannot be proven, restore consumers fail closed.
4. Database and filestore captures participate in one capability-defined coherence boundary so downstream consumers can reason about a usable environment instead of isolated components.
5. Discard and residual-failure semantics are explicit, typed, and redacted so downstream cleanup authority is clear without leaking sensitive details.

## Unresolved Architectural Choice

The specification phase must resolve one architectural choice without violating accepted downstream contracts:

- whether the single `DataArtifactRef` consumed by `DatabaseProvider.restore(...)` identifies a composite environment capture directly; or
- whether it identifies one opaque artifact handle that resolves, within the capability boundary, to a coherence group covering both database and filestore.

Whichever option is chosen must preserve both existing truths:

- the provider contract continues to consume exactly one opaque `DataArtifactRef`; and
- managed data environments continue to require database+filestore coherence before a target is usable.

## Acceptance Intent

This proposal is complete when follow-on specification and verification can prove that:

- one accepted capability contract defines what `DataArtifactRef` means for downstream consumers;
- integrity and availability can be checked before any restore mutation occurs;
- database and filestore coherence is represented explicitly enough to block partial or mismatched restore inputs;
- discard and failure semantics are capability-owned and redacted;
- downstream work (`CHG-FIRST-DATABASE-ADAPTER`, managed data environments) can depend on this capability without redefining artifact semantics.

## Risks

- If the contract is database-only, downstream environments may restore unusable targets because filestore coherence remains undefined.
- If refs carry bytes or live-source details, the contract breaks accepted opaque-reference boundaries.
- If validation occurs after mutation, restore safety fails.
- If this capability absorbs adapter, anonymization, control-plane, or orchestration concerns, prerequisite scope will blur and downstream ownership will regress.

## Rollback

Because this phase is proposal-only, rollback is limited to superseding or replacing the proposal before acceptance. No runtime behavior, state ownership, or downstream contract implementation changes are introduced by this artifact alone.

## Success Criteria

- Proposal scope remains prerequisite-only and contract-first.
- Downstream dependencies and exclusions are explicit and consistent with accepted specs.
- The single unresolved architectural choice is named clearly enough for the spec/design phases to settle without reopening scope.
- The proposal gives a clean acceptance target for `AC-CAP-DATA-ARTIFACTS-READY` without absorbing implementation work.
