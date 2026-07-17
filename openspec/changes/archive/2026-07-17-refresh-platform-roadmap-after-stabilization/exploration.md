## Exploration: refresh-platform-roadmap-after-stabilization

### Current State

The checked-out base is `bbfd16646bd72e2b3ff20c7dea935ae70eecf26e` (PR #80 merge), and the worktree is clean. The merged state is materially ahead of the current guidance:

- Docker PostgreSQL security authority is implemented and its change is archived at `openspec/changes/archive/2026-07-15-database-adapter-security-authority/`. It includes durable ownership authority, ref-only credential injection, restore/artifact handoffs, and the real-Docker Phase 5 evidence added by commit `265debe`.
- Backend planning now consumes validated `MountPlanningView` evidence, and the materialized-state change is archived at `openspec/changes/archive/2026-07-15-make-backend-planning-consume-materialized-state/`. `src/odoo_forge/backend/plan.py` is pure and derives mounts from evidence; this is no longer the roadmap's next implementation unit.
- The current roadmap still says Unit 3 is the next action, dates its baseline to PR #64, calls the first database adapter merely “ready for proposal,” and describes the database adapter as a future unit. Those claims are stale and contradict the archived changes and current implementation.
- `README.md` still says published-layer resolution/override application remain incomplete. That is false after the archived manifest semantics change. Its status also says there is no standalone database adapter, which is now false; its provider-neutral-foundation wording should distinguish the implemented Docker PostgreSQL adapter from still-unwired provider-neutral consumers.
- `docs/diagrams/odoo-forge-current-implementation.mmd` and its generated SVG still show only a `DatabaseProvider` contract and “no operational adapter.” The current guide repeats that claim in its canonical note and implementation summary. The Mermaid source is authoritative for the SVG; the SVG must be regenerated, never hand-edited.
- `portfolio.json` already marks `ADAPTER-DATABASE-DOCKER` and `CHG-FIRST-DATABASE-ADAPTER` as achieved and retains the live-location authority model. However, `python docs/tools/platform_portfolio/validate.py --root .` currently reports two CRITICAL `bad-ac-ev` violations for missing evidence `S62`, despite prior roadmap prose claiming zero violations. This must be classified and fixed or explicitly documented; it is not safe to claim portfolio validation is clean.
- OpenSpec has two non-archived directories: `CHG-FIRST-DATABASE-ADAPTER` and `sp-data-environments`. The former is stale active residue whose implementation is now archived; the latter remains genuinely blocked with proposal/spec/design/tasks and unchecked implementation work. Archived directories are audit history and must not be rewritten, including archive reports and review evidence.
- The historical `2026-07-08-platform-roadmap.md`, Phase 2 roadmap, dated design documents, and platform HTML are lineage/review artifacts. They must remain protected unless their policy permits a redirect or annotation. Current guidance must point to them as historical rather than silently rewriting their claims.

Actual merged lineage through the requested base is: PR #73 database security-authority implementation, PR #74/related Phase 5 real-Docker acceptance evidence, PR #77 database-adapter archive, PR #78 materialized-state implementation, PR #79 archive, and PR #80 archive-report traceability correction. The exact PR mapping and receipts should be verified from the archived reports before proposal work; do not infer missing verify artifacts.

### Affected Areas

- `docs/specs/2026-07-14-stabilization-roadmap.md` — primary current-status and execution-order source; must advance beyond Unit 3, reconcile Unit 5/Phase 5, and separate the later Unit 4 runtime-risk recheck.
- `docs/specs/platform/portfolio.json` — canonical product/dependency/evidence authority; inspect the `S62` catalog/reference defect and ensure any status/lineage update is evidence-backed.
- `docs/tools/platform_portfolio/validate.py`, `docs/tools/platform_portfolio/test_validate.py` — validator contract and executable integrity gate; validation behavior must remain deterministic.
- `README.md` — current repository status and roadmap summary; contains stale published-layer and database-adapter claims.
- `docs/diagrams/odoo-forge-current-implementation.mmd` — authoritative current implementation diagram source; add the operational Docker PostgreSQL adapter and correct foundation labels/edges.
- `docs/diagrams/odoo-forge-current-implementation.mmd.svg` — derived generated output; regenerate only through `docs/diagrams/render-current-implementation.sh` and verify with `--check`.
- `docs/diagrams/odoo-forge-current-implementation-guide.md` — review-facing explanation and canonical note; reconcile language/status claims with the Mermaid source and current implementation.
- `docs/specs/platform/platform-architecture.html` — inspect as a review-facing/possibly protected artifact; update only if its policy/source relationship permits, otherwise add a redirect/annotation from current guidance.
- `openspec/changes/CHG-FIRST-DATABASE-ADAPTER/` — stale non-archived active residue; classify for archival/redirect handling, without rewriting historical evidence.
- `openspec/changes/sp-data-environments/` — active but blocked; retain as active and update only cross-links/status references required by authoritative documentation.
- `openspec/specs/{docker-postgresql-database-adapter,docker-database-ownership-authority,credential-materialization,local-backend,manifest}/spec.md` — normative current contracts and cross-link targets; do not duplicate their requirements in prose.
- `openspec/changes/archive/2026-07-15-database-adapter-security-authority/` and `openspec/changes/archive/2026-07-15-make-backend-planning-consume-materialized-state/` — immutable evidence sources for traceability; read, link, and classify, never edit.
- `src/odoo_forge/backend/plan.py` and `src/odoo_forge_postgres_docker/provider.py` — implementation evidence used to validate documentation claims; not in scope for this documentation/governance refresh.

### Approaches

1. **Authority-first documentation reconciliation** — classify each artifact as authoritative, derived, historical/protected, active OpenSpec, or review-facing; update only current guidance, portfolio evidence/catalog references, allowed redirects, and generated outputs from their sources.
   - Pros: preserves audit lineage, prevents duplicated normative requirements, exposes the `S62` validator inconsistency, and produces a small reviewable change.
   - Cons: requires an explicit inventory and source/derived policy for the HTML and diagrams.
   - Effort: Medium

2. **Blanket documentation rewrite** — rewrite all roadmap, README, diagrams, HTML, and archived/current OpenSpec text to match HEAD.
   - Pros: superficially uniform.
   - Cons: violates protected-history and archive rules, risks fabricating or losing evidence, and makes review/rollback difficult.
   - Effort: High

### Recommendation

Use authority-first reconciliation. Treat `portfolio.json` as product/dependency/status authority, canonical OpenSpec specs and archived receipts as normative/evidence authority, the stabilization roadmap as current sequence authority, Mermaid as diagram source authority, and the SVG as generated output. The proposal should define an exact update matrix rather than a file-wide rewrite: update the roadmap, README, current implementation guide/Mermaid/SVG, permitted cross-links, and any portfolio validator/evidence correction proven by archived receipts; preserve historical and protected documents with redirects or annotations only where allowed. Keep documentation/governance refresh separate from a later Unit 4 registry/Git/workspace runtime-risk recheck. Plan forced chained PR slices under the 400-line authored review budget, for example: (1) inventory/portfolio/roadmap authority and validator correction, (2) README and current-guide/source diagram reconciliation, (3) generated SVG and review-facing cross-links/validation receipt.

Required validation should include `python docs/tools/platform_portfolio/validate.py --root .`, the validator unit tests, OpenSpec active/archive inventory checks, targeted stale-claim searches, Mermaid `docs/diagrams/render-current-implementation.sh --check`, and the repository's documentation/test commands as applicable. The proposal must identify the exact source of `S62` and refuse to mark it resolved if no receipt exists.

### Risks

- `S62` may represent a missing evidence-catalog entry, a stale portfolio reference, or a traceability defect; changing it without the archived receipt would fabricate governance evidence.
- The active `CHG-FIRST-DATABASE-ADAPTER` directory can be mistaken for an unimplemented change; classification must preserve its content while making the archived implementation the current lineage target.
- The current guide is Spanish while requested technical artifacts are English; changing language wholesale would expand scope. Prefer correcting factual claims and retain language unless a separate documentation decision authorizes translation.
- HTML ownership/source policy is not established by the inspected files; editing it blindly could violate protected-history or generated-artifact rules.
- Updating the roadmap may expose that Unit 4 is a future runtime-risk recheck rather than a prerequisite for the documentation refresh; do not combine those technical investigations.
- Generated SVG changes can exceed the review budget or include nondeterministic noise; use the pinned renderer and byte-for-byte check.

### Ready for Proposal

Yes. Proceed to proposal with the classification/update matrix, evidence-backed `S62` decision, protected-history rules, exact validation commands, and three forced chained review slices capped at 400 authored changed lines each. Do not create proposal/design/spec/tasks or implement code during exploration.
