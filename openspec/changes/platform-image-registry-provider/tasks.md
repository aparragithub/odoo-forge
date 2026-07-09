# Tasks: Platform Image Registry Provider

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | 450-650 |
| 400-line budget risk | High |
| Chained PRs recommended | Yes |
| Suggested split | PR 1: contract/spec/types/tests → PR 2: GHCR adapter + CLI |
| Delivery strategy | force-chained |
| Chain strategy | stacked-to-main |

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: stacked-to-main
400-line budget risk: High

### Suggested Work Units

| Unit | Goal | Likely PR | Notes |
|------|------|-----------|-------|
| 1 | Freeze the new port contract and value types | PR 1 | Base from main; includes spec-aligned core tests and import boundary updates. |
| 2 | Ship GHCR-first publish/resolve/pull/exists flows | PR 2 | Base from PR 1; includes CLI wiring and adapter tests. |

## Phase 1: Foundation / Contract

- [x] 1.1 Update `src/odoo_forge/ports/image_registry_provider.py` to the SP-1 protocol: `publish`, `pull`, `resolve_digest`, and `exists`.
- [x] 1.2 Create `src/odoo_forge/image_registry/types.py` for `ImageRef`, `ImageDigestRef`, and `LocalImageRef`; re-export from `src/odoo_forge/image_registry/__init__.py`.
- [x] 1.3 Extend `src/odoo_forge/image_registry/errors.py` and `reference.py` for publish/pull/exist failures without touching `PublishedLayer`.

## Phase 2: Core Implementation

- [x] 2.1 Implement GHCR-first `publish()` and `resolve_digest()` in `src/odoo_forge_registry/provider.py` using existing digest-inspection patterns.
- [x] 2.2 Implement `pull()` as local-daemon prefetch only and `exists()` as a no-layer-transfer registry check.
- [x] 2.3 Keep `DockerBackendProvider.run()` ownership unchanged in `src/odoo_forge_docker/provider.py`; no runtime-pull duplication.
- [x] 2.4 Update `src/odoo_forge_cli/main.py` to add `image-publish`/`image-pull`, rename validate to `image-exists`, and route resolve to `resolve_digest`.

## Phase 3: Testing / Verification

- [x] 3.1 Update `tests/ports/test_image_registry_provider.py` for protocol conformance and new signature assertions.
- [x] 3.2 Add adapter tests in `tests/adapters/test_registry_provider.py` for push/pull/inspect command mapping and auth/not-found/unsupported classification.
- [x] 3.3 Extend `tests/cli/test_image_registry.py` for CLI outputs, exit codes, and the no-backend-call boundary.

## Phase 4: Cleanup / Documentation

- [x] 4.1 Update `docs/specs/platform/SP-1-image-registry-provider.md` and `openspec/changes/platform-image-registry-provider/specs/image-registry-provider/spec.md` if wording drifts during apply.
- [x] 4.2 Remove any temporary compatibility glue after PR 2; keep `PublishedLayer` cleanup explicitly out of scope.
