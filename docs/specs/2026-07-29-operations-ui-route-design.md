# Operations UI route — SDD flow map

**Layer:** Planning · **Status:** design (not authority) · **Date:** 2026-07-29

> **This document is a design, not authority.** The normative planning record is
> [`docs/specs/platform/portfolio.json`](specs/platform/portfolio.json). Where the two disagree,
> the portfolio wins. This map becomes authoritative only by being adopted into the portfolio's
> `decompositions[]`, `decisions[]`, and `items[]` — which is declared here as `CHG-0`.

## Purpose

Define the ordered set of SDD changes required to reach a **minimal visible web surface** over the
odoo-forge control plane, and the gates each change depends on.

The deliverable of this design is the route itself. No implementation is authorized by this
document; each change on the route runs its own ordinary SDD cycle.

## Scope decisions

Four scoping decisions were taken before drawing the map:

1. **Deliverable** — the documented route only. No code in the design session.
2. **UI scope** — a **state dashboard**: view instances, their state, and their stored pointers.
   Actionable deployment is out of scope. Including it would pull `SP-DELIVERY-AUTOMATION` and
   `SP-ENVIRONMENT-REQUESTS` with their transitive hard dependencies — roughly thirteen nodes, or
   substantially the whole platform.
3. **Landing** — hybrid. This design doc now; adoption into the portfolio declared as `CHG-0`.
4. **Sequencing** — visible surface first. Identity and RBAC are deferred rather than built up
   front. This costs no graph integrity (see *Governance mechanics*), but it does require the
   `DEC-UI-PARTIAL` decision and the written constraints recorded with it.

## Verified findings

Established against `portfolio.json` and the source tree, not inferred from prose:

- `SP-OPERATIONS-UI` carries two **hard** predecessor edges: `G46` from
  `SP-CONTROL-PLANE-AUTHORITY` and `G65` from `SP-PLATFORM-ACCESS`. Its soft edges are `G66`
  (`SP-DELIVERY-AUTOMATION`) and `G67` (`SP-ENVIRONMENT-REQUESTS`).
- Its two cited decisions, `DT` (tenancy) and `DG` (prerequisite grouping), are **decided**
  (2026-07-11 and 2026-07-10). Neither blocks.
- The only live decision blocker on the identity branch is **`DPROV-IDP`** (`unresolved`, owner
  Security; options `GitHub OIDC` / `GitLab OIDC` / `Google OIDC`). The portfolio's other
  unresolved decisions — `DO`, `DR`, `DPROV-REMOTE` — do not fall on this route.
- Three nodes have **zero blockers** today: `CAP-PROVIDER-CATALOG` (no predecessors at all),
  `CAP-DEPLOYMENT-SPEC`, and `PORT-IDENTITY`.
- `CHG-FIRST-IDENTITY-ADAPTER` sits at `blocked_placeholder`, blocked only by `DPROV-IDP` —
  its other two cited decisions, `DP` and `DT`, are already decided.
- **`SP-4-control-plane-core.md` is stale.** Its scope note (lines 19–24) and success criterion
  (lines 87–91) treat "one adapter globally at init vs. per-instance selection" as open. That is
  decision `DP`, decided 2026-07-10 as *"one adapter globally at init"*.
- **Governance gap.** `SP-4` lists the control-plane transport/stack choice as an open decision,
  but no corresponding record exists in `portfolio.json` `decisions[]`. This route closes it as
  `DEC-CP-STACK`.
- **No deterministic validator exists.** `platform-subproject-governance` requires that every
  plan reference resolve "under the deterministic validator". No such validator exists in `src/`,
  `tests/`, or as a script; no test references the portfolio at all.
- **No HTTP surface exists.** Runtime dependencies are `cryptography`, `pydantic`, `pyyaml`,
  `typer`. The sole entry point is the `forge` CLI. `openspec/changes/` has no active change.
- Existing `decompositions[]` declare `changed_line_forecast.hard_gate: 400`. `SP-4` carries seven
  scope bullets and three open decisions, so it does not fit a single SDD change.

## The route

Seven changes. Two fronts run in parallel; three decision gates.

```
CHG-00  PORTFOLIO-VALIDATOR ····················· makes CHG-0 verifiable
CHG-0   ADOPT-UI-ROUTE ························· governance

        ┌──────────────────────────────┬─────────────────────────────┐
CHG-1   │ PROVIDER-CATALOG             │ CHG-2  SP4A-INSTANCE-REGISTRY │
        │ zero blockers, starts today  │ pure domain, no framework    │
        └──────────────┬───────────────┴──────────────┬──────────────┘
                       │                              │
                       │        CHG-3  SP4B-REGISTRY-POSTGRES
                       │               ↑ gate: DEC-CP-STACK
                       └───────────────┬──────────────┘
                                       │
                       CHG-4  SP4C-CONTROL-PLANE-EDGE
                              read-only API + composition root
                              + on-read reconciliation
                                       │
                       CHG-5  OPS-UI-READONLY  ← the visible surface
                              ↑ gates: DEC-UI-PARTIAL, DEC-UI-STACK

DEFERRED — closes the SP-OPERATIONS-UI acceptance later:
        PORT-IDENTITY → CHG-FIRST-IDENTITY-ADAPTER → SP-PLATFORM-ACCESS
                        ↑ gate: DPROV-IDP
```

