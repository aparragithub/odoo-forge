# Proposal: Wire the GitHub Actions Pipeline Adapter into the CLI

## Intent

`GitHubActionsPipelineProvider` (ADAPTER-PIPELINE-GITHUB) is implemented and
tested but structurally unreachable: no `_make_pipeline_provider` factory
exists in the composition root, no `pipeline` command family exists, and
`main.py` never imports the adapter package. The archived adapter design
explicitly deferred this wiring. Today nobody — human or automation — can
trigger or inspect a CI run through `forge`. This change closes that gap by
wiring the adapter through the existing composition-root → command →
`main.py` registration pattern already used by `image`/`backend`/`manifest`.

## Scope

### In Scope
- `_make_pipeline_provider()` factory in `src/odoo_forge_cli/_composition.py`,
  constructing `GitHubActionsPipelineProvider` over `GitHubActionsRestTransport`.
- Env-var-sourced config for token/owner/repo/ref (no manifest field exists
  today; this is a minimal seam, not a secrets redesign), following the
  `_doctor_age_key_file` / `SOPS_AGE_KEY_FILE` env-var-override precedent.
- New `src/odoo_forge_cli/commands/pipeline.py` exposing exactly two commands:
  **trigger** and **status** (mirrors the two most operationally useful port
  methods; `logs` is deferred — see Out of Scope).
- Registration of `pipeline.register(app)` in `src/odoo_forge_cli/main.py`.
- `tests/cli/test_pipeline.py` mirroring `tests/cli/test_image_registry.py`
  (`CliRunner` + `monkeypatch.setattr(_composition, "_make_pipeline_provider", ...)`).

### Out of Scope
- A `pipeline-logs` command (same wiring shape; deferred to keep this slice
  small and reviewable — can follow as a fast-follow once trigger/status land).
- Manifest schema changes to carry owner/repo/ref (env vars only, for now).
- Any change to `PipelineProvider`, neutral types, or the adapter's internal
  behavior/tests (already covered by CHG-FIRST-PIPELINE-ADAPTER).
- A general secrets-management story for GitHub tokens (SOPS/manifest-backed
  secret injection like `_make_backend_provider` uses) — deferred; env var
  only for this slice.
- Resolving whether import-linter contracts permit `odoo_forge_cli` →
  `odoo_forge_pipeline_github` — flagged as a design-phase verification item,
  not resolved here.

## Capabilities

### New Capabilities
- `pipeline-cli-command`: CLI-level trigger/status commands backed by the
  composition-root factory, covering command shape, arg validation, error
  boundary, and env-var config resolution (no existing spec covers CLI UX for
  pipeline operations — `pipeline-provider` only covers the port).

### Modified Capabilities
- None. `github-actions-pipeline-adapter` and `pipeline-provider` specs are
  unchanged; this change is purely a new consumer of the existing port.

## Approach

Follow the exact `image.py` shape: each Typer command in `pipeline.py` calls
`_composition._make_pipeline_provider()` (module-qualified), converts CLI args
into the port's neutral request type, invokes the port method, `typer.echo`s
the result, and catches the port's domain error type into a single
`error: ...` line + `typer.Exit(code=1)`. The factory reads
`token`/`owner`/`repo`/`ref` from env vars (exact names TBD in design,
following the `SOPS_AGE_KEY_FILE` precedent) and raises a clear CLI error if
required vars are missing — no silent defaults for `token`.

## Affected Areas

| Area | Impact | Description |
|------|--------|--------------|
| `src/odoo_forge_cli/_composition.py` | Modified | New `_make_pipeline_provider()` factory |
| `src/odoo_forge_cli/commands/pipeline.py` | New | `trigger`/`status` Typer commands + `register(app)` |
| `src/odoo_forge_cli/main.py` | Modified | Import + register `pipeline` command family |
| `tests/cli/test_pipeline.py` | New | CliRunner + `_composition` monkeypatch tests |
| `pyproject.toml` | Possibly Modified | Only if import-linter needs a new allowed contract (design-phase check) |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Import-linter forbids `odoo_forge_cli → odoo_forge_pipeline_github` | Med | Verify contract direction explicitly in design phase before writing code |
| Missing env vars produce unclear CLI failures | Med | Explicit validation with a single `error: missing <VAR>` message, tested |
| Token handling accidentally logged/echoed | Low | Never echo token value; test asserts it's absent from output |
| Scope creep into full secrets story or `logs` command | Low | Explicit Out of Scope list above |

## Rollback Plan

Revert the branch: remove `_make_pipeline_provider`, delete
`commands/pipeline.py` and its `main.py` registration, delete
`tests/cli/test_pipeline.py`. The adapter package itself and the port are
untouched, so no data or contract migration is involved.

## Dependencies

- CHG-FIRST-PIPELINE-ADAPTER (archived) — provides the adapter being wired.
- Composition-root pattern in `_composition.py` and command pattern in
  `commands/image.py` — precedents to mirror exactly.

## Success Criteria

- [ ] `forge pipeline-trigger` / `forge pipeline-status` (exact names
      confirmed in design) invoke `GitHubActionsPipelineProvider` via the
      composition root and print neutral-type results.
- [ ] Missing env vars produce a clear `error: ...` + exit code 1, tested.
- [ ] `tests/cli/test_pipeline.py` passes using the `_composition` monkeypatch
      pattern (no live network).
- [ ] Full test suite (`uv run pytest`) green; import-linter check passes.

## Delivery Note

Estimated size: small, single PR (one factory + one command module + one test
file, well under the 400-line review budget). No PR chaining anticipated.

## Proposal Assumptions (auto mode — no interactive round)

- Command surface limited to `trigger` + `status`; `logs` deferred as a
  fast-follow rather than bundled in.
- Config source is env vars, not manifest fields — matches the only existing
  precedent (`SOPS_AGE_KEY_FILE`) and avoids inventing new manifest schema.
- Exact env var names and exact CLI command names are left to sdd-design.
- Import-linter contract direction (`odoo_forge_cli` → `odoo_forge_pipeline_github`)
  is an explicit open verification item for sdd-design, not resolved here.
