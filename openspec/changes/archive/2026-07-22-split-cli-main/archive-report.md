# Archive Report: split-cli-main

Archive completed 2026-07-22. Behavior-preserving refactor of the `odoo_forge_cli`
CLI package — no externally-observable capability change.

## Status
- Result: PASS
- Change: `split-cli-main`
- Verify: PASS — 0 CRITICAL, 0 WARNING, 1 SUGGESTION (Engram verify-report id 3270)
- Tasks: 49/49 complete across 6 chained PRs

## Outcome
Split the 896-line god-module `src/odoo_forge_cli/main.py` by cohesion into:
- `main.py` — thin (24 lines, 0 `@app.command`): `app` + callback + four `register(app)` calls
- `_composition.py` — DI factories
- `_presentation.py` — output formatters
- `_support.py` — path/lock/manifest helpers
- `commands/{image,backend,maintenance,manifest}.py` — the 16 commands, each family behind `register(app)`

## Delivery (6 work units, stacked-to-main, all green)
| PR | Commit | Scope |
| --- | --- | --- |
| PR1 | 7d05253 | extract `_composition`/`_presentation`/`_support` |
| PR2 | e78380f | `commands/image.py` |
| PR3 | bb4c288 | `commands/maintenance.py` |
| PR4 | 5e2fd6b | `commands/backend.py` (size:exception — verbatim move) |
| PR5a | 21b8347 | `commands/manifest.py` — validate/onboard |
| PR5b | 55ca987 | `commands/manifest.py` — lock/unlock/project + thin `main.py` |

## Verification evidence
- `uv run pytest`: 901 passed, 17 deselected, coverage 97%
- `uv run lint-imports`: 6 kept / 0 broken (`forbidden_modules=["odoo_forge_cli"]` intact)
- `forge --help`: all 16 commands present, flat hyphenated names, byte-identical
- No circular imports; entry point `forge = "odoo_forge_cli.main:app"` preserved

## Delta spec sync
None. The change's `specs/cli-structure/spec.md` is a behavior-preservation
contract for a pure refactor (`Capabilities: None/None`); no `openspec/specs/`
capability spec existed or was created. Nothing to merge — correct outcome.

## Follow-up (non-blocking SUGGESTION)
`commands/manifest.py` landed at ~316 lines, over the soft ~250-line cohesion
target. It holds 5 same-family commands (single responsibility); a further
intra-file split was judged to fragment one command family for no behavioral
benefit. Revisit only if the module grows.

## Source artifacts (Engram)
- proposal: #3265
- spec: #3266
- design: #3267
- tasks: #3268
- verify-report: #3270
