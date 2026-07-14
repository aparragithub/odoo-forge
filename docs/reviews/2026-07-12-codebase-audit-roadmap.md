# Codebase Audit Outcome and Risk-Ordered Roadmap

The bounded full-codebase review approved the immutable target with no blocker and no
required correction. It admitted five evidence-backed INFO/WARNING findings: one possible
credential disclosure boundary, one reclassified lifecycle-authority concern, two Docker deadline
semantics issues, and one CLI diagnostic consistency issue. These findings can be corrected
through ordinary focused changes and reviews; WARNING or INFO severity does **not** automatically
justify Judgment Day.

The recommended order is security boundary first, future store conformance second, deadline
semantics third, CLI readability fourth, then the three defect units exposed by characterization,
followed by residual no-defect characterization.
An optional cross-module Judgment Day is gated until all bounded work is complete and is warranted
only if the combined immutable delta creates an extraordinary integration risk.

## Review Baseline

| Item | Immutable value |
| --- | --- |
| Branch and commit | `main` at `e149f2b194aa9e1f0c8463ef41c300be0a333314` |
| Worktree | Clean at review start and completion |
| Lineage | `review-full-head-e149f2b194aa` |
| Target identity | `sha256:1bddc31549d659583ae6f1462dc909fd516677f0729982e113dd1a1b445296f9` |
| Scope | Full tree: 337 files, 36,627 lines |
| Review policy | High tier, ordinary bounded 4R review |
| Receipt | `.git/gentle-ai/review-transactions/v2/review-full-head-e149f2b194aa/review-receipt.json` |
| Terminal state | Approved |

The native high-tier review applied all four lenses to the complete target. The user-requested
deep-focus map prioritized reliability for `src/odoo_forge` core/domain, resilience for
`odoo_forge_docker` and `odoo_forge_git`, risk for `odoo_forge_registry`,
`odoo_forge_workspace`, and `factory`, and readability for `odoo_forge_cli`.

Verification passed at the reviewed target:

- Import Linter: 6 contracts kept.
- Ruff: check and format verification passed.
- mypy: 104 files passed.
- pytest: 475 passed, 1 deselected, 98% coverage.

## Findings at a Glance

| ID | Concern | Evidence | Classification | Roadmap |
| --- | --- | --- | --- | --- |
| `R1-001` | Workspace errors may expose credentials from raw Git stderr | `src/odoo_forge_workspace/provider.py:141`, `src/odoo_forge_workspace/provider.py:203-206` | Inferential; causality unknown | Work unit 1 |
| `R3-001` | The audit questioned direct construction of `CLOSED` with residual cleanup; trusted materialization deliberately permits it | `src/odoo_forge/ports/durable_operation_store.py:16-20`, `:34-51`, `:96-110`; `tests/ports/test_durable_operation_store.py:306-367` | Reclassified: not actionable in the current core value model | Work unit 2 |
| `R4-001` | PostgreSQL polling can substantially exceed its readiness timeout | `src/odoo_forge_docker/provider.py:386-388`, invocation timeout at `src/odoo_forge_docker/provider.py:448` | Deterministic; causality unknown | Work unit 3 |
| `R4-002` | Odoo health polling can substantially exceed `health_wait_timeout` | `src/odoo_forge_docker/provider.py:402-404`, invocation timeout at `src/odoo_forge_docker/provider.py:448` | Deterministic; causality unknown | Work unit 3 |
| `R2-001` | `stop`, `logs`, and `exec` emit raw multi-line Pydantic errors | `src/odoo_forge_cli/main.py:519`, catches at `src/odoo_forge_cli/main.py:546`, `:570`, and `:603` | Deterministic; introduced | Work unit 4 |

No finding was admitted for `odoo_forge_git`, `odoo_forge_registry`, or `factory` during the original
review. Subsequent characterization reproduced one credential-safe failure-boundary defect in each
adapter and one temporary-secret cleanup defect in factory. The user authorized splitting the
former work unit 5 into four bounded units on 2026-07-12; these are discoveries, not completed fixes.

