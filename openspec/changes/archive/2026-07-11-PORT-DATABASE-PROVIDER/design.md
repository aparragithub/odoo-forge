# Design: Provider-Neutral Database Provider Port

## Technical Approach

Add a pure-core `DatabaseProvider` protocol and an `odoo_forge.database` package containing immutable values and redacted failures. The port has no adapter imports or side effects. Conformance tests provide required evidence; portfolio evidence is recorded only after verification.

**Review boundary:** this design covers only the X7 provider contract. Docker behavior, credential/artifact implementations, runtime cutover, policy, coordinated copy, CLI, and managed environments are excluded.

## Architecture Decisions

| Decision | Choice | Alternative / tradeoff | Rationale |
|---|---|---|---|
| Port shape | `@runtime_checkable Protocol` in `odoo_forge.ports` | ABC registration adds nominal coupling | Matches every current provider port and keeps adapters structurally independent. |
| Value model | Frozen Pydantic v2 models plus `str, Enum` for ownership | Mutable `BaseModel` matches older backend values but violates this contract | Pydantic is already a core dependency; `ConfigDict(frozen=True, extra="forbid")` makes immutability and secret-bearing extras testable. |
| Cross-capability inputs | Declare `CredentialHandle` in `odoo_forge.credentials.types` and `DataArtifactRef` in `odoo_forge.data_artifacts.types` as opaque `NewType` references | Defining them in `odoo_forge.database` would make the provider own adjacent capabilities | Capability-owned paths preserve G15/G16. This adds declarations, not resolution, materialization, storage, or payload access. |
| Python signatures | Required parameters are positional-or-keyword, have no defaults, and use the neutral names shown below | Positional-only parameters are atypical for current ports; keyword-only parameters add a constraint absent from the spec | This follows existing provider style while making `inspect.signature` expectations deterministic. |
| Ownership authority | Destructive methods require `CreationReceipt`; adopted/external refs never acquire creator proof | Trusting `DatabaseRef` alone permits unsafe deletion | Makes authority explicit and enables negative conformance evidence. |
| Failures | One `DatabaseProviderError` family with typed subclasses and sanitized public fields | Free-form adapter exceptions can leak provider details or secrets | Callers can classify failures without adapter knowledge; redaction is enforceable. |
| Delivery | Force-chained, contract-first slices under 400 authored changed lines | One PR increases review load | Slice values/errors, then protocol/conformance, then gate evidence; each slice remains independently testable. |

## Data Flow

```text
provider-owned request + opaque handles + operation identity
                         │
                         ▼
                  DatabaseProvider
          ┌──────────────┼──────────────┐
          ▼              ▼              ▼
 DatabaseCreation   DatabaseRef    CleanupReport
 (ref + receipt)    (no secrets)   (all residuals)
```

`reconcile` uses operation identity to recover mutation-before-return. `delete` and `cleanup` validate receipt authority before any destructive adapter action. This change defines those obligations but performs no action itself.

## File Changes

| File | Action | Description |
|---|---|---|
| `src/odoo_forge/database/types.py` | Create | Frozen provider values, ownership enum, and operation identity. |
| `src/odoo_forge/database/errors.py` | Create | Typed, redacted failure family. |
| `src/odoo_forge/database/__init__.py` | Create | Explicit public re-exports. |
| `src/odoo_forge/credentials/types.py` | Create | Capability-owned opaque `CredentialHandle` declaration only. |
| `src/odoo_forge/credentials/__init__.py` | Create | Re-export the credential handle. |
| `src/odoo_forge/data_artifacts/types.py` | Create | Capability-owned opaque `DataArtifactRef` declaration only. |
| `src/odoo_forge/data_artifacts/__init__.py` | Create | Re-export the artifact reference. |
| `src/odoo_forge/ports/database_provider.py` | Create | Six-operation structural port with type-only domain imports. |
| `tests/database/test_types.py` | Create | Immutability, composition, ownership, and forbidden-content invariants. |
| `tests/database/test_errors.py` | Create | Taxonomy and redaction evidence. |
| `tests/ports/test_database_provider.py` | Create | Runtime shape, exact signatures, and ownership-safe fake-provider conformance. |
| `docs/specs/platform/portfolio.json` | Modify later | Attach approved artifact and verification receipt IDs; clear G3 only after acceptance. |

## Interfaces / Contracts

The protocol implements the specification's type-level signatures with these Python declarations:

```python
def provision(self, spec: DatabaseSpec, credentials: CredentialHandle) -> DatabaseCreation: ...
def restore(self, spec: DatabaseSpec, artifact: DataArtifactRef,
            credentials: CredentialHandle) -> DatabaseCreation: ...
def adopt(self, ref: DatabaseRef) -> DatabaseRef: ...
def reconcile(self, operation: OperationIdentity) -> DatabaseCreation: ...
def delete(self, creation: DatabaseCreation) -> None: ...
def cleanup(self, receipt: CreationReceipt) -> CleanupReport: ...
```

Every parameter is required and positional-or-keyword. The port imports provider values from `odoo_forge.database.types`, `CredentialHandle` from `odoo_forge.credentials.types`, and `DataArtifactRef` from `odoo_forge.data_artifacts.types`. `DatabaseCreation` contains `DatabaseRef` and `CreationReceipt`; provider values contain identifiers and metadata only—never secrets or artifact bytes.

## Testing Strategy

| Layer | What to test | Approach |
|---|---|---|
| Unit | Frozen/extra-forbidden values, composition, ownership enum, redaction | Pytest construction, mutation, serialization, and hostile sensitive-input cases. |
| Contract | Six methods, exact names/kinds/defaults/annotations/returns via `inspect.signature`, structural acceptance/rejection, guarded cleanup | Compare each fake-provider signature to the protocol declaration; no Docker, subprocess, credential, or artifact implementation. |
| Architecture | Pure-core isolation | `uv run lint-imports`, mypy, and assertions that port modules import no adapter. |
| E2E | None | No runtime integration exists in X7 scope. |

## Threat Matrix

N/A — no routing, shell, subprocess, VCS/PR automation, executable-file classification, or process-integration boundary.

## Migration / Rollout

No runtime or data migration. Deliver additive chained slices; record gate evidence only after verification succeeds.

## Open Questions

None.
