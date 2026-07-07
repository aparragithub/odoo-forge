# Exploration: Phase 2 Slice 2 — Resolution / Materialization (shared)

## Current State
Slice 1 delivered a pure domain (`src/odoo_forge/manifest/{schema,composition,lockfile,drift,state,errors}.py`) plus a `SourceProvider` Protocol port (`src/odoo_forge/ports/source_provider.py`, `resolve_ref(url: str, ref: str) -> str`, no adapter) and a thin CLI (`src/odoo_forge_cli/main.py`, only `forge validate`). `CoreLayer.ref: str | None = None` is accepted and `compose()` preserves it verbatim — deliberately NOT resolved (spec amendment, see `openspec/specs/manifest/spec.md` Requirement "Core layer is a first-class field"). `Lockfile` (`ResolvedRepo{url,ref,commit}`, `ResolvedLayer{name,repos}`, `Lockfile{generated_from,layers}`) exists as a schema but nothing produces it — `forge validate` only *reads* an existing `project.lock` via ad hoc `json.loads` + `Lockfile.model_validate` (W3 in verify-report: format never formalized). `detect_drift(manifest, lock, materialized)` is pure/three-input; `materialized` is always `None` today (Slice 3 adapter not built). Import-linter enforces `odoo_forge` core purity: forbids `docker, boto3, kubernetes, git, typer, subprocess, requests, httpx` imports and forbids `odoo_forge_cli` (pyproject.toml `[tool.importlinter]`, 2 contracts, both KEPT). No `git`/network dependency exists yet in `pyproject.toml`.

### Affected Areas
- `src/odoo_forge/ports/source_provider.py` — port stays interface-only; Slice 2 adds the first real caller.
- `src/odoo_forge/manifest/schema.py` — `CoreLayer.ref: str | None` needs a pure default-substitution helper (not mutation of the model itself, and NOT inside `compose()` per spec).
- `src/odoo_forge/manifest/lockfile.py` — `Lockfile`/`ResolvedRepo`/`ResolvedLayer` need a formalized serialization contract (version field, canonical JSON, key ordering for diff-friendliness).
- `src/odoo_forge_cli/main.py` — needs a new `forge lock` command; current `_load_lock` ad hoc JSON parsing should be extracted/shared, not duplicated.
- `pyproject.toml` `[tool.importlinter]` — needs a THIRD root package for the concrete adapter plus a new forbidden-import contract mirroring `core-ignores-cli`.
- New package (name TBD, e.g. `odoo_forge_git`) — first concrete `SourceProvider` implementation; must not be importable from `odoo_forge`.
- `openspec/specs/manifest/spec.md` — needs a new capability/requirement for ref resolution and lock generation (Slice 1 spec explicitly deferred this).

### Design Questions (surfaced, not answered by assumption)

**Q1 — Ref resolution strategy** (compare below).
**Q2 — Where does `core.ref: None → odoo_version` resolution live?**
The port signature is `resolve_ref(url: str, ref: str) -> str` — it does not accept `None`. This means "substitute `odoo_version` for a missing ref" and "look up the SHA for a ref" are two DIFFERENT operations with different purity requirements:
- Default-ref substitution (`ref or manifest.odoo_version`) is pure string logic, zero I/O — it CAN legally live in `odoo_forge` core without violating the import-linter gate, but it must NOT be inside `compose()` itself (spec forbids `compose()` from resolving/mutating `core.ref`). It should be a new, separate pure function, e.g. `resolve_default_ref(core: CoreLayer, odoo_version: str) -> str`, called by whatever orchestrates locking — not by `compose()`.
- SHA lookup (`resolve_ref(url, ref) -> sha`) is inherently I/O and MUST go through the port; the concrete implementation lives in a new adapter package outside `odoo_forge`.
- The orchestration function that ties these together ("build a `Lockfile` from a `Manifest` + a `SourceProvider`") is the real new unit here. It can still live inside `odoo_forge` core as a *use case* that receives a `SourceProvider` as a structural (Protocol) parameter — this preserves purity (no concrete adapter import) while giving the core a testable seam via a fake, exactly like `tests/ports/test_source_provider.py` already does with `_FakeGitProvider`. This is the idiomatic hexagonal move: the port lives with the core, the adapter and the composition root (CLI) live outside it.

**Q3 — Hexagonal placement of the concrete adapter.** Slice 1's own docstring in `source_provider.py` states adapters "live outside the core package in a later slice and MUST NOT be imported here." That means a NEW top-level package (sibling to `odoo_forge`/`odoo_forge_cli`), added to `importlinter.root_packages`, with a new forbidden-import contract (`odoo_forge` forbids the adapter package, mirroring `core-ignores-cli`). The CLI (`odoo_forge_cli`) becomes the composition root: it constructs the concrete adapter and injects it into the core's lock use-case function. This keeps the "2 kept / 0 broken" purity gate intact by adding a third contract, not by weakening the existing two.

