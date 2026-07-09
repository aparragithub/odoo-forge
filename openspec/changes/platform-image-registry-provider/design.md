# Design: Platform Image Registry Provider

## Technical Approach

Implement SP-1 by expanding the existing GHCR seam into a four-verb `ImageRegistryProvider` contract while keeping SP-1 as source of truth. `sp1-a` remains the foundation for reference parsing and registry diagnostics; `sp1-b` remains the owner of runtime container pulls inside `DockerBackendProvider.run()`. This slice adds only registry-port behavior: publish an already-built image, resolve a mutable ref to a digest, check digest existence, and optionally pre-pull a digest into the local Docker daemon.

## Architecture Decisions

| Decision | Choice | Alternatives considered | Rationale |
|---|---|---|---|
| Publish ownership | `publish()` accepts an already-built local image ref and pushes it; it does **not** call `factory/build.sh` | Wrap Phase 1 build script inside publish | Keeps SP-1 focused on registry concerns, reuses Phase 1 outputs directly, and avoids mixing build orchestration into the port |
| Pull boundary | `pull()` is a registry prefetch that returns a `LocalImageRef`; `DockerBackendProvider.run()` keeps its own runtime `docker pull` | Move all pulls into the backend or let registry pull start containers | Freezes the ownership line required by spec: registry pull prepares availability, backend pull owns execution-time guarantees |
| Value types | Introduce lightweight core aliases/newtypes for `ImageRef`, `ImageDigestRef`, and `LocalImageRef`; GHCR adapter may return the same canonical digest string as the local handle on first slice | Keep anonymous `str` everywhere; add heavy Pydantic models | Named value types clarify contracts now, keep signatures cheap, and leave room for future non-Docker-backed handles |
| Error ownership | Extend `odoo_forge.image_registry.errors`; parsing/unsupported errors stay in core helpers, subprocess/API classification stays in adapter, CLI renders a single `RegistryError` boundary | Let CLI classify stderr or create adapter-private errors | Preserves pure-core rules and matches existing adapter->typed-domain-error->CLI pattern |

## Data Flow

```text
image-publish --ref local-tag
CLI -> normalize publish input -> GhcrImageRegistryProvider.publish()
    -> docker push local-tag
    -> docker buildx imagetools inspect pushed-ref
    -> ImageDigestRef

image-pull --ref digest
CLI -> normalize digest -> GhcrImageRegistryProvider.pull()
    -> docker pull digest
    -> LocalImageRef

image-run --odoo-image-ref digest
CLI -> plan_backend(..., odoo_image=digest)
    -> DockerBackendProvider.run()
    -> runtime docker pull remains here
```

## File Changes

| File | Action | Description |
|---|---|---|
| `src/odoo_forge/ports/image_registry_provider.py` | Modify | Replace `resolve`/`validate` contract with `publish`/`pull`/`resolve_digest`/`exists` using named value types and lazy annotations |
| `src/odoo_forge/image_registry/types.py` | Create | Define lightweight reference aliases/newtypes used by the port and tests |
| `src/odoo_forge/image_registry/errors.py` | Modify | Add publish/pull-specific typed failures while keeping existing malformed/unsupported/auth/not-found/unavailable ownership |
| `src/odoo_forge/image_registry/reference.py` | Modify | Split normalization helpers for publishable local refs vs registry digest/tag refs |
| `src/odoo_forge/image_registry/__init__.py` | Modify | Re-export new types and errors |
| `src/odoo_forge_registry/provider.py` | Modify | Add GHCR-first `publish`, `pull`, `resolve_digest`, and `exists` adapter behavior over docker/buildx tooling |
| `src/odoo_forge_cli/main.py` | Modify | Replace `image-validate` with `image-exists`; add `image-publish` and `image-pull`; keep `image-resolve` name but route to `resolve_digest` |
| `tests/ports/test_image_registry_provider.py` | Modify | Update protocol and signature conformance coverage |
| `tests/adapters/test_registry_provider.py` | Modify | Cover push/pull/inspect command mapping and typed error classification |
| `tests/cli/test_image_registry.py` | Modify | Cover new command surface and fail-fast diagnostics |

## Interfaces / Contracts

```python
from __future__ import annotations

class ImageRegistryProvider(Protocol):
    def publish(self, ref: ImageRef) -> ImageDigestRef: ...
    def pull(self, digest: ImageDigestRef) -> LocalImageRef: ...
    def resolve_digest(self, ref: ImageRef) -> ImageDigestRef: ...
    def exists(self, digest: ImageDigestRef) -> bool: ...
```

CLI shape stays `image-*` for consistency:
- `image-publish --ref <local-image-ref>` -> prints digest ref
- `image-resolve --ref <registry-tag>` -> prints digest ref
- `image-exists --ref <digest-ref>` -> prints `true`/`false`
- `image-pull --ref <digest-ref>` -> prints local image ref

## Testing Strategy

| Layer | What to Test | Approach |
|---|---|---|
| Unit | Reference normalization, typed errors, protocol signatures | Extend pure-core pytest coverage and signature assertions |
| Integration | GHCR adapter command mapping for push/pull/inspect/exists | Monkeypatch `subprocess.run` and assert argv + error classification |
| CLI | Output, exit codes, fail-fast boundaries, no backend invocation from registry commands | Typer runner tests with fake provider |
| Boundary | Runtime pull ownership stays in Docker backend | Keep `tests/backend/test_plan.py` and add CLI assertions that registry commands never call backend factories |

## Migration / Rollout

No data migration required. Deliver as chained PRs: (1) port/types/spec/tests, (2) GHCR adapter + CLI commands, (3) backend-alignment follow-up only if apply reveals a contract mismatch. This matches the 400-line review budget and keeps the boundary freeze reviewable.

## Open Questions

- [ ] Should `LocalImageRef` remain the pulled digest string in slice 1, or should CLI retag it to a stable local alias for ergonomics?
- [ ] Does Mirgor need GHCR as an explicit init default now, or can adapter selection remain implicit until SP-4/SP-6 wiring?
