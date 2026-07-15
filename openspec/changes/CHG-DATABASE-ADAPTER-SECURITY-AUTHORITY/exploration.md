## Exploration: CHG-DATABASE-ADAPTER-SECURITY-AUTHORITY

### Current State
The Docker PostgreSQL adapter is additive and currently preserves the provider-neutral `DatabaseProvider` contract and local-backend routing. Provisioning obtains an opaque credential handoff, passes an `--env-file` path to `docker run`, applies public Docker labels, verifies labels/readiness, and returns a `DatabaseCreation` containing a receipt. Ownership is presently reconstructible from `docker inspect`: the receipt operation/token is copied into labels, and `assert_live_ownership` accepts matching public labels. Runtime evidence is created by an importable module-level `_mint_runtime_ownership_evidence` function guarded only by an in-memory module marker, so a consumer able to import the module can mint evidence without a live adapter authority.

The accepted findings from `review-e272dab2cf939ee5` are therefore security-boundary defects, not ordinary verification cleanup: PostgreSQL credentials can persist in Docker `Config.Env`; ownership receipts can be reconstructed from inspect-visible labels; runtime evidence minting is forgeable/importable; and verification/archive evidence is stale relative to the final authority lineage. The archived verification-closure evidence is useful historical context but must be regenerated for this change and must not be treated as final authority.

The source contracts explicitly require handle-only credential handoffs, no plaintext in provider values/diagnostics/evidence, receipt-scoped mutation, fail-closed runtime acceptance, preserved provider-neutral contracts, and unchanged local-backend ownership/routing. Existing tests cover the current label proof, readiness gate, credential target handoff, rollback behavior, and real-Docker prerequisite harness. No review artifact for `review-093c1c067f361178` was opened or modified; that lineage is expressly excluded.

### Affected Areas
- `src/odoo_forge_postgres_docker/provider.py` — replace inspect-reconstructible label proof, remove the current mint call, and ensure Docker invocation cannot persist PostgreSQL credentials in `Config.Env`.
- `src/odoo_forge/database/readiness.py` — replace the importable/in-memory runtime evidence minting seam with a verifiable authority while retaining the pure readiness evaluator and provider-neutral shape unless evidence proves a narrower compatible boundary.
- `src/odoo_forge_postgres_docker/target_handoffs.py` and `src/odoo_forge/credentials/materialization.py` — preserve opaque credential capability semantics while defining a target-native injection path that does not downgrade to Docker environment persistence.
- `src/odoo_forge/database/types.py`, `src/odoo_forge/database/errors.py`, and `src/odoo_forge/ports/database_provider.py` — inspect for compatibility only; provider-neutral contracts and typed redaction must remain unchanged.
- `tests/adapters/test_postgres_docker_provider.py` — add security regressions for `Config.Env`, non-reconstructible receipts, authority-backed evidence, and fail-closed ownership decisions.
- `tests/adapters/test_postgres_docker_provider_integration.py` — extend real-Docker proof where unit doubles cannot demonstrate inspect behavior or credential persistence.
- `tests/database/test_readiness.py` — preserve and extend acceptance tests so forged/importable evidence cannot make the gate ready.
- `openspec/specs/docker-postgresql-database-adapter/spec.md`, `openspec/specs/credential-materialization/spec.md`, and `openspec/specs/database-provider/spec.md` — normative boundaries to preserve or delta-modify; do not redefine provider-neutral contracts.
- `openspec/changes/archive/2026-07-15-CHG-DATABASE-ADAPTER-VERIFICATION-CLOSURE/verify-report.md` — read-only historical evidence; regenerate final verification evidence against the new lineage rather than editing or reusing it as current proof.

### Approaches
1. **Target-native secret injection plus adapter-held ownership authority** — provision PostgreSQL through a Docker-supported secret/file mechanism that is absent from `Config.Env`; keep receipt authority in a non-inspect-reconstructible verifier (for example, an adapter-owned capability/registry or cryptographically verifiable, non-public receipt binding), and issue runtime evidence only through that authority after live inspect/readiness checks.
   - Pros: directly closes all accepted findings; preserves opaque credential contracts; makes the security boundary explicit; supports genuine real-Docker evidence.
   - Cons: requires deciding how authority survives process boundaries/reconcile; Docker version/runtime behavior must be validated; likely spans provider, authority types, and integration tests.
   - Effort: High

