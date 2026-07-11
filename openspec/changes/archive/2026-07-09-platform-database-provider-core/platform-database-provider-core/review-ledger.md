# Review Ledger: Platform Database Provider Core

## Design Round 1

Automatic corrective design attempt 2: **READY FOR RE-REVIEW**. Round-1 findings retain their original severity; statuses below changed only where the updated spec/design contains explicit executable evidence.

| id | lens | location | severity | status | evidence |
|---|---|---|---|---|---|
| CORE-001 | risk | `design.md` “Interfaces / Contracts”, “Testing Strategy” | CRITICAL | corrected | Deterministic identities/labels plus `reconcile_created` reconstruct receipts; cleanup aggregates every teardown failure and tests mutation-before-return. |
| CORE-002 | risk | `spec.md` “Pure Lifecycle Values”; `design.md` credential contract | CRITICAL | corrected | Injected `CredentialResolver` yields protected temporary password/pgpass leases; argv/log/error/ref/receipt exclusion and guaranteed unlink are normative and tested. |
| CORE-003 | reliability | `spec.md` “Pure Lifecycle Values”; `design.md` decisions/contracts | CRITICAL | corrected | `DatabaseSpec.network: NetworkAttachment` is opaque and runtime-supplied; adapter never creates, owns, or removes networks. |
| CORE-004 | reliability | `spec.md` “Creation Outcomes”; `design.md` contracts/commands | CRITICAL | corrected | Canonical live operations and tagged captured requests are distinct; capture has media/version/digest/URI only, exact restore dispatch, and source-unavailable tests. |
| CORE-005 | risk | `spec.md` “Recoverable Ownership”; `design.md` ownership labels | CRITICAL | corrected | Created/adopted/external metadata, creator-token label verification, canonical deliberate drop, and receipt-aware compensation helper are executable. |
| CORE-006 | architecture | `spec.md` “Adapter Isolation and Additive Coexistence” | CRITICAL | corrected | Provider selection/mixing requirements and scenarios were removed and delegated solely to umbrella `INT-CLI-01`; only additive package coexistence remains. |
| CORE-007 | resilience | `spec.md` “Docker PostgreSQL Lifecycle”; `design.md` command topology | CRITICAL | corrected | PostgreSQL 16 topology, names/labels, init/start/readiness, restore dispatch, transactions, rollback, reconciliation, and receipt timing are explicit. |
| CORE-008 | resilience | `design.md` subprocess paragraph; `spec.md` lifecycle requirements | CRITICAL | corrected | Bounded commands use safe operation labels; redaction precedes typed mapping; secret leases clean up on success/failure and residuals are reported. |
| CORE-009 | readability | `design.md` “Migration / Rollout” | CRITICAL | corrected | Nine autonomous tested slices separate contracts, scaffolding, provision/recovery, drop, live clone, captured restore, randomization, and real-Docker proof. |
| CORE-010 | reliability | `design.md` “Migration / Rollout” | WARNING | info | Ordering improved: values, receipts, reconciliation, and cleanup contracts land before the non-mutating scaffold and every mutation slice. |

Corrective design must also update the child spec where ownership is wrong, preserve canonical provider signatures, and keep runtime/governance/copy orchestration outside this child.

## Corrective Attempt 2 — Full Gate Result

Scoped Judgment Day verified `CORE-001..009`, but the fresh full-context gate **FAILED**. Scoped verification cannot clear newly exposed contract gaps.

| id | lens | location | severity | status | evidence |
|---|---|---|---|---|---|
| CORE-011 | readability | `spec.md` | CRITICAL | open | The specification is 1,069 words and exceeds the mandatory 650-word budget. |
| CORE-012 | resilience | `design.md:48-52` | CRITICAL | open | Recovery cannot reconstruct a random creator token from a hash label; no durable token store/derivation or crash-state machine exists. |
| CORE-013 | risk | `spec.md:25`; `design.md:43-50` | CRITICAL | open | Target credential creation/storage and artifact URI materialization are undefined; resolving existing handles is insufficient. |
| CORE-014 | resilience | `design.md:50-52` | CRITICAL | open | Complete secret-safe Docker argv/mount/env topology, dump transport, restore materialization, and safe subprocess result API remain unspecified. |
| CORE-015 | readability | `proposal.md:33`; `design.md:71-73` | CRITICAL | open | Proposal and design disagree on four versus nine slices, with no per-slice line forecast or explicit start/finish/rollback boundaries. |

Automatic remediation budget is exhausted. Tasks and implementation remain blocked until a new user-approved correction resolves `CORE-011..015` and a fresh full-context gate passes.
