# Design: Workspace Partial Clone

## Technical Approach

Switch `GitWorkspaceProvider._clone_and_replace` (`src/odoo_forge_workspace/provider.py:134-150`)
from `git clone --no-checkout` to a partial clone `git clone --filter=blob:none
--no-checkout`, with a transparent full-clone fallback. Isolate the fallback to
the clone step only (extract a private `_clone` helper) so the subsequent
`checkout --detach <commit>` and `_atomic_swap` run exactly once, unchanged. Port
signature, idempotency, dirty/linked-worktree refusal, atomic swap, and `promote`
stay byte-for-byte identical. Add the first real-git hermetic integration test for
this adapter (none exists today).

## Architecture Decisions

### Decision: Fallback detection strategy — retry-once on any clone failure

**Choice**: On a partial-clone `CheckoutError`, `rmtree` the temp dir and retry
once with the current full-clone argv (no `--filter`). If the full clone also
fails, let that error propagate.

**Alternatives considered**: (b) a narrow capability probe that classifies the
git "filter unsupported" signal via a controlled channel.

**Rationale**: `_run` deliberately never surfaces git stderr (clone URLs may embed
`user:token@`; provider.py:198-208). We therefore cannot distinguish "remote
rejected `--filter`" from "auth/network failure" without reintroducing a
credential-leak surface. Option (b) requires piercing that guarantee for a
marginal gain. The error path already terminates in failure: on a genuine auth
error the wasted full-clone attempt still ends in the same raised `CheckoutError`,
just later — no worse observable outcome, and no credential exposure. The only
cost is one extra doomed clone on hard-failure paths, which is acceptable. Bias
toward robustness (proposal) confirmed. Credential-safety guarantee of `_run` is
left fully intact.

### Decision: Fallback scoped to clone, not clone+checkout

**Choice**: Only the clone is retried; `checkout --detach` runs once afterward.

**Rationale**: If the partial clone succeeds, the remote advertised `allowFilter`,
so lazy blob fetch during checkout will work; a checkout failure is a distinct
fault that a full re-clone would not fix and must propagate. `git clone` requires
an empty/absent target, so the failed attempt is `rmtree`d before retry (git
recreates the dir).

## Data Flow

    checkout(url, commit, dest)
      └─ _clone_and_replace
           ├─ _clone(url, tmp)                    # partial clone
           │     └─ CheckoutError? → rmtree(tmp) → full clone (no --filter)
           ├─ git -C tmp checkout --detach <commit>   # lazy blob fetch for commit
           └─ _atomic_swap(tmp, dest)             # unchanged
    promote(source, dest, branch)
      └─ git -C source worktree add -b branch -- dest  # same commit → blobs cached, offline

`worktree add` needs no network: `checkout --detach <commit>` already materialized
(lazy-fetched) every blob for that commit into the shared object store; the linked
worktree targets the same commit and reuses that store/promisor config.

## Exact argv

| Step | argv |
|------|------|
| Partial clone (new) | `git clone --filter=blob:none --no-checkout -- <url> <tmp>` |
| Fallback clone | `git clone --no-checkout -- <url> <tmp>` (today's argv) |
| Checkout (unchanged) | `git -C <tmp> checkout --detach <commit>` |

`--filter=blob:none` is a single token before `--`, so the end-of-options
positional guarantee for `<url>`/`<tmp>` is preserved.

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `src/odoo_forge_workspace/provider.py` | Modify | Add `--filter=blob:none`; extract `_clone` with retry-once fallback |
| `tests/adapters/test_workspace_provider_integration.py` | Create | Real-git hermetic clone→checkout→promote→worktree-add + fallback |

## Testing Strategy (STRICT TDD — RED first)

| Layer | What to Test | Approach |
|-------|-------------|----------|
| Unit (argv) | First clone carries `--filter=blob:none` | Extend `_fake_run_factory` mock; assert argv shape. RED before impl |
| Unit (fallback) | Non-zero on filtered clone → second clone without `--filter` | Fake `run` fails only the `--filter` argv; assert fallback argv issued |
| Integration | Full path against real local fixture, no network | New file, real `git` subprocess |

New file `tests/adapters/test_workspace_provider_integration.py`:
- Module marker `pytestmark = pytest.mark.integration` (matches existing
  `*_integration.py`; deselected by `addopts -m 'not integration'`).
- Skip helper: `pytest.skip` if `git` missing or `< 2.19` (partial clone +
  worktree).
- Fixture A: bare repo in `tmp_path` with a real commit, `git config
  uploadpack.allowFilter true`; clone via `file://` URL. Assert partial clone →
  `checkout --detach <pinned SHA>` → `promote` worktree materializes the tree with
  correct file contents, sourced only from the local remote.
- Fixture B: identical bare repo WITHOUT `allowFilter` (default); assert `checkout`
  still succeeds via full-clone fallback and the tree is correct.

## Threat Matrix

| Boundary | Applicability | Design response | Planned RED test |
|---|---|---|---|
| Documentation-like paths | N/A: no file-type classification | — | — |
| Git repository selection (`-C`, positional paths) | Applicable: clone target + `-C` retained | `--` end-of-options preserved before `<url>`/`<tmp>`; fallback reuses same guard | Unit argv assertion that both clones keep `--` before positionals |
| Commit state | N/A: no index/commit writes | — | — |
| Push state | N/A: no push/refspec | — | — |
| PR commands | N/A: no PR automation | — | — |

## Migration / Rollout

No migration. Revert = drop `--filter=blob:none` and the fallback branch (single
function). Runtime dependency: git ≥ 2.19.

## Open Questions

- [ ] Empirical download-savings figure on real Odoo core — measure during apply
  (success-criteria only; does not block implementation).
