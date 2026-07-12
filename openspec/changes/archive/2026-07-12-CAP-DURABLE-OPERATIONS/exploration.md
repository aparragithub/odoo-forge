## Exploration: CAP-DURABLE-OPERATIONS

### Current State
`docs/specs/platform/portfolio.json` and the active OpenSpec changes already treat `CAP-DURABLE-OPERATIONS` as a prerequisite capability, not an implementation detail inside one workflow. The portfolio decomposition and archived platform-subproject evidence consistently assign it the same problem space: idempotent operation state, journal/recovery, terminal outcomes, and residual reconciliation.

The strongest current downstream dependency is `openspec/changes/sp-data-environments/`. Its proposal, spec, and design already assume a durable operation identity, monotonic state machine, retry-safe orchestration, authoritative terminal commit, residual cleanup obligations, and idempotent reconciliation before managed data environments can be accepted. The earlier archived coordinated-copy/database-governance work provides historical evidence for the same failure modes: torn terminal commits, post-mutation audit loss, and residual cleanup that is not durably recoverable.

Current code does NOT provide a reusable durable-operations capability. What exists today is fragmented safety evidence:
- `src/odoo_forge/database/types.py` defines `OperationIdentity`, `CreationReceipt`, and `CleanupReport`, but only for database-provider ownership and cleanup semantics.
- `src/odoo_forge/data_artifacts/contracts.py` defines typed restore/discard outcomes, including residual identifiers, but not workflow checkpoints or replay.
- `src/odoo_forge_docker/provider.py` already shows created-only rollback, residual cleanup reporting, and safe retry-friendly resource ownership boundaries.
- `src/odoo_forge_cli/main.py` and `src/odoo_forge_workspace/provider.py` contain atomic file replacement patterns, proving the repo already values crash-safe writes.

Those pieces are useful inputs, but they are NOT a capability contract. There is no generic durable operation record, no operation journal, no checkpoint model, no compare-and-swap terminal commit contract, no recovery/replay protocol, no residual-reconciliation queue, and no observability/evidence schema that multiple workflows can share.

### Affected Areas
- `docs/specs/platform/portfolio.json` — authoritative prerequisite intent and dependency placement.
- `openspec/changes/sp-data-environments/{proposal.md,exploration.md,design.md,specs/managed-data-environments/spec.md}` — active downstream consumer already blocked on this capability.
- `openspec/specs/database-provider/spec.md` — proves operation identity and reconcile semantics already matter at a lower-level provider boundary.
- `src/odoo_forge/database/types.py` — existing ownership/receipt vocabulary that should align with, not replace, the durable-operations contract.
- `src/odoo_forge/data_artifacts/contracts.py` — existing typed residual/failure patterns worth reusing.
- `src/odoo_forge_docker/provider.py` — current rollback/residual behavior and created-only cleanup constraints.
- `src/odoo_forge_cli/main.py` and `src/odoo_forge_workspace/provider.py` — current crash-safe atomic-write patterns that inform persistence expectations.
- Future likely addition: `src/odoo_forge/durable_operations/` plus one or more provider-neutral ports for operation store, recovery, and evidence persistence.

### What Downstream Actually Needs
`CAP-DURABLE-OPERATIONS` must answer these questions before workflow implementation is safe:

1. **Operation identity and idempotency**
   - What stable key defines "the same operation"?
   - How are same-input replay and conflicting-input retry distinguished?

2. **Lifecycle and checkpoints**
   - What monotonic states exist between accepted request, mutation, terminal success/failure, compensation, and cleanup-required?
   - What checkpoint data is durable enough to resume after crash without redoing unsafe mutation?

3. **Terminal commit boundary**
   - How does a workflow atomically publish its authoritative terminal outcome together with required evidence/receipts/cleanup obligations?
   - What compare-and-swap or equivalent revision rule prevents torn visibility?

4. **Recovery and reconciliation**
   - How does restart discover in-flight, unknown-outcome, or cleanup-required operations?
   - What does `reconcile(operation_id)` mean at workflow level versus provider level?

5. **Ownership and compensation handoff**
   - How are invocation-owned receipts attached so compensation deletes only owned targets?
   - How are residual cleanup obligations persisted when cleanup cannot complete now?

