# Current Stabilization Roadmap

**Status:** current as of 2026-07-15

This is the review-facing execution order for stabilizing the implemented platform before larger
product outcomes. [`portfolio.json`](platform/portfolio.json) remains authoritative for product
identity, status, dependencies, decisions, and acceptance evidence. OpenSpec owns normative
requirements; this roadmap links those artifacts instead of restating them.

## Next Action

Start a bounded SDD change for Unit 3, **Make Backend Planning Consume Materialized State**. Explore
how `plan_backend(manifest, state, ...)` should derive mounts from authoritative
`MaterializedState`, distinguish operations that require a materialized workspace from pure
instance operations, and reject absent or incoherent state safely. Keep
`CHG-FIRST-DATABASE-ADAPTER` and `sp-data-environments` outside this change.

Units 1 and 2 are complete. Do not reopen their archived OpenSpec artifacts or use their historical
planning text as requirements for Unit 3.

## Authority and Current State

| Source | Authority now | Evidence |
| --- | --- | --- |
| [`portfolio.json`](platform/portfolio.json) | Canonical product status and dependency authority | `meta.live_location` points to itself; its validator reports 0 violations. |
| This roadmap | Current stabilization sequence | Updated after Units 1 and 2 merged; current `origin/main` is PR #64 at `70293f0`. |
| [`2026-07-12-codebase-audit-roadmap.md`](../reviews/2026-07-12-codebase-audit-roadmap.md) | Closed review/remediation evidence | Its postscript records completed fixes and says Judgment Day was neither authorized nor performed. |
| [`2026-07-08-platform-roadmap.md`](2026-07-08-platform-roadmap.md) | Historical/superseded | Its header redirects current status to `portfolio.json`. |
| [`2026-07-06-phase-2-slices-roadmap.md`](2026-07-06-phase-2-slices-roadmap.md) | Historical/superseded | Its header preserves Phase 2 delivery history and redirects current planning. |

Current baseline evidence:

- Unit 1 is complete through issue #55 and PR #62: the disposable real-Docker lifecycle baseline
  and readiness/recovery behavior are merged and archived.
- Unit 2 is complete through PR #64 and archived OpenSpec change
  `2026-07-14-decide-manifest-layer-override-semantics`: published layers resolve to immutable
  version/digest lock entries and exact-URL Git overrides are applied before resolution.
- Final Unit 2 evidence records `uv run pytest`: 574 passed, 6 deselected; import-linter, Ruff,
  formatting, and mypy passed.
- `plan_backend(manifest, state, ...)` explicitly discards `MaterializedState`, so backend mounts
  do not yet reflect the materialized workspace.
- Provider-neutral database, data-artifact, durable-operation, project-catalog, and tenancy
  contracts are not equivalent to operational runtime integration.

## Active OpenSpec Inventory

Every non-archived directory under `openspec/changes/` is listed here.

| Active change | Classification | Exact evidence | Correct next step |
| --- | --- | --- | --- |
| [`CHG-FIRST-DATABASE-ADAPTER`](../../openspec/changes/CHG-FIRST-DATABASE-ADAPTER/exploration.md) | **Ready** for proposal | Exploration lines 7 and 57-59 say all three accepted inputs exist and the change is ready for proposal. Portfolio edges `G15`-`G17` point from achieved `CAP-CREDENTIALS`, `CAP-DATA-ARTIFACTS`, and `PORT-DATABASE-PROVIDER`; `DPROV-DB` selects Docker PostgreSQL. No proposal, spec, design, tasks, apply, verify, or archive artifact exists. | Create its SDD proposal after the runtime baseline unit below; do not extract the current backend or claim runtime cutover. |
| [`sp-data-environments`](../../openspec/changes/sp-data-environments/proposal.md) | **Blocked; planning partially complete** | Exploration, proposal, delta spec, design, and tasks exist. Tasks 1.1 and 1.3 are complete; task 1.2 and all implementation tasks are unchecked. Proposal lines 33-37 and spec lines 77-91 block implementation until `CHG-FIRST-DATABASE-ADAPTER`, `WF-DATA-COPY`, and `SP-CONTROL-PLANE-AUTHORITY` have accepted evidence. No apply, verify, or archive artifact exists. | Keep active but do not apply. Resume only after all three portfolio handoffs are accepted. |

There are no other active changes, no completed-but-unarchived change, and no active apply, verify,
or archive report. Archived changes and dated review records remain historical evidence and MUST NOT
be revived as trackers.

## Stabilization Work Units

Finish each unit with its implementation, focused tests, runtime evidence, and documentation in one
rollback-safe review boundary. Ordinary review means a frozen diff/content receipt and only the
named lens; it does not mean a full-repository review.

### 1. Establish Executable and Real-Docker Baselines

**Status: Complete** — merged through issue #55 and PR #62. The archived SDD evidence records the
disposable real-Docker lifecycle baseline and readiness/recovery corrections. This unit is closed.

