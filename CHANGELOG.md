# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Breaking

- **Removed `GitRepo.requires_edition`.** Per-repo edition gating is gone.
  Manifests that still set `requires_edition` on a repo (or, previously, on a
  `GitLayer`/`PublishedLayer`) now fail validation with an actionable error
  naming the replacement fields instead of silently ignoring or misapplying
  the flag.

  **Migration:**
  - If the repo/layer *is* the enterprise source, move it to the new
    top-level `enterprise:` block (sibling of `core:`):
    ```yaml
    enterprise:
      url: https://github.com/<org>/enterprise.git
      ref: "19.0"
    ```
    The `enterprise:` block is now **required** when `edition: enterprise`
    and **forbidden** otherwise (symmetric validation).
  - If the layer merely *requires* enterprise to be present (a precondition,
    not the enterprise source itself), set `requires_enterprise: true` on
    the `GitLayer`/`PublishedLayer` instead:
    ```yaml
    - type: git
      name: adhoc-ee
      requires_enterprise: true
      repos: [...]
    ```
    `requires_enterprise` is a coherence-only guard: it makes `compose()`
    reject the layer under `edition: community`, but it does **not** affect
    mount classification (unlike the old `requires_edition` shortcut).

- **`localization` is no longer a system/reserved mount root.** It is now an
  ordinary user category. A layer declaring `category: localization` mounts
  under `/mnt/custom/localization/` instead of the old top-level
  `/mnt/localization/`. The container image no longer pre-creates
  `/mnt/localization`.

- **User-declared categories now nest under `/mnt/custom/<category>/`.** The
  system/structural mount roots are reduced to exactly `community`,
  `enterprise`, and `worktrees`; every user layer mounts under the `custom`
  parent namespace (uncategorized → `/mnt/custom/default/`). Consumers that
  hard-coded a flat `/mnt/<category>/` projection path must update to the
  nested layout.

- **`MOUNT_ROOTS` shape change.** The mount-root table is now derived from the
  manifest (`build_mount_roots(base, manifest)`) rather than a static
  module-level constant, and `MountRoot` widens from a closed `Literal[...]`
  to `str`. The CLI threads a per-manifest host table via `_host_roots(parsed)`
  instead of an import-time `_HOST_ROOTS` global.

### Added

- `EnterpriseLayer` model (`url`, `ref`) as a singleton, sibling of `core:`.
  The composed onion chain now inserts it at position 2 when present:
  `core -> enterprise -> layers -> client`.
- `Manifest.enterprise: EnterpriseLayer | None` with symmetric validation
  (required iff `edition == "enterprise"`, forbidden otherwise).
- `classify_root` maps the `EnterpriseLayer` singleton to mount root
  `"enterprise"`, mirroring how `CoreLayer` maps to `"community"`.
- `requires_enterprise: bool = False` on `GitLayer` and `PublishedLayer`
  (guard-only precondition, defaults to `False`, no mount effect).
- **Open, user-declared layer categories.** `category` accepts any validated
  slug (`^[a-z0-9]([a-z0-9-]*[a-z0-9])?$`, 1–63 chars) instead of a closed
  enum; `None` normalizes to `"custom"`. There is intentionally **no**
  reserved-name blocklist — a category named `community`/`enterprise`/
  `worktrees` is just a plain subfolder under `/mnt/custom/` and can never
  collide with a system root.

### Changed

- `factory/entrypoint.sh` `build_addons_path` now scans the fixed system roots
  (`worktrees`, `community`, `enterprise` — `worktrees` first so an
  `unlock`-promoted worktree shadows the read-only copy via `addons_path`
  first-match) and then globs `/mnt/custom/*` categories (sorted), with
  `/opt/odoo/addons` last. Arbitrary user categories mount without image
  changes.
- `factory/Dockerfile` pre-creates only `community`, `enterprise`,
  `worktrees`, and the `custom` parent (dropped the hard-coded `localization`
  root); per-category subdirectories are created at mount time.

See `docs/adr/0002-edition-enterprise-y-categorias-de-mount-abiertas.md` for
the full rationale.
