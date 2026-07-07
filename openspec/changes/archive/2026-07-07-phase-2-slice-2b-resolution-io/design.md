# Design: Phase 2 Slice 2b — Git Resolution & Lock Writer (resolution I/O)

## Technical Approach
First I/O boundary that PRODUCES a `project.lock`. `odoo_forge` stays import-pure: git/subprocess live only in a NEW sibling package `odoo_forge_git`; `odoo_forge_cli` is the composition root that constructs the adapter and injects it. Chained PRs: **PR-1** = adapter + `resolve_ref` + resolution error taxonomy + 3rd import-linter contract; **PR-2** = pure `build_lock` use-case (Protocol-injected) + `forge lock` writer + `_load_lock`→`from_json()`. Strict TDD — every seam fakeable without network.

## Architecture Decisions

| # | Decision | Choice | Rejected | Rationale | PR |
|---|----------|--------|----------|-----------|-----|
| 1 | Ref mechanism | `git ls-remote <url> <ref>` argv (never `shell=True`) | full/shallow clone (GitPython/pygit2); naming-convention guess | smallest surface yielding a REAL sha; no disk; reuses ambient git creds; clone/cache is Slice 3 | 1 |
| 2 | Adapter location | new top-level `src/odoo_forge_git/`, class `GitSourceProvider` | inside `odoo_forge`; inside CLI | core must not import subprocess/git; sibling pkg keeps purity gate; CLI-only would block core-side reuse | 1 |
| 3 | 3rd contract | ADD forbidden `odoo_forge`→`odoo_forge_git` (2→3 kept) | weaken existing 2; permit-rule for adapter→subprocess | deny-list is per-source; adapter freely imports subprocess since it is not a listed source; core still blocked by contract-1 | 1 |
| 4 | Build-lock placement (MOST DELICATE) | pure core use-case `build_lock(manifest, provider: SourceProvider) -> Lockfile` in new `manifest/locking.py` | CLI-side orchestration | port lives with core; Protocol param = zero concrete import → import-linter intact; testable via fake (mirrors `_FakeGitProvider`); idiomatic hexagonal | 2 |
| 5 | DI shape | CLI `_make_provider() -> SourceProvider` returns `GitSourceProvider()`; passed to `build_lock` | global singleton; provider in port ctor | composition root owns wiring; factory is the network-free test seam (monkeypatch) | 2 |
| 6 | Error home | new `ResolutionError` base + 3 subclasses in `manifest/errors.py`, family SEPARATE from `ManifestError` | subclass ManifestError; new module | pure (message only) so legal in core; adapter→core import is allowed direction; single taxonomy home per Slice 1; separate family = distinct catch in `forge lock` | 1 |
| 7 | core.ref=None | `build_lock` calls 2a `resolve_default_ref(core, odoo_version)` BEFORE `provider.resolve_ref` | resolve inside compose (spec forbids) | None→odoo_version is pure string, then sha lookup | 2 |

## Ref resolution (concrete, PR-1)
`resolve_ref(url, ref)`:
1. **Bare SHA pass-through**: `re.fullmatch(r"[0-9a-f]{40}", ref)` → return as-is, no subprocess (ls-remote lists refs, not arbitrary commits; already pinned; remote existence check needs a fetch → deferred).
2. Else `subprocess.run(["git","ls-remote",url,ref], capture_output=True, text=True, check=False)`.
3. returncode 0 + empty stdout → `RefNotFoundError(url, ref)` (fail loud — never guess a sha).
4. returncode != 0 → classify stderr: auth markers (`Authentication failed`, `could not read Username`, `Permission denied`, `publickey`) → `AuthenticationError(url)`; else `NetworkError(url, detail)`. `FileNotFoundError` (git binary absent) → `ResolutionError` base.
5. Parse lines `\t`-split into (sha, refname); **selection priority**: `refs/heads/<ref>` (branch) > `refs/tags/<ref>^{}` (peeled annotated tag = target commit) > `refs/tags/<ref>` (lightweight) > first line. Return the 40-char sha.