## Decision Gates

| Gate | Decision |
| --- | --- |
| G0: baseline integrity | Before each unit, record the starting commit/tree and confirm unrelated changes are excluded from its evidence. |
| G1: credential behavior | If a reproducible Git stderr sample can expose userinfo or tokens, treat redaction as a security boundary and complete work unit 1 before all others. If not reproducible, still enforce the safe public-error contract because stderr is untrusted. |
| G2: lifecycle authority | Keep snapshot coherence in `DurableOperationRecord.__post_init__` and transition authority in `DurableOperationStore.resolve_residual`. Apply the persisted-transition requirement when the first concrete durable store is adopted. |
| G3: deadline contract | Define whether configured readiness values are wall-clock deadlines or attempt budgets. Proceed only after tests encode one contract for both PostgreSQL and Odoo. |
| G4: diagnostic contract | Preserve field location and message while enforcing stable, single-line CLI output for all manifest-validation paths. |
| G5: no-finding characterization | Add tests only for concrete high-risk boundaries that are not already characterized; do not manufacture findings or broad refactors. |
| G6: extraordinary review | Run Judgment Day only if the aggregate post-fix delta crosses security, lifecycle, and process-boundary semantics in a way ordinary focused reviews cannot confidently isolate. Otherwise finish with ordinary integration review. |

## Dependency-Ordered Work Units

### 1. Enforce the Workspace Credential-Redaction Boundary

**Finding:** `R1-001`

**Objective:** Ensure no raw Git diagnostic can expose credentials embedded in a remote URL through
`WorkspaceError` or CLI output, while retaining enough safe context to diagnose the failed Git
subcommand.

| Planning field | Boundary |
| --- | --- |
| Likely files | `src/odoo_forge_workspace/provider.py`; `tests/adapters/test_workspace_provider.py`; relevant CLI projection tests only if the public boundary needs end-to-end proof |
| Tests and evidence | Simulate clone stderr containing HTTPS userinfo, token-like values, and a credential-bearing URL; assert exceptions and CLI stderr contain none of them. Cover ordinary non-secret stderr to prove the safe diagnostic remains useful. |
| Exit criteria | Every workspace subprocess failure emits a bounded, credential-free public message; timeout and non-zero-exit paths share the policy; focused adapter and CLI tests pass. |
| Rollback boundary | Revert only the workspace diagnostic sanitization and its tests. Checkout, atomic replacement, scan, and promotion behavior remain unchanged. |
| Review mode | Ordinary focused security review. Escalate to explicit Judgment Day only if the fix introduces a shared redaction primitive used across multiple credential-bearing adapters or changes the public error model. |

**Completion and evidence (2026-07-12):**

- Changed `src/odoo_forge_workspace/provider.py`, `tests/adapters/test_workspace_provider.py`, and `tests/cli/test_project.py`.
- Raw Git stderr and credential-bearing argv no longer cross `CheckoutError`, `WorkspaceError`, or CLI boundaries. Timeout exception cause/context and formatted tracebacks are secret-free, while bounded subcommand plus exit-code or timeout diagnostics remain useful.
- Focused verification: 26 passed. Full verification: 478 passed, 1 deselected; Ruff, mypy, and the diff check passed.
- Runtime harness: N/A; deterministic subprocess adapter/CLI boundary tests provide the runtime-boundary evidence.
- The initial implementation review's INFO `R3-001` identified timeout cause leakage; the follow-up resolved it before final review.
- Final review: lineage `review-c6d10eb0f723761a`, approved with zero findings. Receipt: `.git/gentle-ai/review-transactions/v2/review-c6d10eb0f723761a/review-receipt.json`.

This unit is first because later diagnostics work must not normalize or reuse an unsafe error
payload. Its public-error contract is an input to work unit 4.

### 2. Require Conforming Residual Closure in the First Durable Store

