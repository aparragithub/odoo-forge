# Module Dependency Validation Specification

## Purpose

Real, derived validation that every installed module's declared dependencies
resolve to an installable module in the composed, materialized addons_path —
replacing the manually-declared `requires_enterprise` guess with a fact
derived from actual `depends:` graphs, for every layer type whose content is
actually materialized on disk (`GitLayer`). `PublishedLayer` content is never
git-checked-out, so it stays outside this capability's reach entirely — its
edition coherence is covered by a separate, restored manual flag (see
`openspec/specs/manifest/spec.md`'s Migration note).

## Requirements

### Requirement: Dependencies must resolve among installable modules

For every module found under the materialized addons_path (traversal order
via `ordered_addons_roots(manifest, base)`), each entry in that module's
`depends:` list MUST resolve to a module present in the same addons_path with
`installable: True`. Traversal precedence follows `ordered_addons_roots`;
first-match-wins across mount roots is intentional and out of scope for this
requirement (see Non-Goals).

#### Scenario: All dependencies resolve
- GIVEN a materialized addons_path where every module's `depends:` entries
  match an installable module
- WHEN the validator runs
- THEN it reports no missing dependencies

#### Scenario: A missing dependency fails loud
- GIVEN a module `x` whose manifest declares `depends: ["y"]` and no module
  named `y` exists anywhere in the addons_path
- WHEN the validator runs
- THEN it reports `y` as a missing dependency of `x`

#### Scenario: Community chain reaching an Enterprise-only module fails
- GIVEN a community-edition manifest whose installed modules' dependency
  chain reaches an Enterprise-only module (e.g. `account_reports`), and that
  module is absent because no `enterprise:` block is configured
- WHEN the validator runs
- THEN it reports the Enterprise-only module as a missing dependency,
  functionally replacing the removed `requires_enterprise` coherence check

### Requirement: Multi-root module discovery follows first-match-wins precedence

`build_module_index` MUST process `roots` in the given order and, when the
same module name is discovered under more than one root, MUST keep the
`OdooModule` found in the earliest root and MUST NOT overwrite it with a
later root's manifest. A root that does not exist, or exists but is not a
directory, MUST be skipped silently (treated as contributing zero modules),
MUST NOT raise, and MUST NOT prevent later roots from being scanned.

#### Scenario: Earlier root wins on a name collision
- GIVEN two roots, each containing a module directory of the same name with
  different `depends:` content
- WHEN `build_module_index([root_a, root_b])` runs with `root_a` first
- THEN the resulting index entry for that name matches `root_a`'s manifest,
  not `root_b`'s

#### Scenario: A non-existent or non-directory root is skipped, not an error
- GIVEN a `roots` list containing one valid addons root and one path that
  does not exist on disk
- WHEN `build_module_index` runs
- THEN it completes without raising and the index contains only the modules
  discovered under the valid root

### Requirement: Manifests are parsed via ast.literal_eval only

Every `__manifest__.py` file under the addons_path MUST be parsed using
`ast.literal_eval` against its top-level dict literal. `exec`/`eval` MUST
NEVER be used. A manifest file that is not a syntactically valid Python
literal, or whose top-level value is not a `dict`, MUST be a hard parse
error identifying the failing file path — it MUST NOT be silently skipped
or treated as absent.

#### Scenario: Malformed manifest is a hard error
- GIVEN a `__manifest__.py` file containing invalid Python syntax
- WHEN the validator parses the addons_path
- THEN it raises an error naming that exact file path
- AND validation does not continue as if the module were simply missing

#### Scenario: Non-dict top-level literal is a hard error
- GIVEN a `__manifest__.py` whose top-level literal is a list, not a dict
- WHEN the validator parses it
- THEN it raises an error naming that exact file path

#### Scenario: Pathological manifest never crashes with a raw traceback
- GIVEN a `__manifest__.py` file so deeply nested/corrupted that
  `ast.literal_eval` raises `RecursionError` or `MemoryError`
- WHEN the validator parses it
- THEN it raises the same clean, file-naming error as a syntax error — never
  an unhandled `RecursionError`/`MemoryError` traceback

### Requirement: Filesystem I/O while walking the addons_path is guarded

Every filesystem call `build_module_index` makes while walking the
addons_path (`is_dir`, `iterdir`, `is_file`, `read_text`) MUST be guarded
against `OSError`. A permission-denied directory, a symlink loop, or a TOCTOU
race (a module directory disappearing mid-scan) MUST be converted into the
same clean, path-naming hard error used for a malformed manifest — never an
unhandled traceback.
(Previously: only the directory-listing (`iterdir`) guard had an asserting
test; the `is_dir` root guard, the manifest `is_file` guard, and the
`read_text` guard were implemented but unverified.)

#### Scenario: Permission-denied directory fails clean, naming the path
- GIVEN a directory under the addons_path that raises `OSError` when listed
  (e.g. permission denied)
- WHEN the validator walks the addons_path
- THEN it raises a clean error naming that directory, not a raw traceback

#### Scenario: A root that raises OSError on is_dir() fails clean, naming the root
- GIVEN an addons root whose `is_dir()` check raises `OSError` (e.g. a
  symlink loop at the root itself)
- WHEN `build_module_index` runs
- THEN it raises a clean error naming that root, not a raw traceback

#### Scenario: A manifest path that raises OSError on is_file() fails clean, naming the path
- GIVEN a module's `__manifest__.py` path whose `is_file()` check raises
  `OSError` mid-scan
- WHEN `build_module_index` runs
- THEN it raises a clean error naming that manifest path, not a raw traceback

#### Scenario: A manifest that raises OSError on read_text() fails clean, naming the path
- GIVEN a module's `__manifest__.py` file that raises `OSError` when read
  (e.g. removed mid-scan)
- WHEN `build_module_index` runs
- THEN it raises a clean error naming that manifest path, not a raw traceback

### Requirement: Non-installable modules never satisfy dependencies

A module with `installable: False` (explicit or inferred default per Odoo
manifest semantics) MUST NOT be treated as satisfying any other module's
dependency on it. Such modules remain present in the addons_path index (they
are not excluded from being *discovered*) — they are excluded only from the
set of modules that can *satisfy* a `depends:` entry, and their own
`depends:` list MUST NOT be evaluated for missing-dependency reporting.
(Previously: only the "does not satisfy others" direction had an asserting
test; that an uninstallable module's own `depends` is skipped as a
validation subject was implemented but unverified.)

#### Scenario: Uninstallable module does not satisfy a dependency
- GIVEN module `x` declares `depends: ["y"]`, and module `y` exists with
  `installable: False`
- WHEN the validator runs
- THEN `y` is reported as a missing/unsatisfied dependency of `x`

#### Scenario: An uninstallable module's own depends is never evaluated
- GIVEN module `z` has `installable: False` and declares
  `depends: ["nonexistent"]`
- WHEN the validator runs
- THEN `z` is never reported as having a missing dependency, even though its
  own declared `depends:` would otherwise be unsatisfied

### Requirement: Validation is attached to every command that materializes a workspace

The dependency validator MUST run as a step within `forge validate` (executed
only when `lock is not None`, mirroring the existing drift-check gate) AND
within `forge onboard` (executed right after `project_workspace` completes
and the post-projection drift check confirms a clean, fully materialized
tree). Both call sites share one implementation
(`_check_module_dependencies` in `odoo_forge_cli.main`) so the check and its
error-shaping logic are never duplicated. This closes the gap where a user
running `forge lock && forge onboard && forge run` — without ever calling
`forge validate` — would otherwise get zero dependency/Enterprise-reachability
checking.

`forge lock` deliberately does NOT run this check: it only resolves refs and
writes `project.lock` — it never checks out a workspace itself, so there is
no addons_path to inspect at that point (running the check there would only
see stale evidence from a previous `onboard`, if any, not the newly-locked
manifest's actual state).

When no lock is present for `forge validate` (unprojected workspace), the
validator step MUST be skipped entirely — it MUST NOT report false
missing-dependency errors against an empty/unprojected tree. For
`forge validate`, when the workspace is only PARTIALLY materialized (some
locked layer/repo reports `not_materialized` drift), the validator step MUST
NOT run at all — it MUST instead fail with a distinct, clear
"workspace not fully materialized" error, never a false "module missing"
report derived from an incomplete addons_path.

#### Scenario: No lock skips the validator (forge validate)
- GIVEN a `project.yaml` with no corresponding `project.lock`
- WHEN `forge validate` runs
- THEN the module-dependency validation step does not execute and reports
  nothing

#### Scenario: Lock present triggers the validator (forge validate)
- GIVEN a valid `project.lock` and a materialized addons_path
- WHEN `forge validate` runs
- THEN the module-dependency validation step executes against that addons_path

#### Scenario: Partially materialized workspace fails distinctly, not falsely
- GIVEN a valid `project.lock` declaring a layer/repo that is not yet
  materialized on disk
- WHEN `forge validate` runs
- THEN it fails with a clear "workspace not fully materialized" error
- AND it does NOT run the module-dependency validator against the
  incomplete addons_path, and does NOT report a false missing-dependency error

#### Scenario: forge onboard runs the same validator after materialization
- GIVEN a valid `project.lock` and a `WorkspaceProvider` that successfully
  checks out every declared repo
- WHEN `forge onboard` runs and the workspace materializes cleanly
- THEN the module-dependency validation step executes against the newly
  materialized addons_path, exiting non-zero on any missing dependency

#### Scenario: forge lock never runs the validator
- GIVEN a valid manifest with resolvable refs
- WHEN `forge lock` runs
- THEN it writes `project.lock` without ever invoking module-dependency
  validation, since no workspace has been materialized by `forge lock` itself

### Requirement: Failure is a hard error reporting all missing dependencies at once

When one or more missing dependencies are found, `forge validate` MUST exit
non-zero (`typer.Exit(code=1)`) and MUST report every missing dependency
found, not only the first encountered.

#### Scenario: Multiple missing dependencies are all reported
- GIVEN three modules each missing a distinct dependency
- WHEN `forge validate` runs
- THEN the command exits non-zero and the error output names all three
  missing dependencies, not just one

## Non-Goals

- Module-name collision/shadowing detection across mount roots — first-match-wins
  is intentional Odoo override behavior, not a defect, and is explicitly out
  of scope.
- `external_dependencies` (python/bin) validation — a different problem domain
  (system environment completeness), out of scope.
- Circular-dependency detection — Odoo's own loader already fails on cycles;
  no gap to close here, out of scope.

## Testing Note

Unit tests for this capability MUST use fixture `__manifest__.py` files under
fake/temp addons roots constructed in-test — never real Odoo source trees —
so tests stay fast, deterministic, and independent of any real Odoo checkout.
