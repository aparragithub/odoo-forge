# Tasks: Fix Roadmap Refresh Verification Closure

## Review Workload Forecast

| Field | Value |
|---|---|
| Historical logical records | Frozen S0 240, S1 180, S2 353, S3 260–360, S4 completed; S5 forecast 190–300 |
| Combined review target | Native staged projection binds all 11 child paths; its high-tier full-4R target and receipt are authoritative, and prior estimates are superseded |
| 400-line budget risk | High |
| Chained PRs recommended | Yes |
| Suggested split | Frozen S0 → S1 → S2 → S3 → S4; new S5 190–300; feature-branch chain |
| Delivery strategy | force-chained |
| Chain strategy | feature-branch-chain |

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: feature-branch-chain
400-line budget risk: High

### Suggested Work Units

| Unit | Goal | Likely PR/base | Focused test command | Runtime harness | Rollback boundary |
|---|---|---|---|---|---|
| 0 | Freeze failed evidence and parent-derived policy inputs | PR 1; tracker branch | `sha256sum`; `git diff --check` | N/A: evidence/planning only | Remove child evidence files only |
| 1 | Add strict RED tests and isolated fixtures | PR 2; PR 1 branch | focused validator tests (expected RED) | N/A: tests-only slice; baseline remains healthy where applicable | Revert test/fixture additions only |
| 2 | Make validator GREEN, refactor, and verify artifacts | PR 3; PR 2 branch | focused, Ruff, then `uv run pytest` | fixed renderer `--check` plus validator CLI | Revert validator/tests/HTML only |
| 3 | Add root parity and renderer/evidence trust-boundary contracts | PR 4; PR 3 branch | focused, Ruff, then `uv run pytest` | renderer; validator CLI with relative and absolute roots | Revert Slice 3 validator/test changes |
| 4 | Advance parent report state without receipt authentication | Historical; S3 branch | focused, Ruff, then `uv run pytest` | failed-state and synthetic PASS probes | Revert Slice 4 parser/tests/evidence records only |
| 5 | Separate staged child dependencies from parent verification | PR 5; S4 branch | focused, Ruff, then `uv run pytest` | renderer; relative/absolute and isolated staged-tree CLI | Revert Slice 5 validator/tests/records/report only |

## Phase 1: Immutable Baseline (Slice 0; frozen)

- [x] 1.1 Before edits, copy parent `verify-report.md` byte-for-byte to `evidence/parent-verify-fail.md`; record and assert SHA-256 `0fbb60e3b0aba12a46cc26a69c57b40ffb26fa1c60adde5946c0ee9018d084c4`, then create the `.sha256` receipt.
- [x] 1.2 Derive the ≤400 authored-line cap and Unit4 exclusion only from parent `tasks.md` guard lines and `apply-progress.md` measured records; record slice boundaries and never alter the failed report.

## Phase 2: Strict RED Tests and Fixtures (Slice 1; frozen)

- [x] 2.1 RED: extend `test_validate.py` with failing tests for canonical apply status, injected fixed-renderer coherence and adversarial executable paths, exact contained guide link, valid unchanged S62, isolated unverifiable-reference removal plus `gap_catalog`, fabricated evidence, and verified HTML ownership/current/target metadata.
- [x] 2.2 RED verification: run focused tests and record targeted failures; confirm the unchanged baseline suite remains healthy where applicable, without implementing production behavior in this slice.

## Phase 3: GREEN, REFACTOR, and Runtime Verification (Slice 2; frozen)

- [x] 3.1 GREEN: update `validate.py` with `RendererResult`/fixed `--check` seam, exact link and metadata contracts, conditional fixture-only evidence-gap handling, canonical status, and immutable snapshot failure codes; keep production S62 accepted.
- [x] 3.2 REFACTOR and artifact correction: simplify pure helpers; update `platform-architecture.html` with exactly one verified ownership marker and current/target sections plus the literal guide link; assert production `portfolio.json` and valid S62 are byte-unchanged unless fresh validation proves invalidity (currently it does not).
- [x] 3.3 Run fixed renderer `--check`, injected tests, validator CLI, Ruff check/format for both validator files, focused tests, and full `uv run pytest`; record exact outcomes.

## Phase 4: Root Parity and Renderer/Evidence Trust Boundary (Slice 3; 260–360 authored, hard ≤400)

- [x] 4.1 RED: keep legacy path/slice helper tests direct-only; native staged review plus SDD verification own scope, Unit4, and high-tier approval.
- [x] 4.2 RED: add a test proving an invalid renderer script is rejected before any renderer process invocation.
- [x] 4.3 RED: add relative/absolute-root parity tests for valid, missing, fabricated, and gap evidence plus matching CLI outcomes.
- [x] 4.4 GREEN/REFACTOR: remove helper runtime wiring; bind renderer bytes before invocation and retain root normalization; keep dispatchers acyclic.
- [x] 4.5 Verify focused/full pytest, Ruff check/format, renderer, relative and absolute validator CLI, snapshot/portfolio hashes, and `git diff --check`/whitespace; rollback only Slice 3 validator/test files and evidence.

## Phase 5: Parent-Report Advancement (Slice 4; parser superseded by native parent verification)

- [x] 5.3 GREEN/REFACTOR: retain immutable snapshot/hash validation only; native parent SDD verification owns canonical PASS and authority checks.

## Phase 6: Staged Dependency Separation (Slice 5; 190–300 authored, hard ≤400)

- [x] 6.1 RED: prove the child repository validator ignores parent apply-progress status, while the parent SDD contract rejects noncanonical first/unique status.
- [x] 6.2 RED: define and test exactly 13 authoritative staged paths (prior 11 plus Mermaid source and SVG), with zero foreign parent OpenSpec paths; staged-tree tests fail on stale staged Mermaid even when the worktree is clean, and dirty-worktree evidence is non-authoritative.
- [x] 6.3 GREEN/REFACTOR: remove the parent status gate from child validator/tests without weakening renderer, diagram, or stale-claim gates; wire isolated staged-tree validation and the exact 13-path target.
- [x] 6.4 Native staged orchestration passed against the isolated exact index tree; record scope, CLI, hash, and whitespace evidence, while native review binds the final post-recording tree.
- [x] 6.5 Record rollback as Slice 5 validator/tests/staged-tree/records/report only; keep the parent contract and foreign OpenSpec paths outside the slice.

## Post-Implementation Lifecycle (Orchestrator; uncheckboxed)

1. After Slice 5 changes staged dependencies or bound bytes, obtain fresh child review, bind it, and reverify the child.
2. Only after child review/binding and reverification pass, incorporate the child and create, approve, and bind a new combined parent lineage; then run parent review and reverification.