6. **Observability and durable evidence**
   - Which events/outcomes must be durably queryable for audit, debugging, and retry decisions?
   - What redaction rules apply so evidence never contains secrets or data bytes?

### Approaches
1. **Capability-first durable operation contract** — define a provider-neutral lifecycle, checkpoint, terminal-commit, and reconciliation contract before any consumer-specific orchestration.
   - Pros: Matches the portfolio, keeps the capability reusable, and unblocks `sp-data-environments`, `WF-DATA-COPY`, and future workflow consumers without coupling them to one store or adapter.
   - Cons: Requires disciplined scoping so it does not absorb control-plane business policy or specific workflow semantics.
   - Effort: Medium.

2. **Let each workflow own its own durability model** — `sp-data-environments`, copy workflows, and lifecycle automation each invent local retry/recovery logic.
   - Pros: Faster for the first slice only.
   - Cons: Duplicates failure handling, makes cross-workflow evidence incoherent, and directly defeats the point of the prerequisite capability.
   - Effort: High with high rework risk.

3. **Control-plane-first durable implementation** — start by designing a specific persistent store/outbox/transaction model and let the capability be whatever that store supports.
   - Pros: Concrete and implementation-shaped.
   - Cons: Prematurely couples the contract to one authority/persistence choice while `SP-CONTROL-PLANE-AUTHORITY` is still a separate prerequisite track.
   - Effort: High.

### Recommendation
Use **capability-first durable operation contract**.

The next phase should frame `CAP-DURABLE-OPERATIONS` as the minimal reusable contract that lets long-running or crash-sensitive workflows prove these guarantees:
- retries are idempotent;
- states are monotonic and recoverable;
- terminal success/failure is durably recorded with required evidence;
- only invocation-owned resources are compensated;
- incomplete cleanup becomes durable residual work rather than silent loss; and
- hidden/incomplete work never becomes authoritative visibility.

The proposal should define the contract, not prematurely choose the final persistence implementation. It should likely introduce:
- an immutable operation identity/idempotency key rule;
- a capability-owned workflow state model;
- a checkpoint/receipt bundle model;
- a terminal compare-and-swap or equivalent commit contract;
- recovery/reconciliation semantics for unknown outcomes and residual cleanup; and
- typed, redacted observability/evidence outputs.

The proposal should explicitly exclude:
- database-provider specifics beyond contract alignment;
- anonymization or approval business rules;
- control-plane product/API scope beyond the durable contract it must later satisfy; and
- scheduling/retention policy that belongs to resource lifecycle or recovery outcomes.

### Constraints, Edge Cases, and Open Questions
- Same operation ID with different request digest must fail as a conflict, not replay as success.
- Unknown commit outcome after mutation must reconcile to exactly one terminal result.
- Cleanup failure must persist durable residual obligations; logging alone is not enough.
- Evidence must remain redacted: no secret material, connection text, or data bytes in durable records.
- The contract must support consumers whose mutations happen before the authoritative terminal commit is possible.
- Provider-level `reconcile(OperationIdentity)` already exists; the proposal must distinguish provider recovery from workflow-level recovery so the two layers compose cleanly.
- `sp-data-environments` already assumes a transactional `commit_usable(...)`-style boundary. This capability must define the generic contract that assumption rests on, without forcing the entire control-plane implementation into this change.

### Risks
- If the capability is underspecified, each workflow will rebuild its own retry/recovery logic and drift immediately.
- If it is overspecified around one persistence adapter, it will pre-own control-plane implementation decisions that belong elsewhere.
- If terminal commit and evidence durability are separate concerns, crash windows can still expose torn authoritative state.
- If residual cleanup is not first-class durable state, failed compensation becomes invisible operational debt.
- If provider-level and workflow-level reconciliation are conflated, consumers may retry unsafe mutations or lose authoritative outcomes.

### Ready for Proposal
Yes. The repo already has enough authoritative context to justify the need, scope boundary, downstream consumers, and main architectural decision. The proposal is ready as long as it stays capability-first: define lifecycle, idempotency, checkpoints, terminal commit, recovery, ownership handoff, and durable evidence as reusable contracts before choosing workflow-specific implementation details.
