# Design: Fix Roadmap Refresh Verification Closure

## Technical Approach

Preserve immutable evidence, controlled parent PASS advancement, renderer, guide/HTML, root, S62, Ruff, and native-authority contracts. The next slice removes foreign parent OpenSpec status from the child while adding Mermaid/SVG to its staged boundary.

## Architecture Decisions

| Option | Tradeoff | Decision |
|---|---|---|
| Child reads parent `apply-progress.md` | Couples child to foreign OpenSpec | Remove that check; parent verification owns first/unique canonical status. |
| Verify dirty worktree | Convenient but masked two staged failures | All runtime gates execute against an isolated materialization of the native staged candidate. |
| Self-declared paths | Cannot authenticate identity | Native compact receipt is sole tree/path authority; planning helpers remain non-authoritative. |
| Omit diagrams from child target | Recreates stale-claim/coherence failure | Expand prior 11-path target with Mermaid and SVG, exactly 13 paths, excluding every parent OpenSpec path. |
| Rewrite failed history | Loses audit evidence | Preserve both reviews; record failed-report identity, then remove stale child `verify-report.md` before review. |

## Data Flow

```text
native staged target (13 paths) -> isolated tree
  -> child validator: renderer/coherence + stale documentation
  -> native review validate/bind -> child sdd-verify
combined parent staged target -> native validate/bind -> parent sdd-verify
  -> canonical status + diagram + staged/worktree checks
```

## Next-Slice File Changes

| File | Action | Description |
|---|---|---|
| `docs/tools/platform_portfolio/validate.py` | Modify | Remove parent status coupling; retain other gates. |
| `docs/tools/platform_portfolio/test_validate.py` | Modify | Add staged-independence and isolated-tree RED/GREEN coverage. |
| `docs/diagrams/odoo-forge-current-implementation.mmd` | Stage | Authoritative child documentation input. |
| `docs/diagrams/odoo-forge-current-implementation.mmd.svg` | Stage | Renderer-derived output; generated lines excluded only from authored budget. |
| Child `verify-report.md` | Delete before review | Preserve identity in apply history. |
| Child `design.md`; later `tasks.md`/`apply-progress.md` | Modify by phase | This phase edits design only. |

## Interfaces / Contracts

- `validate_repository(root, plan)` no longer reads `openspec/changes/refresh-platform-roadmap-after-stabilization/apply-progress.md` and cannot emit `apply-progress-status`.
- `validate_documentation(root, run_renderer)` retains staged Mermaid/HTML, renderer `--check`, Mermaid/SVG presence, and existing failure codes.
- Child native target is the existing 11 paths plus `docs/diagrams/odoo-forge-current-implementation.mmd` and `.mmd.svg`; no `openspec/changes/refresh-platform-roadmap-after-stabilization/**` path is permitted. This list describes intended scope; only the native receipt authenticates actual tree/paths.
- Parent verification requires one canonical status as the first level-two heading, runs diagram gates on the combined staged tree, and rejects receipt/binding versus materialized-byte mismatch.
- Before deletion, apply history records failed schema, revision `sha256:bd614e7d...d0d4`, verdict, lineage `review-f7800f3da599c36e`, binding revision, tree `351c99bee3427defad95a4da95337abe94b7cdf3`, and output hashes. Only new child verification writes a report.

## Strict-TDD Strategy

| RED case | Expected result |
|---|---|
| Child fixture has any parent apply status | Child result is unchanged; no `apply-progress-status`. |
| Staged Mermaid is stale, SVG mismatches, or renderer fails | Child validator rejects with existing documentation/renderer code. |
| Dirty worktree passes while isolated staged tree fails | Child review/verification fails; worktree result is non-evidence. |
| Parent tree has stale/multiple/non-first status or stale diagram | Reject before PASS. |
| Receipt paths omit either diagram or include parent OpenSpec | Native child gate rejects scope; repository validator does not claim authority. |

Run RED first, then GREEN/refactor, Ruff, focused/full pytest, renderer, both CLI root forms, and native post-apply validation on the isolated staged tree.

## Threat Matrix

| Boundary | Applicability | Safe/failure behavior | Planned RED test |
|---|---|---|---|
| Documentation-like paths | Applicable | Only approved renderer executes; Mermaid/SVG are data. | Decoy executable path is never run. |
| Git repository selection | Applicable | Native worktree/common-dir and receipt select candidate. | Wrong repository/tree rejects. |
| Commit state | Applicable: staged vs dirty | Execute staged tree only; dirty bytes never satisfy evidence. | Staged fail/worktree pass remains FAIL. |
| Push state | N/A: no push automation. | — | — |
| PR commands | N/A: no PR command composition. | — | — |

## Review Workload, Rollout, and Rollback

| Field | Value |
|---|---|
| Estimated authored changed lines | Next slice: 180–320 |
| 400-line budget risk | Medium |
| Chained PRs recommended | Yes |
| Review impact | New high-tier 13-path compact child review; generated SVG stays in identity/digest |
| Delivery / chain | force-chained / feature-branch-chain |

Decision needed before apply: No
Chained PRs recommended: Yes
400-line budget risk: Medium

After implementation: remove stale report → new child review/bind/reverify → incorporate → combined parent review/bind/reverify. Roll back this slice only; restore the failed report solely with its exact historical candidate. Never mutate frozen or prior review evidence.
