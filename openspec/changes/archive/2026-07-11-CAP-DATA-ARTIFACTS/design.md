# Design: CAP-DATA-ARTIFACTS

## Technical Approach

Keep this change contract-first and prerequisite-only. The capability will continue to expose exactly one opaque `DataArtifactRef` to downstream restore consumers, but the capability boundary will define the pure-domain models that explain what that ref can resolve to, how coherence is proven, which validation outcomes block mutation, and how discard is reported without leaking artifact details.

This design does **not** implement storage adapters, artifact transport, restore orchestration, anonymization policy, or control-plane ownership. It defines only the stable contract that those later concerns must consume.

**Review boundary:** represent the contract in pure-core types and validation-oriented interfaces, prove it with contract tests, and record readiness evidence only after verification. No adapter runtime work is included here.

## Architecture Decisions

| Decision | Choice | Alternative / tradeoff | Rationale |
|---|---|---|---|
| Opaque input shape | Keep `DataArtifactRef = NewType("DataArtifactRef", str)` as the only downstream restore input | Expand provider restore to multiple refs or structured payloads | Preserves the accepted database-provider contract and keeps control-plane lineage ref-only. |
| Internal meaning of the ref | A `DataArtifactRef` resolves inside the capability boundary to one **restore set** manifest | Treat the ref as a database-only blob or expose explicit db/filestore refs | The restore set model is the smallest shape that preserves one opaque input while making database+filestore coherence explicit. |
| Contract representation | Add frozen Pydantic models for restore-set metadata, validation outcomes, and discard outcomes | Leave the contract in prose only | Downstream work needs runtime-checkable pure-domain structures to verify conformance without adapter implementation. |
| Capability seam | Define a pure protocol for `resolve`, `validate_for_restore`, and `discard` at the data-artifacts boundary | Let downstream consumers infer validation rules themselves | Keeps integrity/coherence/discard ownership inside the capability and prevents drift across consumers. |
| Coherence proof | Manifest requires explicit component membership and lineage-compatible set identity | Implicitly assume co-capture from naming conventions | The managed-environments spec requires a usable database+filestore pair, not a naming guess. |
| Failure surface | Use typed, redacted enums/models for validation and discard outcomes | Free-form strings or adapter exceptions | Makes fail-closed behavior testable and prevents byte/secret/source leakage. |
| Delivery | Force chained, feature-branch-chain slices with pure-core models first and evidence wiring last | One larger PR | Keeps each review slice well below the 400 authored-line budget and avoids mixing contract work with downstream integration. |

## Data Flow

```text
Downstream consumer
  -> receives DataArtifactRef
  -> passes opaque ref to data-artifacts capability
  -> capability resolves ref to RestoreSetManifest
  -> capability validates availability + integrity + coherence
  -> capability returns RestoreReadiness
       | ready      -> downstream may begin restore mutation later
       | not ready  -> downstream fails closed, no mutation
  -> after consumer lifecycle, capability may receive discard(ref or resolved set)
  -> capability returns typed redacted DiscardOutcome
```

The key rule is ownership: downstream consumers see one opaque ref and typed readiness/discard outcomes, while the capability owns grouping, membership, digest semantics, and residual cleanup meaning.

## File Plan

| File | Action | Description |
|---|---|---|
| `src/odoo_forge/data_artifacts/types.py` | Modify | Keep `DataArtifactRef` opaque and add the pure frozen base model plus contract-facing value types. |
| `src/odoo_forge/data_artifacts/contracts.py` | Create | Define restore-set manifest, component metadata, validation result, discard result, and the capability protocol. |
| `src/odoo_forge/data_artifacts/__init__.py` | Modify | Re-export the stable public contract surface. |
| `src/odoo_forge/ports/database_provider.py` | No signature change | Keep `restore(..., artifact: DataArtifactRef, ...)` unchanged; add at most a clarifying docstring if needed. |
| `tests/data_artifacts/test_contracts.py` | Create | Prove opaque-ref invariants, required membership, redaction, frozen models, and fail-closed validation shapes. |
| `tests/ports/test_database_provider.py` | Modify | Reinforce that provider restore continues to consume exactly one opaque `DataArtifactRef`. |
| `openspec/changes/CAP-DATA-ARTIFACTS/design.md` | Create | Persist this prerequisite-only design. |
| `docs/specs/platform/portfolio.json` | Modify later | Record approved artifact and verification identifiers only after acceptance; do not advance readiness during contract implementation. |

## Interfaces / Models

```python
DataArtifactRef = NewType("DataArtifactRef", str)

class ArtifactComponentKind(StrEnum):
    DATABASE = "database"
    FILESTORE = "filestore"

class ValidationFailureCode(StrEnum):
    UNAVAILABLE = "unavailable"
    INTEGRITY_FAILED = "integrity_failed"
    COHERENCE_FAILED = "coherence_failed"
    INCOMPLETE = "incomplete"
    UNSUPPORTED_FORMAT = "unsupported_format"

class DiscardOutcomeCode(StrEnum):
    COMPLETED = "completed"
    REFUSED = "refused"
    RESIDUAL_FAILURE = "residual_failure"

class ArtifactDigest(_ArtifactValue):
    algorithm: str
    value: str

class RestoreSetComponent(_ArtifactValue):
    kind: ArtifactComponentKind
    opaque_component_ref: str
    format_version: str
    digest: ArtifactDigest

class RestoreSetManifest(_ArtifactValue):
    restore_set_id: str
    lineage_id: str
    components: tuple[RestoreSetComponent, ...]

class RestoreReadiness(_ArtifactValue):
    ready: bool
    manifest: RestoreSetManifest | None
    failure_code: ValidationFailureCode | None
    redacted_detail: str | None

class DiscardOutcome(_ArtifactValue):
    code: DiscardOutcomeCode
    residual_ids: tuple[str, ...] = ()
    redacted_detail: str | None = None

@runtime_checkable
class DataArtifactCapability(Protocol):
    def resolve(self, ref: DataArtifactRef) -> RestoreSetManifest: ...
    def validate_for_restore(self, ref: DataArtifactRef) -> RestoreReadiness: ...
    def discard(self, ref: DataArtifactRef) -> DiscardOutcome: ...
```

