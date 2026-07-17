# Design: First Docker PostgreSQL Database Adapter

## Technical Approach

Add `odoo_forge_postgres_docker` as an infrastructure package implementing the existing `DatabaseProvider` protocol. It uses argv-only Docker subprocesses, operation-scoped labels, creator tokens, and bounded `pg_isready` polling, following `DockerBackendProvider` patterns without importing or rerouting it. Core contracts, CLI routing, local-backend PostgreSQL, PublishedLayer/Override, WF-DATA-COPY, SP-CONTROL-PLANE-AUTHORITY, and sp-data-environments remain unchanged.

## Architecture Decisions

| Option | Tradeoff | Decision |
|---|---|---|
| Reuse `DockerBackendProvider` | Less code but couples database lifecycle to local-backend ownership | Reject; package-isolated adapter with its own Docker boundary |
| Receipt only vs. receipt plus live labels | Labels add inspection calls but prevent stale/forged receipt mutation | Require `provider`, operation, resource-kind, and random creator-token labels; destructive actions require receipt membership **and** exact live-label proof |
| Resolve handles directly vs. CAP target handoffs | Injected handoffs add interfaces but preserve opaque boundaries | Call `materialize_for_target(..., kind="database")`; adapter-local injectors consume the descriptor and validated `DataArtifactRef` without exposing plaintext/bytes |
| Persist a state database vs. Docker introspection | State is stronger offline but creates migration/consistency scope | Reconcile by operation labels; absent, foreign, adopted, or mismatched resources fail closed |

## Data Flow

    DPROV-DB selection -> DatabaseProvider -> CAP-CREDENTIALS descriptor
                              |                    |
                              | restore: validate DataArtifactRef
                              v                    v
                     ownership preflight -> Docker argv -> bounded readiness
                              |                         |
                              +-> receipt <- labels <---+

Provision generates an operation identity before mutation. Each created container, volume, and network receives a unique creator token and is appended to the receipt only after label verification. Failures roll back the reverse created set, rechecking labels. `reconcile`, `delete`, and `cleanup` use the same proof gate. Restore calls `DataArtifactCapability.validate_for_restore` before any Docker mutation, selects the database component from the ready manifest, then uses an adapter-local target injector. No backup API exists in `DatabaseProvider`, so this change adds no competing backup handoff.

## File Changes

| File | Action | Description |
|---|---|---|
| `src/odoo_forge_postgres_docker/__init__.py` | Create | Export the adapter |
| `src/odoo_forge_postgres_docker/provider.py` | Create | Lifecycle, proof gate, Docker runner, readiness, recovery, rollback |
| `src/odoo_forge_postgres_docker/target_handoffs.py` | Create | CAP credential/artifact target-side injection interfaces and redaction |
| `tests/adapters/test_postgres_docker_provider.py` | Create | Command, proof, failure, restore-order, and redaction RED tests |
| `tests/adapters/test_postgres_docker_provider_integration.py` | Create | Opt-in real-Docker acceptance evidence |
| `pyproject.toml` | Modify | Package/root-package registration and integration marker wording |
| `docs/specs/platform/portfolio.json` | Modify | Record DPROV-DB acceptance evidence only |

Provider-neutral files and `src/odoo_forge_docker/` are intentionally unchanged. Planned delivery is four autonomous chained slices, each forecast below 400 changed lines: proof/runner foundation; provision/reconcile/cleanup; CAP handoffs/restore; real-Docker evidence/portfolio receipt.

## Interfaces / Contracts

`DockerPostgresqlDatabaseProvider` keeps all six existing method signatures. Constructor dependencies are clocks, bounded subprocess runner, `DataArtifactCapability`, credential target injector, and restore target injector. Injectors accept only `CredentialInjectionDescriptor` or validated artifact references/manifests; sensitive material may exist only in protected temporary files and is removed on every exit path.

## Testing Strategy

| Layer | Evidence |
|---|---|
| Unit | Protocol conformance; argv/no-shell construction; timeout/nonzero mapping; readiness bound; restore validation before mutation; creator-proof refusal; reverse rollback; redacted exceptions |
| Integration | Real PostgreSQL provision/readiness, interrupted-operation reconcile, forced partial-failure rollback, restore handoff, secret/artifact redaction, foreign-resource survival, zero owned residuals |
| Boundary | `lint-imports`, mypy, ruff, default pytest; integration remains opt-in with unique labels and `finally` cleanup |

## Threat Matrix

| Boundary | Applicability | Safe/failure behavior | Planned RED tests |
|---|---|---|---|
| Documentation-like paths | N/A: no executable classification | No path execution added | None |
| Git repository selection | N/A: no Git invocation | No repository authority | None |
| Commit state | N/A: no commits | No index/worktree behavior | None |
| Push state | N/A: no push | No ref destination | None |
| PR commands | N/A: no PR automation | No command composition | None |
| Docker subprocess | Applicable: hostile names, timeout/nonzero, secret-bearing stderr | Validated identifiers, argv-only/no shell, bounded calls; typed redacted failure and label-proof refusal | Metacharacters never execute; timeout/nonzero fail typed; stderr secret absent; mismatched label blocks mutation |

## Migration / Rollout

No migration or runtime cutover. Acceptance only enables the DPROV-DB adapter; rollback removes selection evidence and only receipt-proven resources.

## Open Questions

None.