2. **Cryptographic receipt/evidence tokens only** — replace public labels and the in-memory marker with signed, opaque tokens validated by an adapter-owned key or verifier, while using a Docker secret/file injection mechanism for credentials.
   - Pros: portable across process boundaries and compatible with reconcile; no inspect-visible token needs to reveal receipt contents.
   - Cons: key custody/rotation and replay/lifetime semantics become mandatory; a verifier key embedded in the same importable package would recreate the trust problem; more design risk before tracker integration.
   - Effort: High

3. **External authority service/store** — delegate receipt and runtime evidence issuance to a durable authority outside the adapter process, with Docker labels containing only opaque lookup identifiers.
   - Pros: strongest process and restart boundary; naturally supports reconciliation and lineage.
   - Cons: introduces a new operational dependency and control-plane scope; conflicts with the requested bounded additive adapter unless explicitly constrained; highest delivery and review risk.
   - Effort: High

### Recommendation
Proceed to proposal with Approach 1 as the bounded direction, explicitly leaving the concrete authority persistence mechanism open for design comparison with Approach 2. The design must define a verifier that is not importable mint authority, does not derive creator proof solely from `docker inspect`, and can support reconcile/rollback without weakening fail-closed behavior. Use Docker-native secret/file injection whose material is not represented in `Config.Env`; prove this with captured `docker inspect` evidence and absence assertions. Preserve `DatabaseProvider`, credential/data-artifact contracts, local-backend routing, tracker/control-plane/data-environment/copy/PublishedLayer/Override exclusions, and all existing scope exclusions. Regenerate verification and archive evidence only after the final authority lineage is complete. Never modify, recover, validate, reopen, or otherwise touch `review-093c1c067f361178`.

The 400-line review budget and force-chained delivery require proposal/design/tasks to forecast multiple autonomous PR slices. A likely chain is: authority and contract seam; credential-safe Docker provisioning; ownership/reconcile and runtime evidence; then real-Docker verification/evidence regeneration. Exact slicing belongs in tasks after design, with each slice independently testable and rollbackable.

### Risks
- Docker secret/file injection may have version, platform, or cleanup semantics that differ from the current `--env-file` path; real-Docker tests are required, not just runner assertions.
- A cryptographic token without protected key custody, or an in-process registry without restart/reconcile semantics, would only relocate rather than close the authority defect.
- Receipt authority must remain available for rollback and reconcile without making its reconstruction possible from public inspect output.
- Removing public labels entirely may affect discovery; retaining lookup labels must not grant ownership authority or reveal reconstructable receipt data.
- Evidence regeneration must bind exact source/test outputs to the final lineage and must not mutate or conflate the forbidden `review-093c1c067f361178` lineage.
- Broad changes to provider-neutral types, local-backend routing, tracker integration, or control-plane/data-environment semantics would violate scope exclusions.

### Ready for Proposal
Yes. The proposal should define this as a security-authority redesign before tracker integration, record `review-e272dab2cf939ee5` as accepted input, explicitly preserve all exclusions, forbid any interaction with `review-093c1c067f361178`, and require final-lineage evidence proving no `Config.Env` credential persistence, no inspect-reconstructible ownership receipt, no importable evidence minting, and fail-closed runtime acceptance.

## Result Contract

```yaml
status: success
executive_summary: "Exploration confirmed four accepted Docker PostgreSQL authority defects and mapped a bounded additive redesign that preserves provider-neutral contracts, local-backend routing, and scope exclusions. The recommended direction combines target-native credential injection with a verifiable adapter-held authority, followed by final-lineage evidence regeneration."
artifacts:
  - "openspec/changes/CHG-DATABASE-ADAPTER-SECURITY-AUTHORITY/exploration.md"
next_recommended: propose
risks:
  - "Authority persistence, restart/reconcile behavior, and Docker-native secret injection require explicit design and real-Docker proof."
  - "Verification/archive evidence must be regenerated against the final lineage without touching review-093c1c067f361178."
  - "The 400-line budget requires force-chained PR slices to be planned before implementation."
skill_resolution: paths-injected
```
