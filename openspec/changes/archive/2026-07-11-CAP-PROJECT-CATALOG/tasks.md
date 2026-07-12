# CAP-PROJECT-CATALOG Tasks

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | 240-340 |
| 400-line budget risk | Medium |
| Chained PRs recommended | Yes |
| Suggested split | PR 1 → PR 2 |
| Delivery strategy | auto-chain |
| Chain strategy | feature-branch-chain |

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: feature-branch-chain
400-line budget risk: Medium

## Task Plan

### 1. PR 1 — pure domain contract and resolver behavior

- [x] 1.1 **RED: lock the contract with focused tests first**
  - Create `tests/project_catalog/test_resolver.py`.
- Cover the spec scenarios:
  - one unique catalog record resolves to one full success result
  - zero matches returns `catalog-not-found`
  - multiple matches returns `ambiguous-resolution`
  - one matched record missing required outputs returns `invalid-catalog`
  - success preserves catalog-declared defaults as authoritative outputs
- Focused command:
  - `uv run pytest tests/project_catalog/test_resolver.py -q`
- Rollback boundary: revert only `tests/project_catalog/test_resolver.py` if the contract changes.

- [x] 1.2 **GREEN: implement the smallest pure-domain slice**
  - Add `src/odoo_forge/project_catalog/{__init__.py,interfaces.py,models.py,validation.py,resolver.py}`.
- Keep the boundary lookup-only: no onboarding, no control-plane persistence, no provider execution, no workspace materialization.
- Model the typed request, record, success result, and typed failures exactly as the spec/design require.
- Focused command:
  - `uv run pytest tests/project_catalog/test_resolver.py -q`
- Rollback boundary: revert only `src/odoo_forge/project_catalog/*` and the resolver tests.

- [x] 1.3 **TRIANGULATE: prove the slice fits project standards**
  - Run the targeted suite plus project checks:
  - `uv run pytest tests/project_catalog -q`
  - `uv run mypy src/odoo_forge/project_catalog tests/project_catalog`
  - `uv run ruff check src/odoo_forge/project_catalog tests/project_catalog`
  - `uv run lint-imports`
- If import-linter or typing reveals boundary drift, fix the smallest offending file only.
- Rollback boundary: revert the last code edit in `src/odoo_forge/project_catalog/*` before widening scope.

- [x] 1.4 **REFACTOR: simplify without expanding scope**
  - Remove duplication in normalization/assembly only if tests stay green.
- Keep public names stable; do not expand the capability boundary.
- Re-run:
  - `uv run pytest tests/project_catalog -q`
- Rollback boundary: revert the refactor-only hunk if it increases surface area.

### 2. PR 2 — acceptance evidence and portfolio handoff

- [x] 2.1 **Update readiness evidence for `AC-CAP-PROJECT-CATALOG-READY`**
  - Update `docs/specs/platform/portfolio.json` with the catalog-ready evidence and the downstream handoff boundary.
- Keep the evidence focused on the accepted identifiers, the resolved result shape, and the distinguishable failure classes.
- Do not add onboarding/request orchestration or control-plane semantics here.
- Verification command:
  - `python -m json.tool docs/specs/platform/portfolio.json >/dev/null`
- Rollback boundary: revert only `docs/specs/platform/portfolio.json`.

- [x] 2.2 **Final bounded verification before archive**
  - Re-run the focused tests after the evidence update:
  - `uv run pytest tests/project_catalog -q`
- Confirm the PR stays under the 400-line review budget and remains separable from downstream workflow work.
- Rollback boundary: revert PR 2 only; PR 1 remains independently shippable.
