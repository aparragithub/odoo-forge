# Proposal: Platform Image Registry Provider

## Intent

Complete SP-1 by evolving the current GHCR-only resolve/validate slice into the platform `ImageRegistryProvider` contract for publish, pull, digest resolution, and existence checks. Reuse Phase 1 publication and keep `sp1-a`/`sp1-b` as foundations.

## Scope

### In Scope
- Redefine the core port and error/value contract around `publish`, `pull`, `resolve_digest`, and `exists`.
- Extend the GHCR-first adapter and CLI to expose foundation-level publish/pull/resolve/exists flows.
- Update spec, tests, and import-boundary coverage to match SP-1 and plan chained delivery.

### Out of Scope
- Deprecated `PublishedLayer` cleanup or any source-resolution redesign.
- Multi-registry runtime fan-out, new image-building infrastructure, or control-plane state.

## Proposal question round

- Should `publish` wrap the existing Phase 1 factory entrypoint, or accept only already-built local image refs?
- Should `pull` stay adapter-abstract for future remote backends, or return a Docker-local handle in this first slice?
- If Mirgor needs a default-at-init now, is GHCR the explicit default?

Assumptions: GHCR is the first adapter, Phase 1 stays the publication engine, and Docker runtime pull ownership stays in `DockerBackendProvider.run()`.

## Capabilities

### New Capabilities
- None

### Modified Capabilities
- `image-registry-provider`: expand the spec from GHCR resolve/validate only to the full SP-1 platform contract and CLI foundation.

## Approach

Keep the existing seam and adapter package, but replace the pre-platform contract with the SP-1 verbs. Reuse `.github/workflows/build-images.yml` and `factory/build.sh` for publication, keep backend runtime consumption as delivered in `sp1-b`, and use chained slices: contract/spec first, adapter+CLI second, backend alignment only if needed.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `openspec/specs/image-registry-provider/spec.md` | Modified | Align requirements to SP-1 source of truth. |
| `src/odoo_forge/ports/image_registry_provider.py` | Modified | Replace resolve/validate-only protocol. |
| `src/odoo_forge_registry/provider.py` | Modified | Add GHCR publish/pull/exists behavior. |
| `src/odoo_forge_cli/main.py` | Modified | Expose platform registry commands. |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| `pull` ownership overlaps backend runtime pull | Med | Freeze boundary in spec/design before apply. |
| Value types drift from future SP-3 needs | Med | Keep returned handles abstract and digest-first. |
| Review size exceeds 400 lines | High | Split into stacked PR slices. |

## Rollback Plan

Restore the current resolve/validate contract, remove new CLI commands, and keep `sp1-b` runtime digest consumption untouched.

## Dependencies

- Phase 1 image factory publication flow.
- Existing `sp1-a` GHCR seam and `sp1-b` runtime digest consumption.

## Success Criteria

- [ ] Spec/design freeze SP-1 boundaries without reintroducing `PublishedLayer` scope.
- [ ] GHCR adapter and CLI can publish, resolve, check existence, and support pull by digest under the new contract.
- [ ] Delivery is planned as chained reviewable slices within the 400-line budget.
