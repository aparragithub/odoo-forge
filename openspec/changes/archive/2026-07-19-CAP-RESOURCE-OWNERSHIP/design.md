# Design: CAP-RESOURCE-OWNERSHIP

## Technical Approach

Keep `CAP-RESOURCE-OWNERSHIP` contract-first, provider-neutral, and prerequisite-only, matching the `CAP-TENANCY` / `CAP-DURABLE-OPERATIONS` precedent.

This change defines one normative platform contract for resource ownership:
- the provider-neutral ownership state model (`created` / `adopted` / `external`, generalized to arbitrary resource kinds; no new states),
- the ownership receipt / evidence shape (opaque operation proof + owned resource ids + live-proof expectation),
- tenant attribution as composition with `CAP-TENANCY` (optional, non-mandatory at ownership time),
- operation-identity composition with `CAP-DURABLE-OPERATIONS` (reuse, never duplicate), and
- the `PORT-RESOURCE-OWNERSHIP` read/attest surface.

It authors NO control-plane authority service, NO lifecycle/retention/reclamation, NO workflow logic, and does NOT rewrite the Docker `LocalOwnershipAuthority` / `provider.py`. The existing `ResourceOwnership` enum is the anchor: its identity and values are preserved and it remains reachable from `database.types` via a re-export shim — only its canonical definition site moves up into the capability. Per portfolio decision `DG`, this stays an independent enabler, not an umbrella merge.

**Review boundary:** verify the contract, the composition at type level, the port signatures, and the readiness gate `AC-CAP-RESOURCE-OWNERSHIP-READY`. Port and value-type code are authored in follow-up implementation slices that consume this design.

## Architecture Decisions

| Decision | Choice | Rejected alternative | Rationale |
|---|---|---|---|
| Canonical home of generalized vocabulary | New core package `src/odoo_forge/resource_ownership/` (`types.py`, `__init__.py`), mirroring the `durable_operations/` precedent | Extend `database/types.py` in place | Ownership is now a platform capability, not a database-domain concern; a dedicated pure-core package keeps it provider-neutral and resource-kind-agnostic. |
| Relationship to existing `ResourceOwnership` / `CreationReceipt` / `OperationIdentity` | **Move + re-export**: the canonical definitions relocate to `resource_ownership/types.py`; `database/types.py` re-exports those names for backward compatibility | (a) Re-export upward from `database.types` (general depends on specific); (b) define parallel duplicate types | This makes the dependency arrow `database` → `resource_ownership` — the correct hexagonal direction (specific depends on general). It is a compatible change: type identity and behavior are preserved, and every existing importer (the 28+ callers, the Docker `LocalOwnershipAuthority` / `provider.py`) keeps working UNCHANGED through the same `database.types` import paths. The re-export shim satisfies the proposal's "align only" intent because the only new thing is where the canonical definition physically lives. No import-linter exception is needed. Duplicating types would create two competing ownership models — exactly what the capability forbids. |
| State model | Exactly `created` / `adopted` / `external`, reusing the existing `ResourceOwnership` StrEnum, generalized to platform scope | Add `reserved` / `pending` implied by the Docker reserve/bind/activate/retire lifecycle | Confirmed binding decision; adapter lifecycle stays an adapter concern. |
| Resource identity | Generalize `DatabaseRef` into a `ResourceRef` (opaque `identifier` + `resource_kind` + `ownership`) that carries kind so databases, containers, registry entries, and future targets share one shape | Keep ownership DB-only; let each downstream kind define its own ref | Portfolio transfers `X20`–`X23` reclassified adoption/deletion/orphan scopes to capability level. |
| Tenant attribution | Optional `tenant_id: str \| None` composed alongside ownership state; `external` / pre-tenancy resources stay unattributed until adopted | Mandatory tenant link at ownership time | Confirmed binding decision; composes with, does not replace, `created` / `adopted` / `external`. |
| Operation identity | Compose the receipt with `CAP-DURABLE-OPERATIONS`' stable identity `DurableOperationIdentity{operation_id, request_digest}` (from `src/odoo_forge/durable_operations/types.py`) — reuse that exact type, never the legacy `OperationIdentity{value: str}` | Re-author operation identity here, or reuse the legacy `OperationIdentity` | `CAP-DURABLE-OPERATIONS` owns identity; compose only. The legacy `OperationIdentity` is a database-domain token type and MUST NOT stand in for durable-ops identity in the ownership receipt. |
| Port surface v1 | Read/attest only: `describe_ownership` + `attest_ownership`. Transition verbs described, deferred | Include reserve/bind/activate/retire/adopt verbs | Confirmed binding decision; verbs bleed toward `SP-CONTROL-PLANE-AUTHORITY`. |
| Live-proof | Receipt declares a live-proof *expectation*; the mechanism (Docker labels, signed evidence, remote attestation) is an adapter concern | Bake label semantics into the contract | Confirmed binding decision; keeps the contract provider-neutral. |

## Conceptual Model