| Field | Boundary |
| --- | --- |
| Portfolio/OpenSpec mapping | `CAP-LOCAL-BACKEND`; canonical `local-backend` spec. No active change exists, so a small stabilization SDD proposal is required before implementation. |
| Entry | Default suite passes; Docker daemon is reachable; real-daemon test reports only an unconditional skip. |
| Exit | Default full suite passes unchanged, and a disposable real-Docker `run -> status -> stop` test passes without leaked containers, networks, volumes, or credentials. Record Docker version and exact commands/results. |
| Rollback | Integration harness and its test-only fixtures; no production behavior. |
| Review | Ordinary focused resilience and cleanup review. Judgment Day is not justified. |

### 2. Decide Published-Layer and Override Semantics

**Status: Complete** — merged through PR #64 and archived at
`openspec/changes/archive/2026-07-14-decide-manifest-layer-override-semantics/`. The accepted
contract implements both features: published layers use immutable version/digest lock entries;
Git overrides match exact declared URLs and apply before resolution. This unit is closed.

| Field | Boundary |
| --- | --- |
| Portfolio/OpenSpec mapping | `CAP-MANIFEST`; canonical `manifest` spec and archived `decide-manifest-layer-override-semantics` change. |
| Entry | Real-Docker baseline is trusted; current schema accepts `PublishedLayer` and `Override`, while historical roadmaps record deferred resolution/application. |
| Exit | Complete: both features are implemented with explicit validation, lock compatibility, migration, projection, drift, and CLI behavior. |
| Evidence | Focused manifest lock/projection tests plus a real Git/registry runtime scenario only for the selected behavior. |
| Rollback | Decision and subsequent manifest work remain separate from backend and database changes. |
| Review | Ordinary architecture review. Use Judgment Day only if the decision changes the public manifest contract or persisted lock compatibility across existing users. |

### 3. Make Backend Planning Consume Materialized State

| Field | Boundary |
| --- | --- |
| Portfolio/OpenSpec mapping | `CAP-LOCAL-BACKEND`, `CAP-MANIFEST`; canonical `local-backend` and `manifest` specs. Future SDD proposal required. |
| Entry | Published-layer/override policy is settled; real-Docker baseline passes. |
| Exit | Backend plans derive mounts from authoritative `MaterializedState`, reject incoherent or absent materialization safely, and preserve pure instance operations where workspace state is irrelevant. |
| Evidence | Focused planner/CLI tests and a real-Docker mount/read-only/worktree scenario. |
| Rollback | Planner, CLI wiring, and their tests; Docker lifecycle semantics remain unchanged. |
| Review | Ordinary reliability and architecture-boundary review. Judgment Day only if the change alters the `BackendProvider` contract or broad runtime ownership. |

### 4. Recheck Registry, Git, and Workspace Runtime Risks

| Field | Boundary |
| --- | --- |
| Portfolio/OpenSpec mapping | `CAP-IMAGE-REGISTRY`, `PORT-SOURCE-PROVIDER`, `PORT-WORKSPACE-PROVIDER`. Existing canonical specs and the completed 2026-07-12 audit are evidence; new defects require separate future SDD proposals. |
| Entry | Backend consumes authoritative materialization; prior credential-redaction fixes remain green. |
| Exit | Bounded live Git, workspace, and registry scenarios confirm credentials stay out of argv/errors/logs, digest and ref classifications remain correct, and partial workspace operations are atomic. Any defect is extracted rather than hidden in characterization. |
| Evidence | Exact focused commands, disposable repositories/registry refs, and content receipts proving no secret-bearing output. |
| Rollback | Characterization by adapter; each reproduced defect becomes its own implementation unit. |
| Review | Ordinary security/resilience review per adapter. Judgment Day only for a severe confirmed leak or a shared cross-adapter error-model redesign. |

### 5. Deliver the First Database Adapter

| Field | Boundary |
| --- | --- |
| Portfolio/OpenSpec mapping | `CHG-FIRST-DATABASE-ADAPTER`, `DPROV-DB`, edges `G15`-`G17`; active [exploration](../../openspec/changes/CHG-FIRST-DATABASE-ADAPTER/exploration.md). |
| Entry | Unit 1 runtime receipt is green; active change advances through proposal, spec, design, and tasks; accepted provider, credential, and artifact handoffs remain unchanged. |
| Exit | Additive Docker PostgreSQL adapter passes contract, credential, ownership, recovery, artifact, and real-Docker tests. Existing local backend still owns its PostgreSQL until a separate cutover. |
| Rollback | Isolated adapter package, composition wiring limited to its test/runtime entry point, tests, and SDD evidence; no local-backend extraction. |
| Review | Chained ordinary reviews, each at most 400 authored changed lines, using contract, security, resilience, or data-safety lens as appropriate. Judgment Day only for a severe data-loss/credential finding or an unavoidable high-impact ownership decision. |

### 6. Integrate Data Foundations into Durable Runtime Workflows

This stage is dependency ordered; achieved contracts do not prove runtime delivery.

