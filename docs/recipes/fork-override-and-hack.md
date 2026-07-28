# Override a repo with your fork — and hack on it locally

Two related situations, one recipe:

- a third-party module needs your patch, and upstream hasn't merged it;
- you need to edit a projected repo locally, but checkouts are read-only.

## Part 1 — declare the override

`overrides` swaps one repo inside one layer for your fork, at your ref,
without touching the layer definition itself:

```yaml
layers:
  - type: git
    name: oca-web
    repos:
      - url: https://github.com/OCA/web.git
        ref: "19.0"

overrides:
  - layer: oca-web
    repo: https://github.com/OCA/web.git
    fork: https://github.com/you/web.git
    ref: "19.0-fix-widget"
```

Then the usual cycle:

```bash
uv run forge lock    --manifest project.yaml
uv run forge project --manifest project.yaml
```

The lock records your fork's branch resolved to an exact commit. The layer
declaration stays pristine — remove the override entry when upstream merges,
re-lock, and you are back on upstream.

## Part 2 — make a checkout writable

`forge project` materializes repos as **read-only** checkouts on purpose:
the workspace is a projection of the lock, and casual edits would be silent
drift. When you genuinely need to edit — developing the patch that becomes
the fork above — promote the repo to a writable worktree:

```bash
uv run forge unlock --manifest project.yaml \
  --layer oca-web \
  --repo https://github.com/OCA/web.git
```

Now edit, commit, and push to your fork from that worktree. Your flow becomes:

1. `unlock` the repo, develop the fix on a branch, push it to your fork.
2. Add the `overrides` entry pointing at your fork and branch.
3. `lock` + `project` — the workspace now runs your patched, pinned code.
4. Upstream merges? Delete the override, re-lock, done.

The point of the ceremony: at every moment, `project.lock` states exactly
whose code, at exactly which commit, is running — including your patches.