```text
ResourceRef                         OwnershipReceipt
  identifier (opaque)                 operation: DurableOperationIdentity  (CAP-DURABLE-OPERATIONS)
  resource_kind (db|container|...)    owned_resource_ids: tuple[str, ...]
  ownership: created|adopted|external live_proof_expected: bool

OwnershipRecord = ResourceRef + TenantAttribution(tenant_id?: str|None) + receipt?
  -> describe_ownership: current state + attribution (READ)
  -> attest_ownership:   receipt proves ownership now (ATTEST, no mutation)
```

## Interfaces / Contracts

`src/odoo_forge/ports/resource_ownership.py` (follow-up slice):

```python
class ResourceOwnershipPort(Protocol):
    def describe_ownership(self, resource: ResourceRef) -> OwnershipRecord: ...
    def attest_ownership(self, receipt: OwnershipReceipt) -> OwnershipAttestation: ...
```

- `describe_ownership` returns current ownership state + optional tenant attribution; no side effects.
- `attest_ownership` verifies the opaque operation proof, owned-id membership, and the live-proof expectation, returning a redacted `OwnershipAttestation`; it MUST NOT mutate or transition state.

## Existing Docker Authority Mapping (no change this slice)

`LocalOwnershipAuthority` already implements read/attest semantics: `read()` / latest-record lookup → `describe_ownership`; `owns()` / `verify_evidence()` → `attest_ownership`; `reserve`/`bind`/`activate`/`retire` are the deferred transition verbs. It becomes a future reference adapter unchanged; `provider.py`'s `verify_runtime_ownership` / `assert_live_ownership` show the live-proof expectation being satisfied Docker-natively.

## File Plan

| File | Action | Description |
|---|---|---|
| `openspec/changes/CAP-RESOURCE-OWNERSHIP/design.md` | Create | This contract-first design. |
| `src/odoo_forge/resource_ownership/types.py` | Create (follow-up) | Canonical home for the generalized `ResourceOwnership` state, `ResourceRef`, `OwnershipReceipt`, `OwnershipRecord`, `OwnershipAttestation`, `TenantAttribution`, plus the relocated `OperationIdentity` / `CreationReceipt` primitives. |
| `src/odoo_forge/ports/resource_ownership.py` | Create (follow-up) | `ResourceOwnershipPort` read/attest Protocol. |
| `src/odoo_forge/database/types.py` | Modify (re-export shim) | Import `ResourceOwnership` / `OperationIdentity` / `CreationReceipt` (and any other relocated names) from `resource_ownership.types` and re-export them under the same names; keep `DatabaseSpec` / `DatabaseRef` / `DatabaseCreation` / `CleanupReport` local. `__all__` unchanged so existing importers are unaffected. |
| `src/odoo_forge_postgres_docker/authority.py`, `provider.py` | Untouched | Keep importing from `database.types`; reference adapter / proof-of-pattern; no change this slice. |
| `docs/specs/platform/portfolio.json` | Modify later | Populate `AC-CAP-RESOURCE-OWNERSHIP-READY`; confirm downstream edges. |
| `docs/13-src-ports-map.md`, `docs/03-src-core-map.md` | Modify later | Register the port and the new core package. |

## Testing Strategy

| Layer | What to prove | Approach |
|---|---|---|
| Unit | State model stays exactly `created`/`adopted`/`external`; `ResourceRef` frozen/opaque; optional tenant attribution; receipt carries operation proof + owned ids + live-proof expectation | Pure pytest value-type tests. |
| Contract | `describe_ownership` read-only; `attest_ownership` refuses non-owned / missing-live-proof receipts and performs no mutation | Structural Protocol + fake-adapter contract tests in `tests/ports/`. |
| Architecture | Core stays provider-neutral; re-export keeps existing `database.types` callers and the Docker adapter green | import-linter + full existing suite unchanged. |

## Threat Matrix

N/A — no routing, shell, subprocess, VCS/PR automation, executable-file classification, or process-integration boundary. This slice adds pure-core value types and a Protocol only; live-proof mechanics (Docker labels, subprocess) stay in the untouched adapter.

## Migration / Rollout

No runtime migration. **Move-and-re-export**: the canonical definitions relocate to `resource_ownership/types.py`, and `database/types.py` becomes a re-export shim so every existing import path resolves unchanged — the Docker adapter and the database domain need no code changes. The one-time care is keeping the shim **exhaustive**: every name that moves must be re-exported under the same identifier (verified by the full existing suite staying green), so no importer breaks. Deliver as small chained slices under the 400-line budget — relocate value types + shim, then port + contract tests, then doc/portfolio alignment. Rollback reverts the artifacts and re-blocks the four downstream items from ownership-dependent design; current adapter behavior is unaffected either way.

### Risks

| Risk | Mitigation |
|---|---|
| Re-export shim misses a relocated name and breaks an importer | Keep `database.types.__all__` unchanged; run the full existing suite (28+ callers + Docker adapter tests) as the acceptance gate for the shim. |
| `attest_ownership` drifts into mutation / transition verbs | Contract tests assert read-only attestation; transition authority stays deferred to `SP-CONTROL-PLANE-AUTHORITY`. |
| Provider leakage into the neutral contract | Derive vocabulary from core value types only; live-proof mechanism stays adapter-owned. |

## Open Questions

None. All four proposal questions resolved and binding.
