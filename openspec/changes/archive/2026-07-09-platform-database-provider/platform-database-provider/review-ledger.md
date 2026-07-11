# Review Ledger: Platform Database Provider

## Judgment Day — Design Round 1

Gate result: **FAIL**. The design phase receives one automatic corrective rerun before dependent phases may proceed.

| id | lens | location | severity | status | evidence |
|---|---|---|---|---|---|
| JDA-001 | judgment-day | `design.md:12,22,42-45,58` | BLOCKER | open | The coordinator requires filestore sequencing, validation, receipts, and compensation that the declared provider contract does not expose. |
| JDA-002 | judgment-day | `design.md:44-50,73-81` | BLOCKER | verified | Normative flow calls `NetworkProvider.ensure` before DB creation; atomic network receipt ownership and the only compensation/successful-stop release paths are explicit. |
| JDA-003 | judgment-day | `design.md:22,42-54,58` | CRITICAL | open | Best-effort cleanup lacks a residual-resource outcome or reconciliation contract, risking sensitive partial targets. |
| JDA-004 | judgment-day | `design.md:24,35-50` | CRITICAL | open | Audit persistence occurs after mutation and has no fail-closed behavior for append, flush, or fsync failure. |
| JDA-005 | judgment-day | `design.md:13,58,65` | CRITICAL | open | PostgreSQL extraction leaves status, stop, logs, roles, and instance status ownership unresolved. |
| JDA-006 | judgment-day | `design.md:12,22,42-43,74-75` | CRITICAL | open | Sequential live database and filestore copies have no shared consistency boundary. |
| JDA-007 | judgment-day | `design.md:79-81` | WARNING | info | The proposed slice order can temporarily break `forge run` before provider composition lands. |
| JDB-001 | judgment-day | `design.md:64` | CRITICAL | verified | Pure-core `resolve_policy` fixes dev/qa/preprod behavior; `CopySpec` carries destination, and production-derived bypass is limited and durably audited. |
| JDB-002 | judgment-day | `design.md:79-81` | CRITICAL | open | Ownership extraction precedes CLI composition, creating an invalid intermediate release. |
| JDB-003 | judgment-day | `design.md:5,58,79-81` | CRITICAL | open | Existing backend-owned PostgreSQL instances have no compatibility path after ownership transfer. |
| JDB-004 | judgment-day | `design.md:5,58,79-81` | WARNING | info | Responsibility for the required database reachability probe and timeout is undefined. |

## Synthesis

- Confirmed by both judges: unsafe chained rollout ordering (`JDA-007`, `JDB-002`).
- Independently corroborated by the automatic design gate: provider/filestore contract, Docker network ownership, local-backend routing, canonical SP-2 drift, audit failure semantics, package/import boundaries, and production-data safety.
- Warnings remain informational and do not independently trigger fixes.
- Corrective action: rerun `sdd-design` once with the full gate feedback, then run a fresh design gate and scoped Judgment Day re-review.

## Round 2 Result

- Scoped Judgment Day: **APPROVED** — all original BLOCKER/CRITICAL entries above were verified; warnings remain informational.
- Automatic design gate: **FAIL** on the final allowed retry. The scoped judges could not introduce findings outside the original ledger, while the full fresh-context gate found four remaining contract defects.

| id | lens | location | severity | status | evidence |
|---|---|---|---|---|---|
| GATE-001 | reliability | `design.md:18-58` | CRITICAL | resolved | Canonical `DatabaseProvider` signatures are preserved exactly; richer runtime and lifecycle behavior moved to named companion ports, with signature conformance required. |
| GATE-002 | readability | `design.md:12,28-30,79` | CRITICAL | resolved | Quiescing uses `ports/data_consistency_provider.py`; existing Git `ports/source_provider.py` is explicitly untouched. |
| GATE-003 | reliability | `design.md:18-60,66-71` | CRITICAL | resolved | Frozen capture/receipt/network types, executable capture/restore/validate/discard/drop/quiesce/resume operations, and cleanup ownership are defined; undefined `Created[T]` was removed. |
| GATE-004 | reliability | `design.md:42-75` | CRITICAL | resolved | Versioned aggregate repository/bindings, exact post-extraction runtime signatures, composite routing and stop failure semantics, and executable legacy discovery/adoption are defined. |