**Finding:** `R3-001`

**Status:** Reclassified — no current code change.

**Reclassification:** The audit raised a legitimate question about proving the transition, but its
proposed core-model fix was a false positive. `DurableOperationRecord` is a snapshot value used for
trusted persistence loading and replay, so direct materialization with `lifecycle=CLOSED` and
residual cleanup history is deliberately valid. Snapshot coherence belongs to
`DurableOperationRecord.__post_init__`; transition authority belongs to
`DurableOperationStore.resolve_residual`. Because no production concrete durable-store adapter
currently exists, there is no exploitable persisted transition path to correct. `R3-001` is
therefore not actionable in the current core value model.

**Future requirement:** The first concrete durable store must implement `resolve_residual` as the
sole atomic persisted transition from `CLEANUP_REQUIRED` to `CLOSED`. It must use compare-and-swap,
increment the revision, preserve the exact terminal bundle, and reject missing records,
clean-terminal records, already-closed records, and revision conflicts. Direct construction remains
valid during trusted materialization and replay.

| Planning field | Boundary |
| --- | --- |
| Current evidence | `src/odoo_forge/ports/durable_operation_store.py:16-20`, `:34-51`, `:96-110`; `tests/ports/test_durable_operation_store.py:306-367`; `openspec/changes/archive/2026-07-14-CAP-DURABLE-OPERATIONS-RECORD-FIX/design.md:65-74`, `:228` |
| Adoption tests | For the first concrete store, prove the atomic `CLEANUP_REQUIRED` to `CLOSED` CAS, revision increment, exact terminal-bundle preservation, and rejection of missing, clean-terminal, already-closed, and revision-conflict cases. Also prove trusted loading/replay accepts directly materialized closed records with residual history. |
| Exit criteria | No current implementation exit criterion. Future store adoption is complete only when persisted writes have one transition authority and materialized snapshots retain the current coherence contract. |
| Rollback boundary | N/A for the current core. A future adapter change must keep its implementation, conformance tests, and persistence migration, if any, in one rollback-safe unit. |
| Review mode | Ordinary focused store-adoption review. Strong persisted provenance is a separate architecture fork requiring schema and replay decisions, migration policy, and Judgment Day; do not recommend it by default. |

This reclassified unit records a conformance gate for future store adoption; it does not block the
current Docker or CLI work.

**Independent roadmap debt:** The merged delta at
`openspec/changes/CAP-DURABLE-OPERATIONS-RECORD-FIX/specs/durable-operations/spec.md` appears not yet
synchronized into `openspec/specs/durable-operations/spec.md`. This needs independent confirmation
and archival synchronization. It is not evidence that `R3-001` is valid, and this roadmap update
does not modify OpenSpec files.

### 3. Give Docker Readiness One Deadline Contract

**Findings:** `R4-001`, `R4-002`

**Objective:** Make PostgreSQL readiness and Odoo health waits honor explicit wall-clock deadlines,
including time spent inside each Docker CLI invocation and sleeps.

| Planning field | Boundary |
| --- | --- |
| Likely files | `src/odoo_forge_docker/provider.py`; `tests/adapters/test_docker_provider.py`; integration timing tests only if deterministic unit tests cannot prove daemon behavior |
| Tests and evidence | Use an injected monotonic clock and controlled subprocess behavior to cover slow invocations, fractional budgets, zero/short budgets, final attempts, and sleep truncation. Prove both gates share the same deadline semantics and preserve typed timeout errors and rollback. |
| Exit criteria | Elapsed time is bounded by the configured gate deadline plus a documented scheduler/process termination tolerance; no poll receives a timeout larger than the remaining budget; adapter tests pass. |
| Rollback boundary | Revert the readiness-loop/deadline calculation and its tests without touching container creation, credential injection, diagnostics, or rollback ordering. |
| Review mode | Ordinary focused resilience review. Judgment Day is not justified for isolated deadline-loop changes; reconsider only if the implementation alters rollback guarantees or broad subprocess semantics. |

