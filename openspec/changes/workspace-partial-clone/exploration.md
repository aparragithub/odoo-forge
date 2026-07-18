# Exploration: workspace-partial-clone

## Problem

The git workspace adapter clones the **full history** of every source repo
(notably the Odoo core repo, >1GB) merely to materialize a read-only working
tree pinned at a single locked commit. The goal is to reduce the download to
the minimum needed to produce the working tree at the pinned commit, **without
breaking the `unlock`/`promote` contract**.

## Current State

`GitWorkspaceProvider._clone_and_replace` (`src/odoo_forge_workspace/provider.py:134-150`):

1. `git clone --no-checkout -- <url> <clone_path>` — downloads the full object
   database (all history/branches). `--no-checkout` only skips materializing the
   temp working tree; it does **not** reduce what is downloaded.
2. `git -C <clone_path> checkout --detach <commit>` — detaches HEAD at the pinned
   SHA, materializing the working tree.

`checkout()` (lines 53-76) is idempotent (no-op if `dest` HEAD already matches),
refuses dirty checkouts and linked worktrees with `CheckoutError`, then
atomically swaps the fresh clone into `dest` via `_atomic_swap`.

`promote()` (lines 115-132) — the `unlock` codepath — runs
`git -C <source> worktree add -b <branch> -- <dest>` from the already-checked-out
`source`, at the **same commit** `source` is already pinned to. This is the hard
constraint any clone-slimming change must preserve.

`ResolvedRepo{url, ref, commit}` (`src/odoo_forge/manifest/lockfile.py`) always
hands `checkout` a resolved 40-char SHA; `ref` only selects which commit was
resolved and plays no role at checkout time. The manifest's `odoo_version` /
`core.ref` selects **which** commit; the working-tree files still must be fetched.

## Affected Areas

- `src/odoo_forge_workspace/provider.py` — `_clone_and_replace` (the commands to
  change), `promote` (must keep working against the new clone shape).
- `tests/adapters/test_workspace_provider.py` — 15 tests, **all** mock
  `subprocess.run` directly; none spawn real git or exercise a real repo.
  `test_checkout_clones_to_temp_and_replaces_into_dest` and
  `test_clone_passes_url_as_positional_after_end_of_options` only assert on argv
  shape — trivially satisfied by any clone strategy.
  `TestPromote::test_promote_creates_worktree_and_raises_if_already_writable`
  asserts on `worktree add -b <branch>` argv, decoupled from clone strategy.
- `tests/cli/test_project.py` only reuses a `git clone` argv to synthesize a
  `CheckoutError` message; not flag-sensitive.
- No `file://` remote or real-git integration test exists for the workspace
  provider today (unlike the docker/postgres adapters, which have
  `*_integration.py` suites).

## Approaches

### 1. Partial clone (`git clone --filter=blob:none --no-checkout`) — RECOMMENDED

Downloads the full commit/tree graph but defers blobs; the existing follow-up
`checkout --detach <commit>` already triggers on-demand blob fetch for exactly
that commit's files. Since `promote`'s `worktree add` targets the same commit
`source` is already at, the blobs it needs are already locally cached from the
initial checkout — `promote` stays offline-safe after the initial checkout.
`git worktree add` on a partial-clone repo is natively supported (git ≥ 2.19);
worktrees reuse the parent repo's object store / promisor config.

- **Pros:** keeps `log`/`blame`/ancestry-dependent flows intact; low risk to the
  `promote`/`unlock` contract (object model unchanged, blobs merely deferred);
  safest incremental change.
- **Cons:** still downloads the full commit+tree graph (real but not maximal
  savings); requires the remote to advertise `uploadpack.allowFilter` (server
  opt-in — GitHub supports it; self-hosted remotes are not guaranteed to).
- **Effort:** Low–Medium.

### 2. Shallow single-commit fetch (`git init` + `remote add` + `fetch --depth 1 origin <commit>` + `checkout --detach FETCH_HEAD`)

Minimal possible download — only the target commit's tree/blobs. `worktree add`
should still work structurally, but this combination is untested here and
carries more uncertainty. Depends on server-side
`uploadpack.allowReachableSHA1InWant`/`allowAnySHA1InWant` to permit fetch-by-SHA
— a narrower, less-commonly-enabled capability than `allowFilter`, and **not**
enabled by default on a vanilla `git init --bare` fixture.

- **Cons:** truncates history entirely (shallow grafts complicate later
  `log`/`blame`); bigger rewrite of `_clone_and_replace` (manual remote wiring);
  higher risk to the barely-tested `promote` interaction.
- **Effort:** Medium.

## Critical test-design finding

Every current workspace-provider test mocks `subprocess.run`, so changing the
clone strategy is **invisible** to the existing suite — those tests keep passing
unmodified regardless of strategy, giving false confidence. Validating that
`worktree add` genuinely still works against a `--filter=blob:none` clone
requires a **new integration-style test** spawning real git against a real local
fixture (bare repo or `file://`), which does not exist today. Local bare-repo
fixtures do **not** enable `uploadpack.allowFilter` by default — the test fixture
must explicitly set `uploadpack.allowFilter=true` (and confirm git's local
same-filesystem path still honours the filter negotiation).

## Recommendation

**Partial clone (`--filter=blob:none --no-checkout`)** — preserves git semantics
closest to today's behavior (full commit/tree graph, lazy blobs), has a
broader-supported server capability requirement than arbitrary-SHA fetch, and
keeps `promote`'s same-commit `worktree add` offline-safe post-initial-checkout.
Treat shallow fetch-by-SHA as a possible future optimization once partial clone's
real-world savings against Odoo core are measured.

## Open questions for design/prototype

1. Measure actual blob-skip savings of `--filter=blob:none` against the real Odoo
   core repo.
2. Confirm `checkout --detach <commit>` reliably triggers lazy blob fetch with no
   extra flags.
3. Empirically confirm `worktree add` from a partial-clone `source` needs zero
   additional network fetch when targeting the same already-checked-out commit.
4. Design the new offline/hermetic integration test (local fixture with
   `uploadpack.allowFilter=true`, real git subprocess, full
   clone→checkout→promote→worktree-add path).
5. Define adapter behavior when a remote does not advertise `allowFilter` (silent
   full-clone fallback vs. hard fail).
6. Decide whether this needs to be configurable per-repo (manifest opt-out) or a
   transparent attempt-and-fallback.

## Risks

- False confidence from unchanged unit tests (all mock `subprocess.run`) — a real
  integration test is mandatory, not optional.
- Server-side capability dependency (`uploadpack.allowFilter`) is outside this
  codebase's control; fallback behavior needs explicit design.
- `promote`/`worktree add` interaction with partial clones is reasoned from git
  semantics, not yet empirically verified in this repo.
