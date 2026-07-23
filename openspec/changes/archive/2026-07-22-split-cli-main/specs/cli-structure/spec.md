# Delta for CLI Structure

No delta specs — behavior-preserving refactor. `split-cli-main` is a pure
internal reorganization of `src/odoo_forge_cli/main.py` into cohesive modules
(`_composition.py`, `_presentation.py`, `_support.py`,
`commands/{image,backend,manifest,maintenance}.py`). No new, modified, or
removed externally-observable capability is introduced (per proposal
`Capabilities: None / None`).

The testable contract for this change is BEHAVIOR PRESERVATION, expressed
below as ADDED requirements (invariants that must hold both before and after
the split).

## ADDED Requirements

### Requirement: CLI Surface Is Byte-Identical

The system MUST expose the exact same Typer command names, options, arguments,
and output for every `forge` CLI command after the split as before it. The
system MUST NOT introduce, rename, remove, or regroup any command (flat
hyphenated names such as `forge image-resolve` MUST remain flat, not become
Typer sub-groups).

#### Scenario: Existing CLI test suite passes unmodified in assertions

- GIVEN the pre-split `CliRunner`-based test suite
- WHEN the suite is run against the post-split package
- THEN every test's command invocation, exit code, and stdout/stderr assertions pass without modification to the assertions themselves

#### Scenario: Help output is unchanged

- GIVEN `forge --help` and `forge <command> --help` for every command
- WHEN invoked before and after the split
- THEN the rendered help text is identical

### Requirement: Entry Point Is Preserved

The system MUST keep the packaging entry point `forge = "odoo_forge_cli.main:app"` resolvable after the split; `main.py` MUST still define the module-level `app` Typer instance that all command modules register against.

#### Scenario: Entry point resolves post-split

- GIVEN the installed package after the split
- WHEN `forge` is invoked from a shell
- THEN it resolves via `odoo_forge_cli.main:app` and executes without import errors

### Requirement: Import-Linter Contract Stays Satisfied

The system MUST NOT introduce a circular import between `main.py` and any `commands/*.py` module; command modules MUST NOT import from `main`. The existing `forbidden_modules = ["odoo_forge_cli"]` import-linter contract MUST continue to pass unmodified.

#### Scenario: No circular imports after registration split

- GIVEN `main.py` importing each `commands/*.py` module and calling `register(app)`
- WHEN the package is imported
- THEN no `ImportError` due to circularity occurs and `uv run lint-imports` passes

#### Scenario: Command modules stay decoupled from main

- GIVEN any module under `commands/`
- WHEN its imports are inspected
- THEN it does not import `odoo_forge_cli.main`

### Requirement: Monkeypatch and Import Targets Are Repointed, Not Facaded

The system MUST relocate every test `patch("odoo_forge_cli.main.<symbol>")` (or equivalent import) to the symbol's new home module. The system MUST NOT add a re-export facade in `main.py` for moved symbols, since a facade would let a stale patch target silently no-op instead of failing.

#### Scenario: Repointed patch target still intercepts the call

- GIVEN a test that previously patched a symbol on `odoo_forge_cli.main`
- WHEN the symbol moves to `_composition.py`, `_presentation.py`, `_support.py`, or a `commands/*.py` module
- THEN the test patches the new module path and the patched behavior is observed during the test run

#### Scenario: No facade re-export exists for moved symbols

- GIVEN the post-split `main.py`
- WHEN its contents are inspected
- THEN it contains no re-export of a moved helper/factory symbol for backward-compatible patching