Treat the pair as one work unit because both defects arise from the same mismatch between attempt
counting and the independent per-invocation timeout. Fixing them separately would duplicate policy
and allow semantic drift.

**Completion and evidence (2026-07-12):**

- Changed `src/odoo_forge_docker/provider.py` and `tests/adapters/test_docker_provider.py`.
- PostgreSQL readiness and Odoo health now use one shared monotonic deadline policy. Probe runtime and sleeps consume the configured budget, and each subprocess timeout is capped at the positive remaining budget.
- Exhausted deadlines skip the subprocess rather than invoking it with `timeout=0`, and return the gate-specific typed readiness error. A real Docker timeout while positive budget remains continues to return `DockerUnavailableError`.
- The initial review identified an INFO finding about `timeout=0` classification; the follow-up removed meaningless zero-budget final probes and resolved it before final review.
- Focused final verification: 12 passed, 58 deselected. Adapter verification: 70 passed. Full verification: 490 passed, 1 deselected, 98% coverage. Ruff, mypy, and the diff check passed.
- Runtime harness: N/A; deterministic tests with injected clock and subprocess behavior prove the deadline boundary without a live Docker daemon.
- Final review: lineage `review-82b5faa3aa182019`, approved with zero findings. Receipt: `.git/gentle-ai/review-transactions/v2/review-82b5faa3aa182019/review-receipt.json`.

### 4. Normalize CLI Validation Diagnostics

**Finding:** `R2-001`

**Objective:** Make `stop`, `logs`, and `exec` report Pydantic validation failures with the same
field-oriented, single-line diagnostic contract used by `validate`, `lock`, `project`, `unlock`,
`run`, and `status`.

| Planning field | Boundary |
| --- | --- |
| Likely files | `src/odoo_forge_cli/main.py`; `tests/cli/test_backend.py`; a small shared CLI test helper only if one already fits project conventions |
| Tests and evidence | Invoke each affected command with an invalid manifest; assert exit code 1, one stable `error: <field>: <message>` line per validation error, no traceback, and no raw multi-line Pydantic rendering. Re-run existing command error-boundary tests. |
| Exit criteria | All manifest-consuming commands expose one consistent validation format and existing backend/domain error behavior is unchanged. |
| Rollback boundary | Revert only validation-error rendering for the three commands and its tests; backend identity derivation and provider calls remain untouched. |
| Review mode | Ordinary focused readability review. Judgment Day is not justified. |

This unit depends on work unit 1's safe public-error policy, but it does not depend on the lifecycle
or Docker implementation details.

**Completion and evidence (2026-07-12):**

- Changed `src/odoo_forge_cli/main.py` and `tests/cli/test_backend.py`.
- Added one internal validation-error renderer and applied it consistently across the manifest-validation boundaries for `stop`, `logs`, and `exec`.
- Invalid manifests now exit 1 with stable, field-oriented one-line errors. Rejected values and secrets, raw multi-line Pydantic representations, tracebacks, and backend provider construction do not cross these boundaries.
- Existing `ManifestError` and `BackendError` boundaries, successful behavior, and `exec` exit-code propagation remain unchanged.
- TDD RED: 3 failed. Focused GREEN: 3 passed. Backend CLI verification: 32 passed. Full CLI verification: 78 passed. Full verification: 493 passed, 1 deselected. Ruff, mypy, and the diff check passed.
- Runtime harness: N/A; the Typer CLI runner exercises the presentation boundary.
- Final review: lineage `review-192994a7729f5a11`, approved with zero findings. Receipt: `.git/gentle-ai/review-transactions/v2/review-192994a7729f5a11/review-receipt.json`.

### 5. Enforce the Git Credential-Safe Failure Boundary

**Discovery:** Characterization reproduced secret exposure through Git failure surfaces.