**Q4 — Lockfile serialization format.** Current: ad hoc `json.dumps`/`json.loads` with no schema version, no explicit key order, no indentation contract (W3). Needs: (a) JSON vs YAML — JSON is consistent with the machine-generated, diff-checked nature of the file and avoids a second parser; (b) a `version`/`schema_version` field for forward compatibility (mirrors `Manifest` not having one yet, but the lock is machine-owned so it's cheaper to version now); (c) deterministic key ordering + stable indentation so `git diff` on `project.lock` is meaningful and drift/CI is reproducible byte-for-byte given the same resolved SHAs.

**Q5 — Offline/caching/auth/resilience.** `git ls-remote` against a private repo needs credentials. Recommendation: do NOT design credential-passing into the `SourceProvider` port for this slice — rely on the ambient `git` credential system (SSH agent / credential helper / `.netrc`) already configured on the operator's machine, and treat auth failures as a typed, catchable error surfaced by the adapter. Explicitly scope out: retry/backoff policy, response caching, and offline mode — call these out as non-goals for Slice 2, deferred if they become a real pain point.

**Q6 — Should Slice 2 be split into chained PRs?** Yes — it bundles 5 deliverables of very different risk profiles (pure logic vs subprocess/network I/O). Recommended split:
- **2a (low risk, pure)**: `core.ref` default-substitution helper + `Lockfile` format finalization (schema version, canonical serialization) + spec amendment. No new dependencies, no import-linter changes beyond documentation.
- **2b (higher risk, I/O)**: concrete git `SourceProvider` adapter (new package + import-linter contract) + `forge lock` CLI command, wiring 2a's use-case function to the real adapter. This is the piece that should get `review-resilience` + `review-reliability` treatment before merge (subprocess/network boundary, partial failure, auth failure, missing ref).
This also respects the 400-line PR review budget — 2a is small/mechanical, 2b is where the real design risk (and test surface: mocked subprocess, `git ls-remote` failure modes) concentrates.

### Approaches — Ref Resolution Strategy

1. **`git ls-remote <url> <ref>` via subprocess, adapter shells out to system git** — resolve a ref to a SHA without a local clone.
   - Pros: no local disk footprint just to resolve a pointer; reuses the operator's existing git config/credentials/SSH agent for free; simple, auditable command; matches "resolve, don't materialize" semantics that this slice's naming implies (materialization is Slice 3).
   - Cons: requires `git` binary present on the host; subprocess argument handling must avoid shell injection (use argv list, never `shell=True`); ref-not-found surfaces as empty stdout rather than a typed exception — adapter must translate that into a raised error itself.
   - Effort: Low-Medium.

2. **Python git library (GitPython or pygit2) doing a full/shallow clone, then reading the ref's commit** — heavier but produces bytes that Slice 3 could reuse directly for materialization.
   - Pros: no subprocess/shell surface; richer error types from the library; the clone could be cached and handed to Slice 3 later.
   - Cons: pulls in a native dependency (`pygit2`→`libgit2` C binding, or `GitPython` still shells to `git` under the hood anyway); doing a clone just to resolve a SHA is wasteful I/O for a "resolution" step that explicitly should NOT materialize; couples Slice 2 to Slice 3's storage/caching decisions prematurely.
   - Effort: Medium-High.

3. **Naming-convention assumption (e.g. always assume `ref == odoo_version` maps to an existing branch, never verify against the remote)** — no network call at all.
   - Pros: trivially simple, zero network dependency, deterministic, testable without mocks.
   - Cons: violates the actual purpose of "pin resolution — ref → commit SHA" (the roadmap explicitly wants a real commit SHA in the lockfile, not a branch name restated); silently produces a wrong/stale lock if the assumed branch doesn't exist or has moved; defers the real problem instead of solving it.
   - Effort: Low, but rejected — does not satisfy the stated Slice 2 deliverable ("Pin resolution — ref → commit SHA into the lockfile").

### Recommendation
**Ref resolution: Approach 1 (`git ls-remote` via subprocess).** It is the smallest surface area that satisfies the actual requirement (a real commit SHA, not a convention-guessed one) without prematurely committing to a clone/cache strategy that belongs to Slice 3 (workspace projection/materialization). Fail loud when `ls-remote` returns nothing for a given ref — do not silently fall back to a guessed SHA.

**Domain placement: split responsibility.** Keep `odoo_forge` core pure by putting ONLY the following in core: (a) the existing `SourceProvider` Protocol, (b) a new pure `resolve_default_ref`-style helper for `None → odoo_version`, and (c) a new use-case function that accepts an injected `SourceProvider` and returns a `Lockfile` — still zero concrete imports, so the import-linter gate stays intact. Put the concrete git adapter in a brand-new top-level package outside `odoo_forge`, wired only from `odoo_forge_cli` (the composition root), with a new forbidden-import contract added to `[tool.importlinter]` (target: 3 kept / 0 broken, not weakening the existing 2).

### Risks
- Import-linter contract count changes (2→3 kept) — must be validated in CI before merge, not assumed.
- Ref-not-found / private-repo-auth-failure error taxonomy is undefined today (`errors.py` has no resolution-related error class yet) — needs explicit design in the proposal, not left implicit.
- Bundling all 5 Slice 2 deliverables into one PR risks exceeding the 400-line review budget and mixing low-risk pure logic with high-risk I/O in one diff — recommend the 2a/2b chained-PR split above.
- Lockfile format change (adding a schema version field) is a breaking change for anyone already holding a Slice-1-era `project.lock` — no migration path exists yet; should be called out explicitly (no released users yet, so likely a non-issue, but worth stating).

### Ready for Proposal
Yes — with the explicit note that `sdd-propose` should decide up front whether to file Slice 2 as ONE change (5 bundled deliverables) or split into 2a/2b sub-changes per the chained-PR recommendation above, since that decision drives the whole task breakdown.
