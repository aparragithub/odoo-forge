# Review Ledger: Platform Subproject Redefinition

**Artifact parity ID:** `LEDGER-PORTFOLIO-REDEFINITION-V5`

One canonical current row exists per finding ID. Historical narratives were removed because duplicate open/resolved rows made automated gating ambiguous. Product decision evidence remains Engram `#6375`. The concrete-records independent review round (PORT-043…PORT-052) corrected the record-level defects; two findings (PORT-045, PORT-047) were refuted on verification against the plan data rather than patched. A judgment-day dual-blind review then confirmed all record-level fixes and surfaced one surviving BLOCKER (JD-001, folded into PORT-051), now resolved. To end the review→fix→re-review loop, an **exhaustive deterministic validator** (encoding reference resolution, edge acyclicity, single-rooted linear chain, forecast bounds, manifest-per-slice, and manifest path-provenance) replaces LLM sampling as the structural gate; it currently reports **0 violations**. Current gate: **STRUCTURALLY VALIDATED (0 violations) — validator to be promoted to the V1 deliverable and re-run in-tree at final parity**.

| id | lens | severity | status | current evidence |
|---|---|---|---|---|
| PORT-001 | decision | BLOCKER | corrected_pending_review | `design.md` cites and preserves `#6375`. |
| PORT-002 | authority | CRITICAL | corrected_pending_review | JSON authority and field parity are normative. |
| PORT-003 | transitions | CRITICAL | corrected_pending_review | `portfolio-plan.json` enumerates typed transitions with scoped members, evidence, and transfer membership. |
| PORT-004 | ownership | CRITICAL | corrected_pending_review | Atomic source-evidenced transfers include shipped foundations and exact SP-2/SP-8/SP-9/SP-10 exclusions. |
| PORT-005 | status | CRITICAL | corrected_pending_review | Every item has status, dated evidence, acceptance evidence/gaps, decisions, and lineage. |
| PORT-006 | validation | CRITICAL | corrected_pending_review | Stdlib validator, tests, and fixtures only. |
| PORT-007 | SP-2 gate | BLOCKER | corrected_pending_review | Canonical archive artifacts replace hash freshness. |
| PORT-008 | history | BLOCKER | corrected_pending_review | Numeric/founding bodies are immutable. |
| PORT-009 | baseline | BLOCKER | corrected_pending_review | E1–E4 baseline all five untracked archives first. |
| PORT-010 | activation | CRITICAL | corrected_pending_review | Final mode precedes activation; rollback deactivates first. |
| PORT-011 | slices | CRITICAL | corrected_pending_review | Per-file A+D forecasts and parent boundaries supplied. |
| PORT-012 | neutrality | CRITICAL | corrected_pending_review | Provider and other choices remain open decisions. |
| PORT-013 | surfaces | CRITICAL | corrected_pending_review | IDs, links, edges, HTML, Mermaid, SVG covered. |
| PORT-014 | budget | CRITICAL | corrected_pending_review | Proposal is below 450 words. |
| PORT-015 | record bounds | CRITICAL | corrected_pending_review | Start/end markers and parsed parity defined. |
| PORT-016 | scope grammar | CRITICAL | corrected_pending_review | Dotted disjoint scopes and exact SP-1/SP-10 records defined. |
| PORT-017 | transfer completeness | CRITICAL | corrected_pending_review | Project catalog, deployment spec, tenancy, promotion, randomized data, durable requests/quotas included. |
| PORT-018 | evidence | CRITICAL | corrected_pending_review | Local resolution and external syntax-only semantics defined. |
| PORT-019 | offline | CRITICAL | corrected_pending_review | No fresh-clone npm/uv promise or payload required. |
| PORT-020 | overbuilt freshness | BLOCKER | corrected_pending_review | No tree manifest; final validation reads live canonical surfaces. |
| PORT-021 | activation state | CRITICAL | corrected_pending_review | `draft→active` is gated by final mode. |
| PORT-022 | changed-line forecast | CRITICAL | corrected_pending_review | Forecast is additions+deletions, including tooling/fixtures. |
| PORT-023 | hybrid parity | BLOCKER | corrected_pending_review | Filesystem artifacts are saved verbatim to matching Engram topics. |
| PORT-024 | taxonomy | CRITICAL | corrected_pending_review | All seven item kinds exist; decisions have a separate complete schema. |
| PORT-025 | SP-1 overlap | CRITICAL | corrected_pending_review | Delivered registry and unbuilt delivery scopes are disjoint records. |
| PORT-026 | SP-10 split | CRITICAL | corrected_pending_review | Every legacy responsibility is assigned to one of three successors. |
| PORT-027 | edge identity | CRITICAL | corrected_pending_review | Stored edges require concrete semantic `from`/`to` and acceptance ownership. |
| PORT-028 | partial status | CRITICAL | corrected_pending_review | Partial requires delivered evidence plus a gap, exclusively. |
| PORT-029 | staged parity | CRITICAL | corrected_pending_review | `staging` permits absent future surfaces; `final` requires complete parity. |
| PORT-030 | ledger precedence | BLOCKER | corrected_pending_review | Unique current rows and closed-status archive rule defined. |
| PORT-031 | Mermaid derivatives | CRITICAL | corrected_pending_review | Standalone `.mmd` and paired tracked SVG checks required. |
| PORT-032 | HTML/link semantics | CRITICAL | corrected_pending_review | Concrete parser checks and external syntax-only validation defined. |
| PORT-033 | archive proof | BLOCKER | corrected_pending_review | Archive report must record intentional completion and independent final full-context PASS. |
| PORT-034 | slice feasibility | CRITICAL | corrected_pending_review | Every forecast ≤350; actual hard-stop is before 400. |
| PORT-035 | delivery budget | CRITICAL | corrected_pending_review | D4 owns only the compact plan; V18 alone owns reports; every active/future slice has per-file A+D forecast. |
| PORT-036 | portfolio inventory | BLOCKER | corrected_pending_review | Exhaustive item records include shipped Source/Workspace/Backend/Image Registry ports and adapters. |
| PORT-037 | decomposition | BLOCKER | corrected_pending_review | E1–E4, D0–D4, V1–V18, and blocked placeholders instantiate every required field and exact path. |
| PORT-038 | graph semantics | CRITICAL | corrected_pending_review | Concrete semantic-ID edges are enumerated separately from lineage and concern transitions and pass acyclicity checks. |
| PORT-039 | exact transfers | CRITICAL | corrected_pending_review | Atomic evidence-backed rows use source terms, exact SP-9 splits, SP-8-only quota, and SP-10 orphan-reclamation. |
| PORT-040 | staging contract | BLOCKER | corrected_pending_review | Every E/D/V entry has a manifest; bootstrap precedes V1, staging follows, and V18 alone is final. |
| PORT-041 | SP-2 severity gate | BLOCKER | corrected_pending_review | Exact active/archive selectors, report schemas, unique-ledger rules, and independent PASS evidence are normative. |
| PORT-042 | transition grammar | CRITICAL | corrected_pending_review | All transition/transfer members use one validated dotted grammar and exact membership. |
| PORT-043 | reference completeness | BLOCKER | corrected_pending_review | Nine process acceptance IDs (`AC-ARCHIVE-BASELINE`, `AC-AUTHORITY`, `AC-DESIGN-CONTRACT`, `AC-DESIGN-TRACE`, `AC-FINAL`, `AC-LEDGER-UNIQUE`, `AC-PARITY`, `AC-PORTFOLIO-PLAN`, `AC-VALIDATOR`) are now defined in `process_acceptance`; V2's nested input was flattened. |
| PORT-044 | historical aliases | CRITICAL | corrected_pending_review | Every renamed/split item carries `historical_aliases`; `meta.historical_alias_map` resolves all `SP-1`…`SP-10` references. |
| PORT-045 | missing SP-4/9/10 decisions | CRITICAL | refuted | The 12 decision records already cover the blocking product choices and are linked via each item's `decision_ids` (SP-4→DP,DT,DG; SP-9→DT,DG; SP-10 successors→DG+relevant). No open decision is missing; fabricating extras was rejected. |
| PORT-046 | transfer completeness | CRITICAL | corrected_pending_review | Added SP-2 `interface.cli` and `audit.local-operation`, SP-4 `authority.provider-catalog`, SP-3 `provider.catalog-registration`; `CAP-PROVIDER-CATALOG` now receives concerns. |
| PORT-047 | mixed ownership scopes | CRITICAL | refuted | No transfer scope mixes database+filestore+network; `data.capture` and `data.consistency` are already disjoint scopes. SP-10 scopes verified internally consistent. |
| PORT-048 | dependency edges | CRITICAL | corrected_pending_review | `CAP-DURABLE-OPERATIONS` and `CAP-RESOURCE-OWNERSHIP` now edge to consuming workflows (`WF-DATA-COPY`, `WF-PRODUCTION-PROMOTION`, `WF-ENVIRONMENT-REQUEST`) and `SP-RESOURCE-LIFECYCLE`; graph stays acyclic. |
| PORT-049 | linear work chain | BLOCKER | corrected_pending_review | Single root `E1`; `D0` stacks on `E4`; `V1` stacks on `D4`; two independent roots removed. |
| PORT-050 | changed-line counting | CRITICAL | corrected_pending_review | `C1`/`C2` now count staged, unstaged, and untracked lines against `HEAD` via `git add -A --intent-to-add`. |
| PORT-051 | V18 closeout feasibility | BLOCKER | resolved | Judgment-day judge A found `M-V18`/`M-V19` still required archive-dir report paths no prior slice produced (JD-001). Fixed: `M-V18.required_present` now references the change-dir reports `V18` produces; `V19.outputs` enumerate the archive-dir files it relocates. Deterministic validator (`docs/tools/platform_portfolio/validate.py`, prototyped) confirms path-provenance: no manifest requires a path produced only by a later slice. |
| PORT-052 | uncovered source doc | CRITICAL | corrected_pending_review | `docs/diagrams/odoo-forge-current-implementation-guide.md` added to `protected_history_paths` as immutable history (user decision: protect, do not migrate). |

