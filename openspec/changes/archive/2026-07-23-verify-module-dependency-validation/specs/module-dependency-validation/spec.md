# Delta for module-dependency-validation

Verification-only delta: locks in behaviors already implemented in
`build_module_index`/`find_missing_dependencies` but not yet asserted by a
test. No requirement text changes meaning; only conformance scenarios are
added/completed.

## ADDED Requirements

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

## MODIFIED Requirements

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