## Data Flow (forge lock, PR-2)

    project.yaml ─(CLI _read_manifest_data)→ dict → Manifest.model_validate
         │
         ▼  build_lock(manifest, provider)              [core/locking, pure]
    compose(manifest)                    # coherence gate (CompositionError)
    generated_from = compute_manifest_hash(manifest)
    core: ref = resolve_default_ref(core, odoo_version)
          commit = provider.resolve_ref(core.url, ref)  → ResolvedLayer("core",[...])
    git layers: per repo commit = provider.resolve_ref(repo.url, repo.ref)
         │        (published layers: no git repo → skipped; registry = Slice 4)
         ▼
    Lockfile(generated_from, layers) ─ to_canonical_json() → write project.lock
         │  provider = GitSourceProvider → git ls-remote  [odoo_forge_git, PR-1]
    ResolutionError|ManifestError → CLI: echo "error: {exc}", Exit(code=1)

## File Changes

| File | Action | PR | Description |
|------|--------|----|-----------
| `src/odoo_forge_git/__init__.py`,`git_provider.py` | Create | 1 | `GitSourceProvider.resolve_ref` via ls-remote |
| `src/odoo_forge/manifest/errors.py` | Modify | 1 | `ResolutionError`+`RefNotFoundError`/`AuthenticationError`/`NetworkError` |
| `pyproject.toml` | Modify | 1 | add `odoo_forge_git` to root_packages + wheel; 3rd contract |
| `src/odoo_forge/manifest/locking.py` | Create | 2 | pure `build_lock(manifest, provider)` |
| `src/odoo_forge_cli/main.py` | Modify | 2 | `forge lock` cmd; `_make_provider()`; `_load_lock`→`Lockfile.from_json()` |
| `tests/adapters/test_git_provider.py` | Create | 1 | monkeypatch subprocess.run — all failure modes |
| `tests/manifest/test_locking.py`, `tests/cli/test_lock.py` | Create | 2 | fake provider; CliRunner + monkeypatched `_make_provider` |

## Interfaces
```python
# odoo_forge/manifest/errors.py  (PR-1)
class ResolutionError(Exception): ...
class RefNotFoundError(ResolutionError):    # .url .ref
class AuthenticationError(ResolutionError):  # .url
class NetworkError(ResolutionError):         # .url .detail
# odoo_forge/manifest/locking.py  (PR-2)
def build_lock(manifest: Manifest, provider: SourceProvider) -> Lockfile: ...
# odoo_forge_git/git_provider.py  (PR-1)
class GitSourceProvider:  # structurally satisfies SourceProvider
    def resolve_ref(self, url: str, ref: str) -> str: ...
```
3rd contract: `forbidden` source `odoo_forge` → forbidden `odoo_forge_git`.

## Testing Strategy
| Layer | What | How |
|-------|------|-----|
| Unit adapter | success / branch-vs-tag / peeled tag / empty→RefNotFound / non-zero+auth→Auth / +network→Network / bare-SHA no-call / no-git→ResolutionError | monkeypatch `subprocess.run`, no network |
| Unit use-case | Lockfile shape; core None→odoo_version; git layers mapped; published skipped; generated_from==hash; ResolutionError propagates | fake provider (deterministic sha) |
| CLI | writes byte-stable `project.lock`, `from_json` round-trip; typed error→clean msg+exit 1 | CliRunner + monkeypatched `_make_provider` |
| Arch | 3 kept / 0 broken; core imports zero git/subprocess; adapter not importable from core | import-linter CI |

## Scope line
IN: ambient git creds (SSH agent / helper / .netrc), typed auth/network/ref-not-found errors. OUT (deferred): credential-passing in port, retry/backoff, caching, offline mode, published/registry resolution (Slice 4), materialization (Slice 3).

## Open Questions
- [ ] **Override application during lock**: `Override{layer,repo,fork,ref}` is validated by `compose()` but NOT yet applied to resolution (fork url/ref substitution). Recommend DEFER to a follow-up to avoid scope creep; confirm.
- [ ] **Published layers in lock**: skipped (no git repo). Confirm they are omitted vs. recorded as empty `ResolvedLayer(name, repos=[])` for drift-tracking visibility. Recommend: omit until Slice 4.
- [ ] **Exit codes**: single code 1 for all (mirrors Slice 1) vs. differentiated per error type. Recommend keep 1.