**Objective:** Ensure raw credential-bearing URLs, stderr, error attributes,
`TimeoutExpired`/`FileNotFoundError` causes, and formatted tracebacks cannot expose secrets, while
preserving ref/auth/network/not-found classification and useful bounded diagnostics.

| Planning field | Boundary |
| --- | --- |
| Production and tests | `src/odoo_forge_git/git_provider.py`; `tests/adapters/test_git_provider.py` |
| Tests and evidence | Exercise credential-bearing URL and stderr failures, public error attributes, timeout and missing-binary cause chains, and formatted tracebacks. Assert no secret survives while each existing failure class and bounded non-secret context remains useful. |
| Exit criteria | All listed Git failure surfaces are credential-safe; ref/auth/network/not-found classification remains stable; focused tests pass. |
| Rollback boundary | Revert only Git failure sanitization and its focused tests; Git operation semantics remain unchanged. |
| Review mode | Ordinary focused security review. No Judgment Day unless the change alters a shared cross-adapter public error model. |

**Completion and evidence (2026-07-12):**

- Changed `src/odoo_forge_git/git_provider.py` and `tests/adapters/test_git_provider.py`.
- HTTP(S) userinfo, arbitrary URI userinfo including `ssh://`, and scp-like remotes are sanitized. Malformed credential-shaped remotes become a bounded redacted placeholder.
- Raw stderr is replaced by bounded diagnostics. Public attributes, strings, tracebacks, causes, and contexts are secret-safe, while useful host/path context and typed ref-not-found, authentication, and network errors remain intact. Tests also prove the subprocess noninteractive contract.
- Initial TDD RED: 3 failed, 17 passed. Final follow-up RED: 5 failed, 22 passed. Focused final verification: 27 passed. Adapter/CLI verification: 213 passed, 1 deselected. Full verification: 503 passed, 1 deselected. Ruff, format, mypy, import contracts, and the diff check passed.
- Runtime harness: N/A; mocked subprocess-boundary tests provide the runtime-boundary evidence.
- The initial review's INFO `R3-001` identified non-HTTP URI userinfo leakage; the follow-up resolved it before final review.
- Final review: lineage `review-0d8d94269a7b724d`, approved with zero findings. Receipt: `.git/gentle-ai/review-transactions/v2/review-0d8d94269a7b724d/review-receipt.json`.

### 6. Enforce the Registry Credential-Safe Failure Boundary

**Discovery:** Characterization reproduced secret exposure through registry failure surfaces.

**Objective:** Ensure raw references, stderr, nested publish/pull errors, timeout and missing-binary
causes, and formatted tracebacks cannot expose secrets, while preserving auth precedence over
not-found, `exists` false only for genuine not-found, and digest immutability.

| Planning field | Boundary |
| --- | --- |
| Production and tests | `src/odoo_forge_registry/provider.py`; shared registry errors/reference only if required; `tests/adapters/test_registry_provider.py` |
| Tests and evidence | Exercise credential-bearing references and stderr across publish, pull, exists, timeout, and missing-binary paths, including nested errors and formatted tracebacks. Prove redaction without weakening classification or digest guarantees. |
| Exit criteria | All listed registry failure surfaces are credential-safe; auth precedence, genuine-not-found `exists` behavior, and digest immutability remain stable; focused tests pass. |
| Rollback boundary | Revert only registry failure sanitization and its focused tests; reference and shared errors change only if the boundary requires them. |
| Review mode | Ordinary focused security review. Judgment Day only for a shared error-model or port break. |

**Completion and evidence (2026-07-12):**

