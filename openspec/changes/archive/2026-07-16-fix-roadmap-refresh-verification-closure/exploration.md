## Exploration: fix-roadmap-refresh-verification-closure

### Current State
The parent change `refresh-platform-roadmap-after-stabilization` is intentionally blocked at `sdd-verify`. Its current PR3 candidate passes the focused tests and product suite, but the live verification report records seven independent blockers: the validator rejects the canonical `Apply Complete — Ready for sdd-verify` status; it checks Mermaid/SVG existence rather than byte coherence; it accepts any resolvable HTML link instead of the exact current-guide target contained in the repository; and three specification scenarios have no runtime coverage (S62 removal with explicit gap reporting, refusal to update HTML with unverified ownership, and rejection of oversized/cross-scope slices). Ruff lint and format also fail in both validator files.

The repository validator is a pure standard-library gate in `docs/tools/platform_portfolio/validate.py`. Repository checks currently cover S62 containment/existence, active inventory, roadmap claims, protected hashes, apply-progress status, HTML labels/links, stale claims, and fixed renderer shape. The current HTML check only asks whether *some* parsed link resolves. The renderer check validates the shell script contract and file existence but never compares regenerated output bytes. The test fixture can support focused temporary-repository tests, but currently models S62 as a valid archived pointer and has no planning-slice or ownership decision helper to exercise.

The parent spec assigns all seven behaviors to this validator/test boundary and excludes Unit4 registry/Git/workspace runtime work. Parent `tasks.md` and `apply-progress.md` still call historical review lineage `review-fd6c0911698f1f96` the completing receipt, while `verify-report.md` identifies current approved authority as `review-b5ad473e370d56c2`, generation 1. That reference can be corrected only as a truthful evidence reconciliation; it is not required to implement the validator fixes.

### Affected Areas
- `docs/tools/platform_portfolio/validate.py` — correct final-status acceptance; add deterministic Mermaid-to-SVG byte verification through the existing fixed renderer boundary; require the exact current-guide link and repository containment; expose explicit S62 gap/removal and ownership/slice validation helpers without legacy remediation tooling; format/lint cleanup.
- `docs/tools/platform_portfolio/test_validate.py` — add focused RED/GREEN coverage for all seven blockers using temporary repositories and pure validation inputs; reformat/import cleanup.
- `openspec/changes/refresh-platform-roadmap-after-stabilization/specs/platform-portfolio-documentation-integrity/spec.md` — parent normative scenarios define the required behavior; read-only dependency unless child design/spec explicitly amends the contract.
- `openspec/changes/refresh-platform-roadmap-after-stabilization/verify-report.md` — failed evidence and exact blocker baseline; child implementation must preserve it as historical verification input and trigger parent re-verification afterward.
- `openspec/changes/refresh-platform-roadmap-after-stabilization/tasks.md` and `apply-progress.md` — possible minimal lineage-reference reconciliation from `review-fd6c0911698f1f96` to `review-b5ad473e370d56c2`; do not rewrite unrelated chronology or parent scope.
- `openspec/changes/fix-roadmap-refresh-verification-closure/` — child OpenSpec artifacts; this exploration is the only artifact created in this phase.

### Approaches
1. **Focused validator-closure child** — amend the validator policy and tests in place, keeping the parent candidate and its failed verify report as the baseline; add only the smallest helpers/fixtures needed to make each specified scenario executable.
   - Pros: directly closes every recorded blocker at its declared authority boundary; preserves parent history; avoids Gentle AI changes and legacy remediation transactions; supports independent child review and rollback.
   - Cons: renderer byte verification must choose a deterministic test seam that does not make unit tests depend on Docker; planning-slice and ownership semantics need explicit, narrow input contracts.
   - Effort: Medium

2. **Evidence-only parent reconciliation** — update status/lineage prose and record external renderer/test evidence without extending validator enforcement.
   - Pros: smaller textual diff.
   - Cons: cannot satisfy R3-001/R3-002 or the three untested normative scenarios; live verification would remain non-compliant and the child would be unable to close the parent.
   - Effort: Low, but insufficient

### Recommendation
Use the focused validator-closure child. Treat the blocked parent as the dependency and amendment target: preserve its current candidate and failed `verify-report.md`, then implement only the seven closure behaviors in the validator/test boundary. Keep renderer execution behind a fixed-argument, injectable or explicitly testable byte-comparison seam so ordinary focused tests remain deterministic while live verification can prove real Mermaid→SVG coherence. Make the exact guide path a named repository-relative contract and reject absolute, traversal, external, or merely alternative links. Represent S62 removal as absence plus an explicit gap-catalog/report assertion, and model HTML ownership as a precondition whose false/unverified state produces a refusal violation rather than silently permitting updates. Add a small pure slice-policy validator for the 400 authored-line limit and Unit4 path exclusion, backed by oversized and cross-scope fixtures.

The child should not invoke, inspect, or depend on Gentle AI legacy remediation tooling. After child review and implementation, rerun the parent focused/full verification against the same candidate lineage, regenerate a new canonical verify report, and only then resolve the parent change. Correct historical review references only if the exact current approved receipt is available and the edit makes the chronology truthful; otherwise report the mismatch without inventing evidence.

Expected authored scope is concentrated in the two validator files, likely within one forced chained slice and below the 400-line budget; generated SVG remains generated evidence rather than authored budget. Rollback is a reverse child-slice revert: restore validator/tests and any narrowly reconciled parent tracker lines, never rewrite protected archives, receipts, or generated SVG by hand. Test strategy is RED/GREEN per blocker, focused validator tests first, then Ruff, full pytest, live validator CLI, deterministic renderer `--check`/byte identity, and parent `sdd-verify`.

### Risks
- A renderer subprocess in the validator could make tests environment-dependent; isolate command execution behind a deterministic seam and retain a live integration assertion for actual byte identity.
- “Exact current-guide link” must be defined as the repository’s canonical relative path, not merely any link resolving inside the repository; otherwise R3-002 remains open.
- S62 gap reporting must distinguish intentional removal from a missing/broken pointer and must not fabricate replacement evidence.
- Ownership and slice validation are documentation policy checks; broadening them into Unit4 runtime or Gentle AI remediation would violate scope.
- Parent task/progress lineage edits can invalidate the current review evidence revision if done beyond the minimal truthful reference correction; rebind/review only through the normal parent workflow.

### Ready for Proposal
Yes. The proposal should state that this is a corrective child amending the blocked parent’s PR3 verification contract, enumerate the seven closure behaviors, preserve the parent failed evidence as input, explicitly exclude Gentle AI and Unit4, define the child-to-parent reverification sequence, and budget one focused validator/test slice under 400 authored lines.
