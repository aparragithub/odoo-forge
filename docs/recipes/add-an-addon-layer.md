# Add an addon layer

You want modules from OCA (or any Git repository) available in your project.
In odoo-forge that is a declaration, not a clone.

## 1. Declare the layer

Add a `git` layer to your `project.yaml`. Each layer has a name and a list of
repos with a `url` and a `ref` (branch, tag, or commit):

```yaml
layers:
  - type: git
    name: oca-web
    repos:
      - url: https://github.com/OCA/web.git
        ref: "19.0"
```

The composed chain is always `core → enterprise (if any) → layers → client`:
later entries win when module names collide.

## 2. Lock it

```bash
uv run forge lock --manifest project.yaml
```

`lock` resolves every declared ref — including the new layer's — to an exact
commit SHA and writes `project.lock`. A branch name like `"19.0"` becomes a
pinned commit: two machines locking the same manifest at different times may
get different SHAs, but a given lock always reproduces the same tree.

## 3. Re-project and run

```bash
uv run forge project --manifest project.yaml
uv run forge run     --manifest project.yaml
```

`project` materializes the new repo under the fixed mount roots as a
**read-only checkout** (see [the fork recipe](fork-override-and-hack.md) for
making one writable). `run` provisions the backend with the layer's addons on
the `addons_path`.

## Updating the layer later

Re-run `forge lock`. If the branch tip moved, the lock changes and
`forge validate` reports drift until you re-`project`. That drift check is
the feature: a stale workspace can never silently run against a manifest that
promises something newer.

```bash
uv run forge validate --manifest project.yaml   # shows drift, if any
uv run forge project  --manifest project.yaml   # re-materializes to the lock
```

## Pinning instead of tracking

To freeze a layer regardless of upstream movement, put the commit SHA directly
in `ref`. A tag is still a movable ref and may resolve to a different commit
when you re-lock.