- Changed `src/odoo_forge/image_registry/errors.py`, `src/odoo_forge_registry/provider.py`, and `tests/adapters/test_registry_provider.py`.
- References containing userinfo are rejected before subprocess execution. Raw stderr, nested publish/pull failures, timeouts, missing binaries, and malformed JSON now expose bounded safe diagnostics; public attributes, strings, tracebacks, causes, and contexts remain secret-safe.
- Authentication precedence over not-found is preserved, and `exists` returns false only for genuine not-found responses. Successful digest mismatches raise bounded `RegistryDigestMismatchError` without exposing either digest; authentication and unavailable errors continue to propagate, while digest immutability and GHCR behavior remain intact.
- Initial TDD RED: 5 failed. Focused final verification: 27 passed. Relevant verification: 187 passed, 1 deselected. Full verification: 513 passed, 1 deselected. All quality gates passed.
- Runtime harness: N/A; mocked subprocess-boundary tests provide the runtime-boundary evidence.
- The initial review's INFO finding identified digest-mismatch/absence conflation; the follow-up resolved it before final review.
- Final review: lineage `review-9323fdde84c3b849`, approved with zero findings. Receipt: `.git/gentle-ai/review-transactions/v2/review-9323fdde84c3b849/review-receipt.json`.
- No commit or pull request has been created for this work unit.

### 7. Guarantee Factory Temporary-Secret Cleanup

**Discovery:** Characterization reproduced incomplete cleanup of the fallback plaintext password
file.

**Objective:** Ensure the fallback plaintext password file has mode `0600` and is removed on
readiness success, failure, and signal/termination where shell control permits, while preserving
file-path passing and preventing plaintext argv or log exposure.

| Planning field | Boundary |
| --- | --- |
| Production and tests | `factory/entrypoint.sh`; focused shell harness; image smoke only if necessary |
| Tests and evidence | Exercise file mode and cleanup after readiness success, failure, and controllable signal/termination paths. Assert secrets remain file-based and absent from argv and logs. |
| Exit criteria | The fallback file is mode `0600`, cleanup occurs on every shell-controllable exit path, existing file-path passing remains intact, and the focused harness passes. |
| Rollback boundary | Revert only local fallback-file creation/cleanup behavior and its harness; container credential architecture remains unchanged. |
| Review mode | High-risk review because factory is security-sensitive shell/runtime. Use Judgment Day only if the change crosses container credential architecture rather than local cleanup. |

**Completion and evidence (2026-07-12):**

- Changed `factory/entrypoint.sh` and `factory/tests/test-entrypoint-temp-secret-cleanup.sh`.
- The process-owned fallback file is mode `0600`, is passed by path only, and never exposes plaintext through argv or logs. Cleanup is idempotent after readiness success, readiness failure, and `TERM`, preserves the command status, and never deletes a caller-owned secret file.
- Metacharacter-safe argument forwarding and command dispatch remain intact.
- TDD RED: the fallback file remained after readiness. GREEN runtime harness: 4 scenarios passed. Factory tests: 16 assertions passed. ShellCheck passed. Python verification: 513 passed, 1 deselected. All quality gates passed.
- Image smoke was unavailable because Docker is not installed; this environment limitation remains unverified by an image-level run.
- Final review: lineage `review-921022ea4df4f21d`, approved with zero findings. Receipt: `.git/gentle-ai/review-transactions/v2/review-921022ea4df4f21d/review-receipt.json`.
- No commit or pull request has been created for this work unit.

### 8. Characterize Residual No-Defect Boundaries

**Scope:** Missing assertions for Git, registry, and factory boundaries, with any reproduced defect
extracted into its own canonical corrective sub-unit.

| Planning field | Boundary |
| --- | --- |
| Production and tests | Focused tests or shell harness only; no production changes |
| Tests and evidence | Add only missing assertions for already-correct behavior and record the risk each assertion closes. |
| Exit criteria | Residual selected boundaries have concise passing evidence; no production behavior changes are included. |
| Rollback boundary | Revert characterization assertions independently by area. |
| Review mode | Ordinary focused review. Any further reproducible defect becomes a separate canonical work unit. |

**Completion and evidence (2026-07-12):**

