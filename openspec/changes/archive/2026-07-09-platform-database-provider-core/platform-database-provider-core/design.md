# Design: Platform Database Provider Core

## Technical Approach

Add frozen core contracts first, then a package-isolated PostgreSQL 16 Docker CLI adapter attached to a runtime-supplied network. It reuses Slice 4b's timeout/readiness patterns but adds recoverable identities, receipt-safe cleanup, artifact-only restore, and credential-file leases. No CLI routing, provider selection, governance, filestore, or copy orchestration changes.

## Architecture Decisions

| Option | Tradeoff | Decision and rationale |
|---|---|---|
| Enrich canonical API | Breaks SP-2 | Preserve all four exact signatures; companions carry receipts/recovery. |
| Unified source request | Could reconnect to production | Keep canonical live-source paths separate from tagged captured-artifact requests. |
| Create networks | Duplicates runtime ownership | `DatabaseSpec.network` is opaque and supplied; core never creates/removes networks. |
| Secrets in env/argv | Observable | Inject `CredentialResolver`; it yields mode-0600 password/pgpass file leases and guarantees unlink. |
| Best-effort rollback | Hides residuals | Deterministic identities plus reconciliation and aggregated typed cleanup failures make every crash window recoverable. |

## Data Flow

```text
live clone ─> pg_dump -Fc ─┐
capture URI ─> digest/format├─> owned target ─> restore TX ─> randomize TX? ─> ready ─> receipt
reconcile(operation ID) ───┘                         failure ─> verified cleanup report
```

## Interfaces / Contracts

```python
@runtime_checkable
class DatabaseProvider(Protocol):
    def provision(self, spec: DatabaseSpec) -> DatabaseRef: ...
    def clone(self, source_ref: DatabaseRef, target_spec: DatabaseSpec) -> DatabaseRef: ...
    def randomize(self, source_ref: DatabaseRef, target_spec: DatabaseSpec,
                  rules: AnonymizationRules) -> DatabaseRef: ...
    def drop(self, ref: DatabaseRef) -> None: ...

class DatabaseCreationProvider(Protocol):
    def provision_created(self, request: ProvisionRequest) -> CreatedDatabase: ...
    def restore_created(self, request: CapturedRestoreRequest) -> CreatedDatabase: ...
    def restore_randomized_created(self, request: CapturedRandomizeRequest) -> CreatedDatabase: ...
    def reconcile_created(self, request: ReconcileRequest) -> CreationReconciliation: ...
    def cleanup_created(self, request: ReceiptCleanupRequest) -> CleanupReport: ...

class CredentialResolver(Protocol):
    def materialize(self, handle: CredentialHandle,
                    purpose: CredentialPurpose) -> ContextManager[CredentialFile]: ...
```

Tagged frozen requests contain `operation_id`, target spec, and only their declared source; canonical calls derive the same identity from `DatabaseSpec.operation_id`. `DatabaseSpec` includes `NetworkAttachment(token)`. `DatabaseCaptureRef(id, uri, media_type="application/vnd.odoo-forge.postgresql-dump", format_version=1, dump_format: custom|plain, sha256, boundary_id)` contains no live connection fields. `ResourceOwnership(kind: created|adopted|external, token?)` appears in refs; receipts repeat created token and operation identity. Cleanup intent is `compensation`; canonical `drop` means deliberate decommission. Labels are `com.odoo-forge.{managed,operation,resource,ownership-token-sha256}`; deletion requires all matches.

Names are `odf-db-{resourceHash}`, `odf-db-{resourceHash}-pgdata`, `odf-db-{operationHash}-init`, and `odf-db-{operationHash}-tool`. Create volume; initialize via the init container using a read-only password-file lease; remove it; start the final container without secret env; wait with `pg_isready`. Tool containers mount pgpass/artifact files read-only on the supplied network. Verify digest before target mutation. Custom dumps dispatch to `pg_restore --single-transaction --exit-on-error`; plain dumps to `psql --single-transaction --set=ON_ERROR_STOP=1`. Randomization is a subsequent ordered, target-only transaction. Receipt timing follows commit and final readiness.

Subprocess calls have bounded timeouts and safe labels (`operation kind`, hashed ID), never request reprs. Stderr is normalized, secret-redacted, then mapped to typed unavailable, artifact, restore, readiness, anonymization, unsafe-drop, or cleanup errors. Rollback/reconciliation inspect labels, remove only token-owned container/volume in reverse order, never the network, and return/raise all teardown failures.

Conformance tests compare `inspect.signature` for each unbound protocol/adapter method, including names, order, annotations, and returns; `isinstance(adapter, Protocol)` separately proves runtime shape.

## File Changes

| File | Action | Description |
|---|---|---|
| `src/odoo_forge/database/{models,errors}.py` | Create | Frozen values, requests, ownership, outcomes. |
| `src/odoo_forge/ports/{database_provider,credential_resolver}.py` | Create | Canonical and companion protocols. |
| `src/odoo_forge_postgres_docker/{__init__,provider,commands}.py` | Create | Docker lifecycle and safe subprocess boundary. |
| `tests/{database,ports}/test_*.py` | Create | Invariants and exact conformance. |
| `tests/adapters/test_postgres_docker_provider{,_integration}.py` | Create | Fake-command and substantive daemon coverage. |
| `pyproject.toml` | Modify | Package/import boundary, marker, and adapter-inclusive coverage. |

## Testing Strategy

Unit tests prove signatures, request separation, command order/dispatch, secret absence and lease cleanup, crash reconciliation, residual reporting, token/label guards, transactions, and redaction. Real Docker proves provision/live clone, artifact-only restore with source unavailable, randomization isolation, mutation-before-return recovery, deliberate/compensation cleanup, and sentinel preservation. Probe `docker info`; skip only with its explicit unavailable reason. Run default and `-m integration`, coverage for both packages, import-linter, mypy, Ruff, and build.

## Migration / Rollout

Forced feature-branch chain; each autonomous slice includes tests and stays below 400 changed lines: (1) values/errors/secrets; (2) protocols/receipts/reconciliation/cleanup; (3) package/commands/coverage, no mutation; (4) provision+recovery; (5) drop+receipt cleanup; (6) live clone; (7) captured restore; (8) randomization; (9) real-Docker matrix. Contracts therefore precede every mutation adapter. No migration or runtime cutover.

## Risks / Open Questions

- PostgreSQL major-version compatibility remains explicit: tooling is pinned to 16 and mismatch is typed. No blocking questions.
