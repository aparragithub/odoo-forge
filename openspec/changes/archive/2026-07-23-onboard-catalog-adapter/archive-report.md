# Archive Report — onboard-catalog-adapter

**Change**: onboard-catalog-adapter (concrete `CatalogIndex` adapter + `forge onboard` dual-mode dispatch)
**Mode**: openspec | branches feat/onboard-catalog-adapter-pr1 (#139), feat/onboard-catalog-adapter-pr2 (#143, superseding auto-closed #140)
**Result**: PASS — archived

## Verification

- Verify report: PASS WITH WARNINGS — 0 CRITICAL, 2 WARNING (both documentation/tracking, non-blocking: tasks.md's R.1–R.4 reconciliation checkboxes lagged their already-implemented/tested decisions, since fixed; missing a persisted PR2 apply-progress Engram record).
- Real execution evidence re-confirmed at verify time on `main` (HEAD `826129c`): `uv run pytest` 945 passed / 17 deselected; `uv run ruff check .` / `format --check .` clean; `uv run mypy` clean, 166 files, no new errors.
- Frozen-symbol constraint held: zero diff across both PRs to `ProjectCatalogResolver`, `plan_backend`, `DockerBackendProvider.run`, `plan_projection`, `project_workspace`. The one in-scope core edit (`@runtime_checkable` on `CatalogIndex`) was explicitly justified in tasks.md R.5 and is not one of the five frozen symbols.
- Spec compliance: 3 requirements / 6 scenarios (`catalog-index-adapter`, new capability) + 5 requirements / 9 scenarios (`manifest` delta, `forge-onboard-cli-catalog-driven`), all covered by passing tests (12 unit + 21 CLI integration = 33 focused tests).

## Task Completion

- `tasks.md`: all 53 numbered tasks checked across Phases 1–7 (adapter RED/GREEN, composition-factory RED/GREEN, `onboard` dispatch RED/GREEN, refactor/verification), plus reconciliation decisions R.1–R.5 checked off during archive prep (R.1–R.4 were functionally complete but their checkboxes had lagged; fixed and re-verified before archiving).

## Review History

Both PRs went through the native 4R bounded review (risk/resilience/readability/reliability), each with one correction round:

- **PR1** (#139): first pass found 3 CRITICAL, deterministic bugs in `YamlCatalogIndex` — an `AttributeError` on alias-only dimensions (`project_slug`/`manifest_name`), a raw `TypeError` on a non-list `records` value, and a broken catalog silently reported as `catalog-not-found` (non-dict top-level YAML). All fixed test-first; re-review approved.
- **PR2** (#143): first pass found a real (non-blocking-severity, but user-directed) gap — the catalog-driven `onboard` path skipped the Enterprise-credential preflight/binding that the `--manifest` path always runs. Fixed test-first (both modes now run the identical preflight/binding sequence); re-review approved with one remaining non-blocking readability note (duplicated preflight/compose block between the two mode functions, flagged for a future cleanup pass).

## Incidental Fixes (pre-existing, unrelated to this change)

While chasing CI green for this stack, `main` itself was found red on three independent pre-existing issues, each fixed as its own small PR before this change's PRs could merge cleanly:

- `fix(postgres_docker): chain DatabaseReadinessError from timeout cause` (ruff B904) — PR #141
- `fix(cli): explicitly re-export plan_backend from commands.backend` (mypy `no_implicit_reexport`) — folded into PR #141
- A `ruff format` drift in the same file — folded into PR #141

## Delivered Contract Summary

- **New adapter package** `src/odoo_forge_catalog/` — `YamlCatalogIndex` (implements `CatalogIndex.find_matches` against a single `catalog.yaml`), `CatalogSourceError`.
- **Composition root**: `_make_catalog_index()` factory in `src/odoo_forge_cli/_composition.py`.
- **`forge onboard` dual-mode dispatch** in `src/odoo_forge_cli/commands/manifest.py`: `--manifest <path>` (unchanged local validate+materialize) vs. positional `<cliente>` (catalog resolve → materialize via `plan_projection`/`project_workspace` → create instance via `plan_backend`/`DockerBackendProvider.run`), both/neither → `ManifestError`.
- `data_policy_default`/`target_default` are transported from the resolved catalog record but explicitly not actioned this slice (ADR-0001 sequencing) — a documented follow-up.

## Spec Sync

- **New capability**: `openspec/specs/catalog-index-adapter/spec.md` created verbatim from the delta (no prior main spec existed).
- **Delta merge**: `openspec/specs/manifest/spec.md` gained the `forge-onboard-cli-catalog-driven` capability section (5 requirements / 9 scenarios) appended after the existing `unlock` requirements — pure addition, no existing requirement modified or removed.

## Source Artifact Traceability (Engram observation IDs)

| Artifact | Engram ID |
|----------|-----------|
| Explore | sdd/onboard-catalog-adapter/explore |
| Proposal | sdd/onboard-catalog-adapter/proposal |
| Spec (delta) | sdd/onboard-catalog-adapter/spec |
| Design | sdd/onboard-catalog-adapter/design |
| Tasks | sdd/onboard-catalog-adapter/tasks (id 10047) |
| Apply-progress (PR1/Unit 1) | sdd/onboard-catalog-adapter/apply-progress (id 10048) |
| Verify report | sdd/onboard-catalog-adapter/verify-report (id 10052) |
| Archive report (this document) | sdd/onboard-catalog-adapter/archive-report (id 10053) |

## SDD Cycle Status

Spec-sync complete. Task-completion gate passed (53/53, reconciliation checkboxes fixed). Verification PASS with 0 CRITICAL. Change folder moved to `openspec/changes/archive/2026-07-23-onboard-catalog-adapter/`, no active reference remains under `openspec/changes/`. Cycle closed.