| Order | Portfolio mapping | Current state and required artifact | Exit evidence |
| ---: | --- | --- | --- |
| 6.1 | `CAP-DATA-ARTIFACTS`, `CAP-DURABLE-OPERATIONS` | Both are achieved provider-neutral foundations, but neither has a concrete persistence/runtime adapter. One bounded integration proposal per selected consumer is required. | Real adapter receipts prove artifact integrity, replay, terminal commit, and residual cleanup across process failure. |
| 6.2 | `INT-DATABASE-RUNTIME-CUTOVER` | Proposed with superseded-planning evidence only. Future SDD proposal required after Unit 5 and the required 6.1 integration decisions. | One database owner, migration/rollback proof, preserved existing volumes, real-Docker receipt. |
| 6.3 | `CAP-RESOURCE-OWNERSHIP` | Proposed; no active artifact. Future SDD proposal required. | Invocation ownership and safe compensation are enforced by concrete adapters. |
| 6.4 | `WF-DATA-COPY` | Proposed with superseded-planning evidence only. Future SDD proposal required after 6.1-6.3. | Coherent database/filestore copy, replay, cleanup, and failure receipts against real adapters. |
| 6.5 | `CAP-PROJECT-CATALOG` | Achieved provider-neutral resolution; no operational catalog adapter. Future integration proposal required when a consumer is selected. | Authoritative persisted lookup is wired to a real consumer with conflict and recovery evidence. |
| 6.6 | `CAP-TENANCY` | Canonical spec exists, but portfolio status is proposed and README records no tenancy implementation. Future SDD proposal required. | Tenant/quota authority is persisted and enforced at one real consumer boundary. |
| 6.7 | `SP-CONTROL-PLANE-AUTHORITY` | Proposed; no active artifact. Future SDD proposal required after project catalog and tenancy integration decisions. | Authoritative reference/lineage store and transactional visibility have focused persistence/recovery evidence. |

Each unit uses ordinary diff/content-receipt review and the narrowest relevant lens. Judgment Day is
justified only for confirmed severe data-loss/security findings or a high-impact architecture fork
in persisted ownership, transaction, or tenancy authority.

### 7. Resume Managed Data Environments

| Field | Boundary |
| --- | --- |
| Portfolio/OpenSpec mapping | `SP-DATA-ENVIRONMENTS`; active [proposal](../../openspec/changes/sp-data-environments/proposal.md), [spec](../../openspec/changes/sp-data-environments/specs/managed-data-environments/spec.md), [design](../../openspec/changes/sp-data-environments/design.md), and [tasks](../../openspec/changes/sp-data-environments/tasks.md). |
| Entry | Task 1.2 has accepted evidence for `CHG-FIRST-DATABASE-ADAPTER`, `WF-DATA-COPY`, and `SP-CONTROL-PLANE-AUTHORITY`; active artifacts are refreshed if prerequisite contracts changed. |
| Exit | Complete its existing tasks and verification without absorbing prerequisite scope; archive only after normative spec sync and accepted runtime receipts. |
| Evidence | Use the active spec's scenarios, focused recovery/coherence tests, and real adapter/control-plane runtime evidence. |
| Rollback | Preserve existing local Docker behavior and data; disable incomplete outcome wiring and reconcile or compensate invocation-owned targets. |
| Review | Forced chained ordinary reviews under the recorded 400-line budget. Judgment Day only for a severe finding or a high-impact atomic visibility/lineage architecture decision. |

### 8. Larger Product Outcomes

After Unit 7, schedule portfolio outcomes such as `SP-DATA-RECOVERY`,
`SP-DEVELOPER-ONBOARDING`, `SP-ENVIRONMENT-REQUESTS`, `SP-PRODUCTION-GOVERNANCE`,
`SP-DELIVERY-AUTOMATION`, remote deployment, access/RBAC, and operations UI strictly from
`portfolio.json` dependencies. Each outcome without an active artifact requires its own future SDD
proposal. This roadmap does not activate or reprioritize them.

## Explicit Non-Goals

- Changing portfolio product status from roadmap prose.
- Rewriting historical roadmaps, archived changes, review receipts, or verification evidence.
- Reviving historical SP-2 or archived database plans as current requirements.
- Starting `sp-data-environments` apply while task 1.2 is blocked.
- Folding runtime cutover, coordinated copy, control-plane authority, or managed environments into
  the first database-adapter change.
- Treating unit coverage, fake providers, or skipped integration tests as real-runtime proof.
- Blanket full-repository review or Judgment Day based only on size, age, or WARNING/INFO findings.
- Commits, staging, pushes, pull requests, or implementation changes as part of this roadmap update.

## Completion Receipt

For every work unit, record the immutable start/end target, authored changed-line count, exact
focused and full-suite commands/results, runtime harness/result or explicit reason it cannot run,
rollback boundary, review tier/lens, and receipt path. A unit is not complete when its normative
OpenSpec delta, implementation, verification, portfolio evidence, and archive status disagree.