`CAP-PROVIDER-CATALOG` is a hard predecessor of `SP-4` as a whole, but not of a pure instance
registry contract. Only the composition root (`CHG-4`) needs to know which adapters are approved.
`CHG-1` and `CHG-2` therefore start the same day; `CHG-1` need only land before `CHG-4`.

`DPROV-IDP` leaves the critical path entirely. That is the point of this sequencing.

## Decomposition contracts

Each new package follows the repository's existing triple: an entry in `root_packages`, an entry in
`[tool.hatch.build.targets.wheel] packages`, and a `"Core never imports X"` forbidden contract.

| # | Change | Package | Inputs | Key outputs | Forecast |
|---|---|---|---|---|---|
| 00 | `CHG-PORTFOLIO-VALIDATOR` | — | — | `tests/portfolio/test_portfolio_integrity.py` | ~200 |
| 0 | `CHG-ADOPT-UI-ROUTE` | — | `portfolio.json` | 3 decisions, 7 decompositions, UI slice item | ~250 |
| 1 | `CHG-PROVIDER-CATALOG` | `odoo_forge/provider_catalog/` | `DP` (decided) | approved-adapter catalog spec + types | ~300 |
| 2 | `CHG-SP4A-INSTANCE-REGISTRY` | `odoo_forge/instance_registry/`, `ports/` | `CAP-TENANCY`, `CAP-RESOURCE-OWNERSHIP` | `InstanceRegistry` port + domain types | ~330 |
| 3 | `CHG-SP4B-REGISTRY-POSTGRES` | `odoo_forge_instances_postgres` | `CHG-2`, `DEC-CP-STACK` | persistence adapter + conformance tests | ~350 |
| 4 | `CHG-SP4C-CONTROL-PLANE-EDGE` | `odoo_forge_server` | `CHG-1`, `CHG-3`, `DEC-CP-STACK` | read-only API, composition root, on-read reconciliation | ~380 |
| 5 | `CHG-OPS-UI-READONLY` | *(none new)* | `CHG-4`, `DEC-UI-PARTIAL`, `DEC-UI-STACK` | templates + view logic inside `odoo_forge_server` | ~300 |

All forecasts sit under the `hard_gate: 400`. Verification for every change: `C37`–`C41`
(`pytest`, `lint-imports`, `mypy`, `ruff`, `uv build`). Rollback per change follows the existing
formula: *deactivate if active; revert listed outputs*.

### Naming constraint

`odoo_forge_registry` already exists and means the **image** registry (GHCR). Naming the instance
registry's persistence adapter `odoo_forge_registry_postgres` would read as a GHCR-over-Postgres
adapter to anyone scanning the tree later. Hence `odoo_forge_instances_postgres`.

## Decision gates

| Decision | Owner | Blocks | Status |
|---|---|---|---|
| `DEC-CP-STACK` | Architecture | `CHG-3`, `CHG-4` | new — closes the governance gap |
| `DEC-UI-PARTIAL` | Security + Product | `CHG-5` | new — admits a partial UI slice |
| `DEC-UI-STACK` | Experience | `CHG-5` | new — collapses SP-9's three open decisions |

### `DEC-CP-STACK` consequences

Two consequences are concrete `pyproject.toml` edits, not abstractions:

1. The chosen web framework and PostgreSQL driver are **added to `forbidden_modules`** of the
   *"Core never imports infrastructure or framework"* contract, which today lists `docker`,
   `boto3`, `kubernetes`, `git`, `typer`, `subprocess`, `requests`, `httpx`. This is `SP-4`'s
   success criterion — *"API framework and persistence live in an adapter/edge layer, never
   imported by `odoo_forge` core"* — made executable.
2. It introduces the repository's **first HTTP runtime dependency**. For a single-maintainer
   project, small surface area is a selection criterion, not a preference.

### `DEC-UI-STACK` recommendation

Server-rendered from the same process as the API edge: no SPA build, no realtime transport,
refresh by polling. This answers all three of `SP-9`'s open decisions (stack, SSR vs. SPA,
polling vs. push) with one cheap answer, and it means `CHG-5` adds **no new package and no new
dependency** — only views inside the edge that already exists. An SPA would add a Node toolchain,
a build step, and a second artifact to version.

### `DEC-UI-PARTIAL` and its written cost