- Registry characterization proves shared subprocess behavior and canonical digest contracts. Factory characterization proves Dockerfile/runtime wiring, including the final effective `USER odoo`.
- The Registry characterization passed 30 tests; Factory characterization passed 2 tests; full verification passed 518 tests with 1 deselected.
- The initial review reported an INFO weakness in the effective-user assertion. The assertion was strengthened before final review.
- Final review: lineage `review-final-registry-factory-20260712`, approved with zero findings. Receipt: `.git/gentle-ai/review-transactions/v2/review-final-registry-factory-20260712/review-receipt.json`.
- The passing Registry/Factory characterization was committed later as `81f90fd` (`test(registry-factory): characterize provider and image wiring`).
- Docker image smoke remains unavailable locally, so the image-level runtime boundary is not verified in this environment.

#### 8.1. Correct Git Remote-Ref Classification

Git characterization reproduced a new defect rather than hiding it in passing characterization:
the standard `fatal: couldn't find remote ref` diagnostic was classified as `NetworkError`. It was
extracted as a canonical corrective sub-unit.

- The implementation anchors the stable diagnostic and returns `RefNotFoundError`. Authentication precedence, network fallback, and credential-safe public failures remain intact.
- Verification: classification matrix 6 passed; Git tests 33 passed; adapter/CLI tests 41 passed; full verification 524 passed, 1 deselected.
- Final review: lineage `review-e4d66c58962320de`, approved with zero findings. Receipt: `.git/gentle-ai/review-transactions/v2/review-e4d66c58962320de/review-receipt.json`.
- The fix is implemented but not committed at the time of this roadmap update.

Residual characterization is complete after extracting and correcting this defect, subject to the
local Docker image-smoke limitation above.

### 9. Optional Cross-Module Integration Judgment

**Status:** Not started and not authorized by this roadmap. No Judgment Day has occurred.

**Objective:** Use dual adversarial judgment only if the completed aggregate delta has extraordinary
cross-module risk that cannot be adequately reviewed as the bounded units above.

The concrete immutable target must be created at gate G6 as follows: freeze the exact Git candidate
tree containing only the accepted outputs of work units 1-8, record its full 40-character tree ID,
record a SHA-256 digest of the ordered path list and file bytes, and bind both values to the unchanged
baseline commit `e149f2b194aa9e1f0c8463ef41c300be0a333314`. Both blind judges must receive that identical target,
scope, resolved skill paths, and criteria. A moving branch name or working directory is not a valid
target.

Judgment Day is extraordinary here only if the aggregate delta couples credential redaction,
durable lifecycle authority, Docker timeout/rollback behavior, and CLI error presentation such that
a single regression could escape isolated reviews. Size alone and the presence of WARNING/INFO
findings are insufficient reasons.

Both blind, read-only judges evaluate the same criteria:

1. No credential material can cross adapter, domain-error, log, or CLI boundaries.
2. Any concrete durable store makes `resolve_residual` the sole atomic persisted transition to `CLOSED`, while trusted materialization/replay remains valid and auditable.
3. Docker readiness deadlines are bounded without weakening rollback or error classification.
4. CLI normalization preserves exit codes, field context, and non-validation diagnostics.
5. Git and registry failure surfaces preserve classification and integrity guarantees without exposing credentials.
6. Factory temporary-secret cleanup preserves file-based credential passing and removes plaintext files on shell-controllable exits.
7. The combined delta introduces no severe regression in architecture boundaries, replay safety, or failure recovery.

Start and persist a native `judgment_day` transaction for the frozen target before launching both
judges. Merge their results into a frozen ledger and persist the transaction, ledger, target
identity, and artifact references. Only severe findings independently confirmed by both judges may
trigger corrections. A one-judge report remains suspect and cannot trigger an automatic fix;
contradictions require human escalation. Before the first correction, obtain explicit human
approval. Permit at most two bounded correction rounds and two scoped re-judgments over the frozen
ledger plus each immutable fix delta. After corrections, run independent final verification,
persist the result, and emit a terminal receipt containing the confirmed, suspect, contradiction,
and INFO counts plus all correction and re-judgment references. The transaction must terminate as
exactly `approved` or `escalated`; unresolved issues after round two terminate as `escalated`.

