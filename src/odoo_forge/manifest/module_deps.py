"""Pure module-dependency validation over a discovered addons_path.

`parse_manifest_source` and `find_missing_dependencies` are pure and never
touch the filesystem. `build_module_index` is the thin I/O adapter: it walks
each root one level deep, reads every `<module>/__manifest__.py` it finds, and
delegates parsing to `parse_manifest_source`. Manifests are parsed via
`ast.literal_eval` only — `exec`/`eval` are never used, and a manifest that
isn't a valid dict literal (or has wrongly-typed `depends`/`installable`) is
a hard parse error naming the offending file path, never silently skipped.
A pathological manifest that makes `ast.literal_eval` raise `RecursionError`/
`MemoryError` is treated the same way. Any `OSError` encountered while
walking the addons tree (permission denied, symlink loop, a directory
disappearing mid-scan) is likewise converted to the same clean `ValueError`,
naming the offending path — never a raw traceback.
"""

import ast
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class OdooModule:
    """One discovered module: its declared dependencies and installability.

    `installable` defaults to `True` and `depends` defaults to `()` when
    absent from the manifest dict, matching real Odoo manifest semantics.
    """

    name: str
    depends: tuple[str, ...]
    installable: bool


ModuleIndex = dict[str, OdooModule]


def parse_manifest_source(text: str, path: Path) -> OdooModule:
    """Parse one `__manifest__.py` file's source text into an `OdooModule`.

    Pure: takes the already-read source text and the module's manifest path
    only (the path is used solely to derive the module name and to name the
    file in any parse error, never to perform I/O here). Uses
    `ast.literal_eval` only — never `exec`/`eval`. Raises `ValueError` naming
    `path` when the source is not valid Python, its top-level literal is not
    a `dict`, or `depends`/`installable` have the wrong type.
    """
    try:
        manifest_dict = ast.literal_eval(text)
    except (SyntaxError, ValueError, RecursionError, MemoryError) as exc:
        raise ValueError(f"malformed manifest at {path}: {exc}") from exc

    if not isinstance(manifest_dict, dict):
        raise ValueError(
            f"manifest at {path} must be a dict literal, got {type(manifest_dict).__name__}"
        )

    depends = manifest_dict.get("depends", [])
    if not isinstance(depends, list) or not all(isinstance(item, str) for item in depends):
        raise ValueError(f"manifest at {path} has invalid 'depends': must be a list of str")

    installable = manifest_dict.get("installable", True)
    if not isinstance(installable, bool):
        raise ValueError(f"manifest at {path} has invalid 'installable': must be a bool")

    return OdooModule(name=path.parent.name, depends=tuple(depends), installable=installable)


def build_module_index(roots: Sequence[Path]) -> ModuleIndex:
    """Walk each root one level deep and index every discovered module by name.

    I/O adapter: for each root, iterates its immediate subdirectories looking
    for `<module>/__manifest__.py`, reads the file, and delegates parsing to
    `parse_manifest_source`. Roots are processed in the given order; a module
    name found in an earlier root wins over the same name found in a later
    root (mirrors Odoo's first-match-wins `addons_path` precedence).

    Every filesystem call (`is_dir`, `iterdir`, `is_file`, `read_text`) is
    guarded against `OSError`: a permission-denied directory, a symlink loop,
    or a TOCTOU race (a module directory disappearing mid-scan) raises a
    clean `ValueError` naming the offending path instead of an unhandled
    traceback.
    """
    index: ModuleIndex = {}
    for root in roots:
        try:
            if not root.is_dir():
                continue
        except OSError as exc:
            raise ValueError(f"cannot inspect addons root {root}: {exc}") from exc

        try:
            entries = sorted(root.iterdir())
        except OSError as exc:
            raise ValueError(f"cannot list addons root {root}: {exc}") from exc

        for entry in entries:
            try:
                if not entry.is_dir():
                    continue
            except OSError as exc:
                raise ValueError(f"cannot inspect module directory {entry}: {exc}") from exc

            manifest_path = entry / "__manifest__.py"
            try:
                if not manifest_path.is_file():
                    continue
            except OSError as exc:
                raise ValueError(f"cannot inspect manifest file {manifest_path}: {exc}") from exc

            if entry.name in index:
                continue

            try:
                text = manifest_path.read_text(encoding="utf-8")
            except OSError as exc:
                raise ValueError(f"cannot read manifest file {manifest_path}: {exc}") from exc

            index[entry.name] = parse_manifest_source(text, manifest_path)
    return index


def find_missing_dependencies(index: ModuleIndex) -> dict[str, frozenset[str]]:
    """Compute every missing dependency across all modules in `index`. Pure.

    A dependency is satisfied only if some module with that name exists in
    `index` AND has `installable: True`; a name that only exists with
    `installable: False` counts as missing. Only modules with
    `installable: True` are checked as validation subjects — a
    non-installable module's own `depends` is never evaluated, though it
    remains present in `index` and can still be reported as someone else's
    missing dependency. Returns a mapping of module name to the frozenset of
    its missing dependency names, covering every module in the index (not
    stopping at the first missing dependency found).
    """
    installable_names = {name for name, module in index.items() if module.installable}
    missing: dict[str, frozenset[str]] = {}
    for name, module in index.items():
        if not module.installable:
            continue
        unsatisfied = frozenset(dep for dep in module.depends if dep not in installable_names)
        if unsatisfied:
            missing[name] = unsatisfied
    return missing


__all__ = [
    "OdooModule",
    "ModuleIndex",
    "parse_manifest_source",
    "build_module_index",
    "find_missing_dependencies",
]