Automatic routing is stopped after the second failed design gate. Dependent tasks, apply, and verify phases MUST NOT run until these blockers are resolved in a new user-approved continuation.

## User-Approved Remediation Gate

The user approved a new automatic continuation. `GATE-001` and `GATE-002` are verified; the following findings remain open after the first remediation attempt:

| id | lens | location | severity | status | evidence |
|---|---|---|---|---|---|
| GATE-005 | reliability | `design.md:18,28-37,73-76` | CRITICAL | verified | `QuiesceLease` owns the authoritative boundary; both captures consume the lease and MUST derive their boundary from it. |
| GATE-006 | risk | `design.md:18,33-50,62` | CRITICAL | verified | DB, filestore, and network creators atomically return creator-produced receipts; inventory preflight is prohibited and cleanup ownership is mapped. |
| GATE-007 | risk | `design.md:64` | CRITICAL | verified | Pure classification, canonical destination mapping, anonymization default, and destination-limited audited bypass are executable contracts. |
| GATE-008 | reliability | `design.md:51-59,66` | CRITICAL | verified | `commit_bound` transactionally persists aggregate+binding with lock, temp-file fsync, replace, directory fsync, typed failure, and legacy reuse. |
| GATE-009 | reliability | `design.md:44-59,79-81` | CRITICAL | verified | Runtime and legacy signatures, absent behavior, ordered partial stop failure, and exact network release owner/timing are explicit. |
| GATE-010 | resilience | `design.md:55-56,68` | CRITICAL | verified | `append_durable` returns only after append+flush+fsync, raises `AuditDurabilityError`, and remains fail-closed before/after mutation. |
| GATE-011 | risk | `design.md:83-87` | CRITICAL | verified | Hatch wheel package, import-linter root package, and forbidden core→PostgreSQL-adapter contract are mandatory. |

One automatic corrective design rerun is allowed for this user-approved continuation; tasks remain blocked until a fresh full gate passes.

## User-Approved Remediation Final Gate

The scoped judges verified the targeted remediation lines, but the fresh full-context gate **FAILED** after the allowed corrective rerun. The scoped verdict cannot clear defects outside its constrained target.

| id | lens | location | severity | status | evidence |
|---|---|---|---|---|---|
| GATE-012 | reliability | `design.md:28-43,73-76` | CRITICAL | open | Database creation consumes a live `DatabaseRef` rather than the captured database artifact, so DB and filestore targets are not guaranteed to share one boundary. |
| GATE-013 | reliability | `design.md:21-59,76,79` | CRITICAL | open | The normative flow invokes validation and capture discard, but no provider contract exposes those operations. |
| GATE-014 | resilience | `design.md:68,76-79` | CRITICAL | open | Post-commit audit failure can compensate resources without rolling back the durable aggregate binding, leaving torn state. |
| GATE-015 | resilience | `design.md:66` | CRITICAL | open | `commit_bound` promises prior-document preservation after replace/fsync failure without a journal or backup recovery protocol. |
| GATE-016 | reliability | `design.md:44-47,79` | CRITICAL | open | Odoo-only backend ownership conflicts with the preserved composite `InstanceStatus`; exact status merge, reachability probe owner/timeout, and error compatibility are incomplete. |
| GATE-017 | risk | `design.md:18,64,68,73` | CRITICAL | open | Durable audit schema/control flow does not explicitly guarantee all required fields or record authorization denial before returning. |
| GATE-018 | resilience | `design.md:68,79` | CRITICAL | open | Cleanup residual aggregation, persistence, retry, and reconciliation remain non-executable. |

Automatic remediation is stopped. Tasks, apply, and verify remain blocked until a new user-approved continuation resolves `GATE-012..018` and a fresh full-context design gate passes.

## User-Approved Design Remediation — Attempt 2

`JDA-002`, `JDB-001`, and `GATE-005..011` are verified only against the explicit contracts cited above. Proposal and specs remain unchanged. No tasks or implementation were created; dependent phases await the fresh design gate.