A UI without RBAC over a control plane that lists instances exposes tenant and instance topology,
even read-only. `CHG-5`'s acceptance criteria must therefore fix, in writing:

- bind to localhost only;
- single operator;
- explicit prohibition on being archived as production-ready.

If that is not recorded, in three months nobody remembers why that surface has no login.

## Governance mechanics

### `G65` is not relaxed

The governance spec fixes the lifecycle vocabulary: `proposed` requires a gap and no delivery
claim; **`partially delivered` requires evidence plus a gap**; `achieved` requires every acceptance
satisfied. Item `kind` admits `sdd_change`, and four such items already exist.

The route therefore leaves the graph intact:

- `SP-OPERATIONS-UI` keeps both hard edges (`G46`, `G65`) and stays `proposed`.
- The slice enters as a new item `CHG-OPS-UI-READONLY`, kind `sdd_change`, with a hard edge only
  to `CHG-4`'s acceptance, and lineage pointing at `SP-OPERATIONS-UI`.
- Once the slice lands, `SP-OPERATIONS-UI` becomes `partially delivered` — evidence (the slice
  exists) plus a gap (no RBAC, no actions). Which is the literal truth.
- `DEC-UI-PARTIAL` records that an `sdd_change` may deliver visible value without satisfying
  `AC-SP-OPERATIONS-UI-READY`.

No edge is mutated and no hard dependency is weakened.

### Why `CHG-00` comes first

`CHG-0` adds seven `decompositions` — one per change on this route, with `CHG-00` and `CHG-0`
themselves recorded retroactively — plus three `decisions` and one item, all carrying
cross-references that must resolve: `edges.from`/`edges.to`, `decision_ids`, `acceptance_ids`,
evidence IDs against `meta.evidence_catalog`, gap IDs against `meta.gap_catalog`. Checking that by
hand is precisely what drifts.

`CHG-00` adds `tests/portfolio/test_portfolio_integrity.py` asserting: valid JSON; every `kind` in
the permitted set; every reference resolves; and the status invariants (`proposed` carries a gap
and claims no delivery; `achieved` has empty gaps and a non-empty `evidence_date`). Landing it
first makes `CHG-0`'s own `C37 pytest` prove something rather than pass vacuously, and it is
reusable for every later portfolio edit.

The `portfolio-state` spec's *"MUST NOT modify any file under `src/` or `tests/`"* requirement is
scoped to that archived refresh, not a universal rule. Keeping `CHG-00` and `CHG-0` separate
nonetheless leaves each diff single-purpose.

## Failure handling

| Failure | Response |
|---|---|
| `DEC-CP-STACK` selects something the core cannot isolate | `CHG-3` stops at `design`, not `apply`. The import-linter contract is the detector: if the framework cannot live in the edge, the decision was wrong and reopens |
| On-read reconciliation reveals real drift in `CHG-4` | Expected outcome, not a failure. The registry yields to backend introspection, never the reverse |
| `DEC-UI-PARTIAL` is rejected | The route survives. `CHG-00` through `CHG-4` remain valid and necessary; only `CHG-5` waits, and the sequencing reverts to building `SP-PLATFORM-ACCESS` first |
| A change exceeds `hard_gate: 400` | It is sliced before proposal. Forecasts are estimates; the gate is measured against the real diff |

### Why reconciliation is not deferred

A state dashboard showing stale state is worse than no dashboard — it reports dead instances as
live. The founding constraint is already written (design line 227: *"ask the backend — never a
parallel registry file that can drift"*). **On-read** reconciliation only, with no periodic job,
keeps this cheap: the local Docker backend already exposes `status`.

## Testing

Strict TDD across all seven changes, which is the repository's active mode. Two existing patterns
carry over:

- **Adapter conformance tests** — `CHG-3` mirrors `tests/pipeline_github/test_conformance.py`:
  the adapter is tested against the port contract, not against its own implementation.
- **Purity gate** — `lint-imports` is the real guard against the framework leaking into the core.
  Not cosmetic lint: it is `SP-4`'s success criterion made executable.

## Non-goals

- No actionable deployment, no `SP-DELIVERY-AUTOMATION`, no `SP-ENVIRONMENT-REQUESTS`.
- No RBAC or identity work on the critical path; the identity branch is deferred, not cancelled.
- No new external-concern port — `SP-4` orchestrates existing ports.
- Not an Odoo-instance admin UI; Odoo owns its own back office.
- No authority claim. Adoption into `portfolio.json` happens through `CHG-0`.

## Known documentation defects

Recorded here, to be fixed by whoever next touches the affected files rather than as part of this
route:

- `SP-4-control-plane-core.md` treats decision `DP` as open; it was decided 2026-07-10.
- `platform-subproject-governance` names the authority `portfolio-plan.json`, while the live file
  is `docs/specs/platform/portfolio.json` per `meta.live_location`. A naming discrepancy, not a
  substantive one.
