# Design: Platform Database Provider

## Technical Approach

Keep policy, immutable references, orchestration, and errors in `odoo_forge`; add a dumb `odoo_forge_postgres_docker` adapter. Preserve canonical SP-2 `DatabaseProvider` signatures and use companion ports for consistency, atomic creation ownership, runtime control, durable audit, and transactional persistence. Existing Git `SourceProvider` remains untouched.

## Architecture Decisions

| Option | Tradeoff | Decision and rationale |
|---|---|---|
| Enrich `DatabaseProvider` | Breaks canonical signature tests | Keep its four methods exact; companions expose richer outcomes. |
| Inventory preflight | Races creation | Creators atomically return receipts from the creation primitive. |
| Caller policy | Permits unsafe choices | Pure-core classification and destination mapping choose policy. |
| Separate save/bind | Leaves torn state | One locked atomic repository transaction writes both. |

## Interfaces / Contracts

Frozen models include `ConsistencyBoundary(id)`, `QuiesceLease(id, source, boundary)`, captures carrying that boundary, `CreationReceipt(kind, resource_id, operation_id, created)`, `CreatedDatabase(ref, receipt)`, `CreatedFilestore(ref, receipt)`, `CreatedNetwork(attachment, receipt)`, `LegacyDiscovery(database, filestore, network, odoo_container)`, and `LegacyAdoption(aggregate, instance)`. Capture implementations MUST derive their output boundary from the supplied lease; callers cannot supply or synthesize boundary IDs.

```python
class DatabaseProvider(Protocol):
    def provision(self, spec: DatabaseSpec) -> DatabaseRef: ...
    def clone(self, source_ref: DatabaseRef, target_spec: DatabaseSpec) -> DatabaseRef: ...
    def randomize(self, source_ref: DatabaseRef, target_spec: DatabaseSpec,
                  rules: AnonymizationRules) -> DatabaseRef: ...
    def drop(self, ref: DatabaseRef) -> None: ...

class DataConsistencyProvider(Protocol):
    def quiesce(self, source: DataSourceRef) -> QuiesceLease: ...
    def resume(self, lease: QuiesceLease) -> None: ...
class DatabaseCaptureProvider(Protocol):
    def capture(self, ref: DatabaseRef, lease: QuiesceLease) -> DatabaseCaptureRef: ...
class FilestoreProvider(Protocol):
    def capture(self, ref: FilestoreRef, lease: QuiesceLease) -> FilestoreArchiveRef: ...
    def restore_created(self, archive: FilestoreArchiveRef,
                        target: FilestoreSpec, operation_id: str) -> CreatedFilestore: ...
    def drop(self, ref: FilestoreRef) -> None: ...
class DatabaseCreationProvider(Protocol):
    def provision_created(self, spec: DatabaseSpec, operation_id: str) -> CreatedDatabase: ...
    def clone_created(self, source: DatabaseRef, spec: DatabaseSpec,
                      operation_id: str) -> CreatedDatabase: ...
    def randomize_created(self, source: DatabaseRef, spec: DatabaseSpec,
                          rules: AnonymizationRules, operation_id: str) -> CreatedDatabase: ...
class DatabaseRuntimeProvider(Protocol):
    def status(self, ref: DatabaseRef) -> RoleStatus: ...
    def stop(self, ref: DatabaseRef) -> None: ...
    def logs(self, ref: DatabaseRef) -> str: ...
class NetworkProvider(Protocol):
    def ensure(self, attachment: NetworkAttachment, operation_id: str) -> CreatedNetwork: ...
    def release(self, attachment: NetworkAttachment) -> None: ...
class DataAggregateRepository(Protocol):
    def commit_bound(self, value: DataAggregate, instance: InstanceKey) -> None: ...
    def get(self, aggregate_id: str) -> DataAggregate: ...
    def resolve(self, instance: InstanceKey) -> str | None: ...
class AuditProvider(Protocol):
    def append_durable(self, record: AuditRecord) -> None: ...
class LegacyRuntimeBridge(Protocol):
    def discover(self, instance: InstanceKey) -> LegacyDiscovery | None: ...
    def adopt(self, instance: InstanceKey, discovery: LegacyDiscovery) -> LegacyAdoption: ...
```