### Model invariants

- `DataArtifactRef` remains opaque and string-backed only.
- `RestoreSetManifest.components` must contain exactly the required members for the target contract; for managed Odoo-like environments that means one `database` and one `filestore` component.
- Component metadata may expose identifiers, format markers, and digests, but never bytes, secrets, hostnames, or live-source details.
- Validation and discard outcomes must be structurally typed and redacted.
- Frozen models use `extra="forbid"` and `hide_input_in_errors=True` to make leakage and shape drift testable.

## Validation Flow

1. **Resolve opaque ref**
   - Consumer supplies one `DataArtifactRef`.
   - Capability resolves it to one restore-set manifest inside the capability boundary.
2. **Check manifest shape**
   - Required identity fields exist.
   - Required component membership exists.
   - Format/version markers are present.
3. **Check integrity evidence**
   - Every required component has digest evidence.
   - Digest metadata is syntactically valid.
4. **Check coherence**
   - Manifest identifies one restore set and one lineage/coherence boundary.
   - Partial, duplicate, or mismatched membership fails closed.
5. **Emit readiness**
   - Success returns `RestoreReadiness(ready=True, manifest=...)`.
   - Any failure returns `ready=False` with a typed failure code and redacted detail.
6. **Mutation gate**
   - Downstream restore work may proceed only from `ready=True`.
   - This capability does not perform restore mutation; it gates it.
7. **Discard handoff**
   - Discard returns `COMPLETED`, `REFUSED`, or `RESIDUAL_FAILURE` with safe opaque residual ids only.

## Integration Contract

- **Database provider:** no signature change. `DatabaseProvider.restore(...)` continues to accept one `DataArtifactRef`; later orchestration may call the data-artifacts capability before invoking provider mutation, but this design does not own that workflow.
- **Managed data environments:** the restore-set manifest becomes the prerequisite contract that proves database+filestore coherence without requiring that capability to invent grouping rules.
- **Control plane:** compatibility remains ref-only. Control-plane systems may store `DataArtifactRef`, readiness evidence identifiers, and lineage references, but not artifact bytes.
- **Adapters:** future adapter/storage implementations must satisfy the protocol and invariants above; they are intentionally out of scope for this design.

## Verification / Evidence Plan

| Evidence target | Proof |
|---|---|
| Opaque reference conformance | Unit tests prove `DataArtifactRef` stays string-backed and no public contract expands restore input beyond one opaque ref. |
| Restore-set resolution contract | Unit tests prove manifest requires restore-set identity plus required component membership. |
| Integrity metadata contract | Unit tests prove digest metadata is required and byte-bearing/secret-bearing extras are rejected. |
| Fail-closed readiness | Unit tests prove unavailable, incomplete, integrity-failed, and coherence-failed states return typed redacted outcomes with `ready=False`. |
| Typed discard outcomes | Unit tests prove discard reports only approved outcome codes and safe opaque residual ids. |
| Downstream compatibility | Contract test proves `DatabaseProvider.restore` still accepts exactly one `DataArtifactRef`. |
| Readiness gate | Portfolio evidence is updated only after proposal/spec/design approval and verification receipt identifiers exist for `AC-CAP-DATA-ARTIFACTS-READY`. |

## Risks

| Risk | Why it matters | Mitigation |
|---|---|---|
| Contract drifts into adapter implementation | Would absorb storage/orchestration scope and blow the review budget | Keep the capability seam protocol-only and test pure-domain invariants only. |
| Manifest is too weak to prove coherence | Downstream environments could accept partial restore inputs | Require explicit component membership and shared restore-set identity. |
| Failure fields leak sensitive details | Violates opaque-reference and redaction requirements | Use typed enums, redacted detail strings, and forbidden extra fields. |
| Downstream consumers bypass readiness | Mutation could start on invalid artifacts | Keep readiness as the explicit gate and preserve provider restore's single-ref contract for later orchestration wiring. |

## Delivery Shape (<400 authored-line review budget)

1. **PR 1 — Core contract models**
   - Add frozen data-artifact value models and exports.
   - Add unit tests for shape, freezing, and redaction.
2. **PR 2 — Capability protocol + readiness/discard outcomes**
   - Add the pure protocol and validation/discard result types.
   - Add fail-closed contract tests.
3. **PR 3 — Downstream compatibility + readiness evidence wiring**
   - Reinforce `DatabaseProvider.restore` compatibility tests.
   - Update portfolio evidence pointers only after verification artifacts exist.

With `feature-branch-chain`, each child PR targets the immediate previous PR branch so reviewers see one contract concern at a time.

## Rollout

No runtime migration is required. This change is additive and contract-only. Downstream restore, managed-environment, and control-plane work remain blocked on their own acceptance gates until this capability has approved artifacts and verification evidence.

## Open Questions

None.