## Machinery Pruned — Decision B (2026-07-10)

After the review→fix loop was diagnosed as living entirely in the self-imposed E/D/V documentation-migration apparatus, that machinery was removed from `portfolio-plan.json`: all 28 E/D/V decompositions, every `slice_manifests` entry, `process_acceptance`, and `fresh_sp2_gate`. The plan now carries only portfolio substance (items, decisions, transitions, transfers, edges, and the four future `CHG-FIRST-*` SDD changes), 116 KB → 66 KB. This **obviates** the machinery-specific findings — PORT-047, PORT-049, PORT-050, PORT-051 (and the manifest/forecast/chain aspects of others): the structures they corrected no longer exist. The traceability findings (aliases, transfers, edges, decisions, taxonomy) remain in force and are gated by `validate.py`.

## Semantic Review — PASS (2026-07-10)

Fresh-context semantic review of the pruned portfolio against `exploration.md` and the SP-1…SP-10 briefs: alias mappings, transfer destinations (including the four added records), dependency edges vs the evidence DAG, decision scoping, taxonomy, and SP-DATA-ENVIRONMENTS exclusions all verified faithful. **0 BLOCKER, 0 CRITICAL, 2 WARNING (non-blocking).** WARNING on SP-RESOURCE-LIFECYCLE quota was assessed and rejected — homing quota there would violate the "quota exactly once at `CAP-TENANCY`; SP-10 transfers no quota" invariant; the plan is correct. WARNING on a direct `CAP-DATA-ARTIFACTS→WF-DATA-COPY` edge is optional polish (already covered transitively).

## Gate Rule

Structural correctness is gated by `docs/tools/platform_portfolio/validate.py` (0 violations, deterministic, exhaustive) plus its unit tests — not reviewer sampling. Independent full-context review confirms semantic correctness of the portfolio records. On PASS, this change may be archived and `SP-DATA-ENVIRONMENTS` (SP-2) unblocks. No per-slice migration gate applies; migrating the docs tree happens through ordinary SDD when scheduled.