If gate G6 is not met, use an ordinary focused integration review and the repository's full quality
suite instead.

## Dependencies and Delivery Boundaries

```text
workspace credential redaction -----> CLI diagnostics

Git credential boundary --------+
registry credential boundary ----+---> residual no-defect characterization
factory secret cleanup ----------+
                                      |
                                      +---> extracted Git remote-ref correction

accepted outputs of units 1-8 --------> optional integration judgment
```

Each work unit is independently reviewable and rollback-safe. A later commit or PR may use one work
unit as its delivery boundary, keeping implementation, tests, and evidence together, but this
roadmap does not prescribe creating commits or PRs. No commit exists for this roadmap at the time of
writing.

## Non-Goals

- Re-running or relabeling the completed ordinary 4R review as Judgment Day.
- Treating approved status as proof that no defects exist.
- Automatically correcting WARNING/INFO findings without a bounded change and focused evidence.
- Refactoring modules merely to align with the lens map.
- Changing public APIs, persisted schemas, or compatibility behavior unless a work unit's decision gate explicitly requires it.
- Combining newly discovered defects into an existing work unit without separate scope and evidence.
- Creating commits, branches, or pull requests as part of this document-only task.

## Tracking Checklist

- [ ] G0: Freeze and record the start target for each work unit.
- [x] Unit 1: Enforce and test workspace credential redaction (completed 2026-07-12).
- [ ] Unit 2: Reclassified — no current code change; enforce conformance when adopting the first concrete durable store.
- [ ] Independently confirm and synchronize the unsynced durable-operations OpenSpec delta during archival work.
- [x] Unit 3: Enforce one wall-clock deadline contract for both Docker gates (completed 2026-07-12).
- [x] Unit 4: Normalize `stop`, `logs`, and `exec` validation diagnostics (completed 2026-07-12).
- [x] Unit 5: Enforce the Git credential-safe failure boundary (completed 2026-07-12).
- [x] Unit 6: Enforce the registry credential-safe failure boundary (completed 2026-07-12).
- [x] Unit 7: Guarantee factory temporary-secret cleanup (completed 2026-07-12).
- [x] Unit 8: Complete residual characterization and extract the Git remote-ref defect (completed 2026-07-12; Docker image smoke unavailable locally).
- [x] Unit 8.1: Correct Git remote-ref classification and preserve auth precedence, network fallback, and credential safety (implemented and approved 2026-07-12; not yet committed).
- [x] Run focused tests with each completed unit and record exact results.
- [x] Run full verification after the residual characterization and extracted Git correction (524 passed, 1 deselected).
- [ ] G6: Decide whether extraordinary cross-module risk actually justifies Judgment Day.
- [ ] Unit 9: If G6 is met and separately authorized, run the optional cross-module integration judgment.
- [ ] If Judgment Day is authorized, freeze its immutable target and enforce the two-round terminal protocol.
- [ ] Close with an approved ordinary review or a terminal Judgment Day outcome; do not leave an open-ended review lineage.

## Postscript — 2026-07-14

This append-only note updates delivery facts without rewriting the review record above.

- Registry credential hardening is committed as `a11eb99`.
- Factory temporary-secret cleanup is committed as `44f3213`.
- Git remote-ref classification is committed as `02e2674`.
- This audit roadmap and its Spanish translation are committed as `db82fc1`.
- The completed `CAP-DURABLE-OPERATIONS-RECORD-FIX` delta was synchronized into
  `openspec/specs/durable-operations/spec.md` and archived at
  `openspec/changes/archive/2026-07-14-CAP-DURABLE-OPERATIONS-RECORD-FIX/`.
- The archive preserves the original PASS WITH WARNINGS verification report. Its one named
  traceability warning was not converted into successful evidence, and no new review was started.
- The optional cross-module Judgment Day remains neither authorized nor performed.
