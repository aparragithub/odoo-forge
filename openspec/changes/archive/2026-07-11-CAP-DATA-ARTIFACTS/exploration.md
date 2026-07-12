## Exploration: CAP-DATA-ARTIFACTS

### Current State
`docs/specs/platform/portfolio.json` is the authoritative planning source. The current portfolio decomposition already treats `CAP-DATA-ARTIFACTS` as an independent prerequisite and describes its ownership at a high level: database/filestore capture refs, checksums, consistency boundary, validation, and discard. Prevalidated portfolio context and downstream OpenSpec artifacts confirm that `AC-CAP-DATA-ARTIFACTS-READY` is still missing and that no active OpenSpec change existed for this capability before this exploration.

Two accepted downstream contracts already depend on this capability without defining it. `openspec/specs/database-provider/spec.md` requires `DatabaseProvider.restore(DatabaseSpec, DataArtifactRef, CredentialHandle) -> DatabaseCreation` and explicitly keeps artifact inputs opaque. `openspec/changes/sp-data-environments/specs/managed-data-environments/spec.md` requires database and filestore to behave as one logical environment, stores only references/lineage in the control plane, and blocks outcome acceptance until approved evidence exists for `CAP-DATA-ARTIFACTS` through `CHG-FIRST-DATABASE-ADAPTER` and other handoffs.

Current code only contains the placeholder type `src/odoo_forge/data_artifacts/types.py:5` (`DataArtifactRef = NewType("DataArtifactRef", str)`) plus its re-export. There is no accepted artifact contract, no capture model, no checksum/digest schema, no validation/discard boundary, no capability API for resolving artifact refs, and no implementation for database/filestore consistency. The local Docker backend preserves named Postgres and filestore volumes and provides useful safety evidence, but it does not expose a reusable artifact capability.

### Affected Areas
- `docs/specs/platform/portfolio.json` — authoritative scope, gate, and downstream dependency intent.
- `openspec/specs/database-provider/spec.md` — accepted consumer that already requires opaque `DataArtifactRef` restore input.
- `openspec/changes/CHG-FIRST-DATABASE-ADAPTER/exploration.md` — explicitly blocked until this capability defines the artifact/reference and consistency contract.
- `openspec/changes/sp-data-environments/specs/managed-data-environments/spec.md` and `design.md` — require coherent database+filestore lineage and keep bytes out of control-plane state.
- `src/odoo_forge/data_artifacts/` — currently only the opaque ref placeholder exists.
- `openspec/specs/local-backend/spec.md` and `src/odoo_forge_docker/provider.py` — evidence of today’s database/filestore runtime shape and preservation constraints, but not the capability contract.
- Archived `platform-database-provider-core` artifacts — non-authoritative evidence only; useful for risk discovery, not for copying requirements.

### What Contract Downstream Actually Needs
`CHG-FIRST-DATABASE-ADAPTER` and later `sp-data-environments` need a capability-owned contract that answers these questions explicitly:

1. **What a `DataArtifactRef` points to**
   - Opaque external identifier only; no bytes, credentials, hostnames, or live-source connection details in provider values.
   - Stable enough for provider restore, workflow lineage, and control-plane reference storage.

2. **How integrity is proven before mutation**
   - Artifact identity, checksum/digest rules, format/version metadata, and typed validation outcomes.
   - Restore consumers must be able to fail closed before mutating a target when validation fails or the artifact is unavailable.

3. **How consistency/coherence is represented**
   - The capability must define the shared consistency boundary that keeps database and filestore captures logically aligned.
   - This is mandatory because `sp-data-environments` forbids exposing partial or mismatched database/filestore copies.

4. **What lifecycle exists around the artifact**
   - Capture handoff semantics, validation/verification semantics, discard semantics, and typed redacted failures.
   - Downstream consumers need to know what is guaranteed to exist at restore time and what cleanup/discard authority means.

5. **How the opaque ref interacts with other owners**
   - Database providers consume refs but do not define artifact internals.
   - Control-plane state stores refs/lineage only, never bytes.
   - Anonymization policy and approval authority must stay outside this capability unless the portfolio explicitly reassigns them.

### Main Design Tension To Resolve In Proposal
There is one important architecture choice the proposal must settle: whether the single accepted `DataArtifactRef` used by `DatabaseProvider.restore(...)` names a composite environment capture or a component artifact that participates in a shared consistency group. Either answer can work, but the proposal MUST preserve both existing truths:
- the provider contract already accepts exactly one opaque `DataArtifactRef`; and
- managed environments require database and filestore coherence, not database-only success.

That choice is proposal material, not a reason to block the proposal entirely.

### Approaches
1. **Contract-first coherent artifact capability** — define the minimal capability contract for opaque refs, integrity metadata, consistency grouping, validation, discard, and typed failures, while keeping bytes and policy ownership outside consumers.
   - Pros: Unblocks the adapter and preserves the portfolio decomposition.
   - Cons: Requires careful scoping so it does not absorb copy orchestration, anonymization, or control-plane ownership.
   - Effort: Medium.

2. **Let each consumer define its own artifact semantics** — database adapter, copy workflow, and control plane each decide how refs/checksums/consistency work.
   - Pros: Lower short-term coordination.
   - Cons: Directly contradicts the prerequisite model and would make coherence/integrity unverifiable across consumers.
   - Effort: High, with high rework risk.

3. **Rehydrate archived provider-core artifact definitions as-is** — promote the archived database-capture contract directly into this capability.
   - Pros: Fastest path to a detailed draft.
   - Cons: Those artifacts are superseded, bundled with other ownership concerns, and were never accepted or verified.
   - Effort: Medium, with high authority risk.

### Recommendation
Use **contract-first coherent artifact capability**. Frame `CAP-DATA-ARTIFACTS` as the missing prerequisite that standardizes how the platform names, validates, relates, and discards database/filestore capture artifacts without exposing bytes through provider or control-plane contracts. Keep the proposal limited to the capability boundary and its acceptance evidence.

The proposal should explicitly define:
- the opaque external reference rule;
- capability-owned integrity metadata and validation outcomes;
- the consistency/coherence model that binds database and filestore captures;
- discard authority and failure semantics; and
- the readiness evidence required for `AC-CAP-DATA-ARTIFACTS-READY`.

The proposal should explicitly exclude:
- database adapter implementation details;
- credential materialization;
- anonymization transformations/policy decisions;
- control-plane persistence ownership beyond ref-only handoff requirements; and
- coordinated copy orchestration beyond the artifact contract it will later consume.

### Risks
- If the contract is database-only, `sp-data-environments` can still produce unusable Odoo targets because filestore coherence would remain undefined.
- If the capability embeds live-source connection details or bytes in refs/values, it breaks the accepted opaque-reference direction.
- If archived artifact shapes are copied wholesale, the change will silently reintroduce superseded ownership and workflow assumptions.
- If validation happens after restore-side mutation instead of before it, artifact-backed restore becomes unsafe.
- If discard authority is vague, downstream cleanup can delete retained evidence or preserve unusable garbage indefinitely.

### Ready for Proposal
Yes — if the proposal is explicitly contract-first and stays within the prerequisite boundary. The repository already has enough authority to justify the problem, downstream consumers, scope boundaries, and the core architectural question around single-ref restore versus environment-level coherence. What is still missing is the normative contract itself, which is exactly what the proposal phase should define.