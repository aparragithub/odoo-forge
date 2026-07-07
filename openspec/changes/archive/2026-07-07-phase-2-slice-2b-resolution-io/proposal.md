# Proposal: Phase 2 Slice 2b — Git Resolution & Lock Writer (resolution I/O)

## Intent
Slice 2a shipped the pure prep (`resolve_default_ref`, canonical `Lockfile` serialization). Nothing yet PRODUCES a `project.lock`: the CLI only READS one (`_load_lock`). This slice adds the I/O boundary — resolve declared refs to real commit SHAs and write the lockfile — turning declared intent into a pinned, reproducible lock. It is the highest-risk slice so far (subprocess + network + a new package), so it stays behind a strict hexagonal seam: core remains import-pure; git/subprocess live only in a new adapter package; the CLI is the composition root.

## Scope
### In Scope
- Concrete git `SourceProvider` adapter in a NEW top-level package (name TBD, e.g. `odoo_forge_git`), implementing the Slice 1 port. May import `git`/`subprocess`.
- `resolve_ref(url, ref) -> sha` via `git ls-remote` (recommended over full-clone / naming-convention guessing; final mechanism → design). Fail loud on empty result.
- Lock-build orchestration: compose manifest → substitute default refs (2a `resolve_default_ref`) → resolve SHAs via injected provider → build `Lockfile`.
- `forge lock` CLI command — the lock WRITER, using 2a `Lockfile.to_canonical_json()`; wire `_load_lock` to use `from_json()`.
- Resolution error taxonomy (new): ref-not-found / auth-failure / network-failure typed errors; resilient CLI boundary turning raw tracebacks into clean messages (mirror resilient-validate).
- import-linter: ADD a THIRD forbidden-import contract for the adapter package (2 kept → 3 kept). Do NOT weaken the existing 2.

### Out of Scope
- Workspace projection / materialization / mount-roots / `unlock` (Slice 3).
- Retry/backoff, response caching, offline mode (deferred non-goals).
- Credential-passing in the port (rely on ambient git credential system).
- Docker/registry backend (Slice 4).

## Capabilities
### New Capabilities
- `ref-resolution`: git adapter + `resolve_ref` via `git ls-remote` + resolution error taxonomy.
- `forge-lock-cli`: lock writer command producing canonical `project.lock`.
### Modified Capabilities
- `manifest`: add requirement for lock generation / ref-resolution use case (port contract itself unchanged; behavior of producing a lock is new).

## Approach
Approach 1 (`git ls-remote` via subprocess) — smallest surface that yields a real SHA without a premature clone/cache strategy (Slice 3). Lock-build orchestration accepts a `SourceProvider` structurally (Protocol param), stays in core (testable via fake), zero concrete import. CLI constructs the real adapter and injects it. TDD: mocked subprocess covers success, empty-ref, non-zero exit, auth-failure. `subprocess` must use argv list, never `shell=True`.

## Affected Areas
| Area | Impact | Description |
|------|--------|-------------|
| new `src/odoo_forge_git/` (name TBD) | New | concrete git adapter |
| `src/odoo_forge/manifest/errors.py` | Modified | resolution error classes |
| `src/odoo_forge/manifest/` (use case) | New | lock-build orchestration (placement → design) |
| `src/odoo_forge_cli/main.py` | Modified | `forge lock` writer; `_load_lock` → `from_json()` |
| `pyproject.toml` | Modified | 3rd import-linter contract + git dep if any |

## Risks
| Risk | Likelihood | Mitigation |
|------|------------|------------|
| import-linter 2→3 breaks purity | Med | validate in CI; add not weaken; fake in core tests |
| subprocess injection / shell surface | Med | argv list, never `shell=True`; no interpolation |
| ref-not-found silently mis-pins | High | translate empty `ls-remote` into typed error; fail loud |
| auth/network failure leaks traceback | Med | typed errors + resilient CLI boundary |
| PR exceeds 400-line review budget | High | see forecast below — chained-PR split |

## Review-Workload Forecast
I/O + subprocess + new package + CLI writer + error types — likely approaching/over 400 lines. `Chained PRs recommended: Yes` (candidate split: PR-1 adapter package + resolve_ref + error taxonomy + 3rd contract; PR-2 lock-build use case + `forge lock` CLI wiring). `400-line budget risk: High`. Final decision deferred to sdd-tasks. Recommended review lenses: **review-resilience + review-reliability** (subprocess/network boundary, partial/auth/missing-ref failure modes).

## Open Design Questions (for sdd-design — do NOT lock here)
1. Ref-resolution mechanism detail: exact `git ls-remote` invocation; what counts as \"ref not found\"; tags vs branches vs bare SHAs (an already-full SHA may need pass-through, not lookup).
2. Adapter package name + location (sibling to `odoo_forge`/`odoo_forge_cli`).
3. How the port is injected into `forge lock` (composition-root construction; DI shape).
4. Offline/auth handling scope for THIS slice vs deferred (ambient credentials recommended; confirm boundary).
5. Should `forge lock` resolve `core.ref=None` via 2a `resolve_default_ref` before pinning? (Recommended yes; confirm.)
6. Where the lock-build orchestration use case lives (core use case with Protocol param vs CLI-side).

## Rollback Plan
Additive slice. New adapter package + new CLI command + additive error classes; revert the branch(es). No existing `project.lock` consumers in the wild (schema_version=1 from 2a); lock format unchanged, so no data migration.

## Dependencies
- Slice 2a merged (`resolve_default_ref`, canonical Lockfile) — DONE (PR #6).
- System `git` binary present on host at runtime.

## Success Criteria
- [ ] `forge lock` composes a manifest, resolves each ref to a commit SHA, and writes a canonical `project.lock` (byte-stable, `from_json()` round-trips).
- [ ] Unset `core.ref` resolves via `resolve_default_ref` before pinning.
- [ ] ref-not-found / auth-failure / network-failure surface as clean typed CLI errors (no raw traceback), non-zero exit.
- [ ] import-linter 3 kept / 0 broken; `odoo_forge` core still imports zero git/subprocess; adapter not importable from core.
- [ ] `_load_lock` uses `Lockfile.from_json()`; validate + lock suites green.
