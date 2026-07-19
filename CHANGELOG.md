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