Each creation companion and canonical method share one adapter primitive; only the creator decides `created` and returns the receipt with the ref. No `ResourceInventory` participates. Receipt ownership dispatches cleanup: DB→`DatabaseProvider.drop`, filestore→`FilestoreProvider.drop`, network→`NetworkProvider.release`; only `created=True` is removed.

`Destination` is `dev|qa|preprod`. Pure `classify_source(source, lineage)` returns `production_derived|non_production`; `resolve_policy(destination)` is canonical: dev→required randomization/no bypass, qa→anonymize-by-default/audited bypass, preprod→anonymize-by-default/audited bypass. `CopySpec` contains `destination`, never a policy. Production-derived data is anonymized unless the destination permits bypass and `authorization_ref`, actor, and reason are present; a durable authorization-intent audit precedes mutation.

`commit_bound` acquires one exclusive lock, validates version/conflicts, writes aggregate plus binding to one temporary state document, flushes+fsyncs, atomically replaces, then fsyncs the parent directory; it raises typed `RepositoryTransactionError` and leaves the prior document intact. Legacy adoption uses this same operation.

`append_durable` returns only after append, flush, and fsync; failure raises `AuditDurabilityError`. Authorization denial, start, result, and cleanup residual records are fail-closed: pre-mutation failure blocks work; post-mutation failure triggers compensation.

## Normative Flow and Runtime Semantics

```text
classify/resolve/authorize -> audit-start -> quiesce(lease+boundary)
 -> DB capture(lease) -> filestore capture(lease) -> resume
 -> NetworkProvider.ensure -> DB create+receipt -> filestore restore+receipt
 -> validate same boundary -> commit_bound -> audit-result
```

Compensation is filestore, DB, network, then capture discard. On success the aggregate retains receipts. `BackendProvider` keeps current `run/status/stop/logs/exec` shapes but controls Odoo only; `DatabaseRuntimeProvider` controls PostgreSQL. Resolution with no binding discovers legacy resources: `None` makes status return both roles `RoleStatus(False,"exited",False)`, while stop/logs raise `InstanceNotFoundError`. Conflicts raise `LegacyAdoptionError`; adoption is mutation-free and commits receipts as `created=False`.

`RuntimeCoordinator.stop` orders Odoo stop, PostgreSQL stop, then network release. It stops at the first failure and raises `CompositeStopError(completed, failed, cause)`; partial success is explicit. It is the sole successful-stop network releaser and releases only a `created=True` network after both stops. Copy compensation is the only other release path and runs only after filestore/DB cleanup; failed or legacy/pre-existing networks remain.

## Files and Testing

Create `src/odoo_forge/database/*`, named companion ports, `src/odoo_forge_postgres_docker/*`, and CLI JSON/audit adapters; modify backend plan/status/port, `odoo_forge_docker`, and CLI routing. `pyproject.toml` MUST add `src/odoo_forge_postgres_docker` to Hatch wheel `packages`, `odoo_forge_postgres_docker` to import-linter `root_packages`, and a forbidden `odoo_forge`→`odoo_forge_postgres_docker` contract.

Unit-test policy, boundaries, receipts, repository crash/lock behavior, audit durability, absence, adoption, and stop failures; integration-test Docker copy/cleanup; test CLI, signature/runtime conformance, import-linter, mypy, Ruff, and build.

## Migration / Rollout

Land additive contracts/adapters, coordinator/persistence, legacy adoption, and atomic CLI routing before removing backend PostgreSQL ownership. No data deletion or format migration.

## Open Questions

None.
