# Exploration: Phase 2 Slice 4a — Registry Resolution

**Status:** exploration complete · **Next:** sdd-propose · **Change:** `phase-2-slice-4a-registry-resolution`

Slice 4a resolves `PublishedLayer.source`/`version` to lockfile entries via an HTTP
registry API call. It is a **network I/O boundary (HTTP)**, distinct from the Docker
(subprocess) boundary delivered in Slice 4b, and it plugs into `build_lock` / the
`SourceProvider` seam — **not** the backend chain.

## Current State

- `PublishedLayer` (`src/odoo_forge/manifest/schema.py:33-39`) is one arm of the
  discriminated `Layer` union with `source`/`version` fields but no resolution
  semantics defined anywhere in the codebase.
- `build_lock` (`src/odoo_forge/manifest/locking.py:22-39`) only handles `GitLayer`
  via `isinstance`; `PublishedLayer` silently falls through with no `else` branch
  (comment at lines 32-34 confirms this is intentional, deferred to registry
  resolution = Slice 4a). Confirmed by tests
  `tests/manifest/test_locking.py::test_published_layers_omitted_from_lock` and
  `test_composition_error_propagates_before_resolution`.
- `SourceProvider` port (`src/odoo_forge/ports/source_provider.py`) is a one-method
  `Protocol`: `resolve_ref(url, ref) -> commit-sha-str`. `GitSourceProvider`
  (`src/odoo_forge_git/git_provider.py`) is the only adapter, shelling out to
  `git ls-remote`.
- `ResolutionError` family (`src/odoo_forge/manifest/errors.py:31-64`:
  `RefNotFoundError`, `AuthenticationError`, `NetworkError`) is name/shape-generic —
  plausibly reusable for HTTP, but currently documented/tested only against git
  failure modes.
- `ResolvedRepo`/`ResolvedLayer` (`src/odoo_forge/manifest/lockfile.py:33-41`) model
  `{url, ref, commit}` — a git-checkout-shaped triple with no analog for a "pinned
  package version/digest."
- Composition root: `odoo_forge_cli/main.py::_make_provider()` (single concrete-adapter
  construction point), injected into `build_lock` from the `lock` command (lines
  192-226), which catches `ManifestError | ResolutionError | OSError` as one clean
  error boundary and writes `project.lock` atomically.
- Adapter convention: sibling packages (`odoo_forge_git`, `odoo_forge_docker`,
  `odoo_forge_workspace`) each own one I/O technology and are individually forbidden
  from being imported by `odoo_forge` via 5 import-linter contracts
  (`pyproject.toml:70-111`), alongside a blanket forbidden-modules list (`docker`,
  `git`, `subprocess`, `requests`, `httpx`, `typer`, etc.) on core.

## Affected Areas

- `src/odoo_forge/manifest/locking.py` — needs a resolution branch for `PublishedLayer`.
- `src/odoo_forge/manifest/schema.py` — `PublishedLayer.source`/`version` semantics
  are undefined; no registry protocol exists anywhere in the repo (test fixture uses
  placeholder `"registry://example/odoo-ee"`).
- `src/odoo_forge/ports/source_provider.py` — reuse-vs-fork candidate for a registry port.
- `src/odoo_forge/manifest/lockfile.py` — `ResolvedRepo` shape doesn't naturally fit a
  non-git resolved entry.
- `src/odoo_forge/manifest/errors.py` — HTTP failure modes (4xx/5xx/timeout/malformed
  response) have no typed home; existing types are git-flavored in docstring intent
  even if generically named.
- `pyproject.toml` `[tool.importlinter]` — needs a 6th forbidden-import contract once
  the new adapter package is named.
- `src/odoo_forge_cli/main.py` — `_make_provider()`/`lock` command wiring, since
  `build_lock` currently accepts exactly one `SourceProvider`.
- New sibling adapter package (name TBD, mirrors `odoo_forge_git`).

## Open Questions / Scope-Fork Candidates (resolve in sdd-propose)

1. **Registry protocol is undefined** — no documented API shape exists anywhere
   (roadmap, code, fixtures). This is the blocking decision; everything else depends
   on it.
2. **Port reuse vs new port** — can `SourceProvider.resolve_ref(source, version) ->
   resolved-str` be reused, or does richer registry response data (checksum, download
   URL) require a new `RegistryProvider` Protocol?
3. **Lockfile shape** — `ResolvedRepo{url, ref, commit}` is git-triple-shaped; a
   registry entry likely needs a different shape, implying a `LOCKFILE_SCHEMA_VERSION`
   bump and a back-compat story.
4. **Error taxonomy for HTTP** — reuse `RefNotFoundError`/`AuthenticationError`/
   `NetworkError` verbatim, or introduce a distinct `RegistryError` family under
   `ResolutionError`?
5. **Import-linter contract naming** — depends on the new adapter package name.
6. **CLI surface impact** — does `build_lock` gain a second provider param, or does one
   provider become a router dispatching per-layer-type?

## Conventions To Preserve

Strict TDD (RED-GREEN-REFACTOR planning required), pure-core/injected-Protocol-adapter
split enforced by import-linter, single composition root in
`odoo_forge_cli/main.py`, atomic lockfile writes (temp file + `os.replace`), typed
error families instead of leaking `httpx`/`requests` exceptions to the CLI boundary,
single clean `error:` line + exit(1) at the CLI boundary.

## Risks

- **Scope creep:** without a bounded registry protocol, this slice can balloon from
  "resolve one field pair via HTTP" into "design a package registry."
- **Lockfile schema risk:** a second resolved-entry shape may require a schema-version
  bump and migration story for existing `project.lock` files.
- **Silent semantic drift** if git-flavored error types are reused for HTTP without an
  explicit decision.

## Recommendation

Do not proceed to design yet. `sdd-propose` must first pin down a concrete (even
minimal) registry protocol assumption, then explicitly resolve the
port/lockfile/error-taxonomy fork questions as proposal decisions before scoping tasks.
**Open Question 1 (registry protocol) must be confirmed with the user** — is there a
real external registry protocol already, or do we define a minimal one?
