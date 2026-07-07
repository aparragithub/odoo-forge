# Exploration — phase-2-manifest-core

**Change:** phase-2-manifest-core
**Phase:** sdd-explore
**Date:** 2026-07-06
**Store:** hybrid (Engram id 2280 + this file)
**Goal:** Independently validate the approved slice-1 design (`docs/superpowers/specs/2026-07-06-phase-2-manifest-core-design.md`) against the parent product spec, Phase 1 factory conventions, and the real `odoo-idp` repo. Treat the design as an idea, not a settled contract.

## Current state

- Approved design proposes a pure Pydantic v2 domain (Manifest / Lockfile / composition / drift) plus a thin `forge validate` CLI, gated by import-linter.
- Parent spec defines the onion/layer model (§2.1–2.3), backend contract (§2.4), hexagonal architecture (§6.1).
- Phase 1 `factory/` bakes Odoo core into the image at a resolved git SHA (`ODOO_REVISION`, via `git ls-remote` in `factory/build.sh:resolve_odoo_revision`), and reserves `/mnt/community`, `/mnt/enterprise`, `/mnt/localization`, `/mnt/custom`, `/mnt/worktrees` as workspace mount points scanned by `entrypoint.sh:build_addons_path`.
- **`odoo-idp` is accessible** at `/home/aparra/Development/wk/odoo-idp` — inspected directly, not fabricated. `.gitmodules` = odoo core + enterprise + 17 ingadhoc localization repos as git submodules. `platform/web/models/repo_source.py` = real `RepoSourceTable` / `ProjectRepoBindingTable.replaced_repo_source_id`. `platform/cli/idp_scripts/services/repo_catalog.py` = drift-detection precedent + `ADDON_LAYERS`.

## Findings

1. **Community/core layer has no source pin in the schema (real gap).** `Manifest.odoo_version` is a bare string; there is no `layers` entry for the community/core layer, yet §2.2 requires ALL layers (community included) to materialize as source for the workspace, and Phase 1 already resolves community to an exact SHA. The schema has nowhere to carry that pin.

2. **Edition-gating is coarser than reality.** `odoo-idp` has `odoo-argentina-ee` — an enterprise-only repo living inside the localization grouping, not the enterprise layer. The design's rule ("community edition MUST NOT declare an enterprise layer") checks at whole-layer granularity with no per-repo edition tag. The fire test may under-validate or misfire on this repo.

3. **Fire-test fixture is authorable now.** `odoo-idp` is accessible (contrary to the task's hedge). Multi-repo-per-layer (`GitLayer.repos: list[GitRepo]`) is confirmed expressible. But findings #1 and #2 mean the schema as drafted still cannot fully express `odoo-idp` — fix those first, or let the fire test surface them per the design's own philosophy.

4. **"Discriminated by field presence" is not Pydantic v2's tagged-union mechanism.** It describes v2 default *smart-mode* union validation (works here because the two models have non-overlapping required fields), not an explicit `Field(discriminator=...)` tagged union. Cost: smart-mode yields ambiguous dual-model error messages on malformed input, conflicting with the acceptance criterion "reports clear errors on malformed input." Recommend a literal `type` tag field.

5. **Manifest hash purity is implied, not specified.** `Lockfile.generated_from` must hash the canonicalized in-memory `Manifest` model, never raw file bytes — never stated. `MaterializedState` injection is correctly pure. Without an explicit statement a future impl could leak file IO into hash logic, and import-linter's current list (no `hashlib`/`pathlib` note) wouldn't catch it.

6. **import-linter: no false conflict.** `git` in `forbidden_modules` blocks `import git` (GitPython); it does not collide with `GitRepo`/`GitLayer` class names (import-linter checks import statements, not identifiers). List omits `requests`/`httpx` but that's acceptable this slice (nothing calls a registry yet).

7. **Phase 1 consistency mostly confirmed.** `odoo_version` as string (not enum) correctly avoids duplicating `factory/versions.yaml`. Open item: no declared mapping from manifest `Layer.name` to the five `/mnt/*` mount roots in `entrypoint.sh` — likely Slice 3's job but not flagged as a dependency anywhere.

## Recommendation

Resolve findings #1, #2, and #4 in `sdd-propose`/`sdd-design` before locking the schema. The design itself calls the schema "the deliverable" validated by the fire test, so these belong before that test is written. Findings #5, #6, #7 are lower-severity clarifications.

## Risks

- Fire test may pass superficially while missing the `odoo-argentina-ee` edition-gating case (#2) → false confidence.
- Community/core pin gap (#1) will resurface as a Slice 3 blocker if not resolved now.
- Undocumented smart-union behavior (#4) may cause confusing CLI error UX contradicting an explicit acceptance criterion.

## Ready for proposal

Yes — with `sdd-propose` explicitly addressing findings #1, #2, and #4 as schema amendments.
