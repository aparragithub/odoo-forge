import ast
from pathlib import Path

import pytest

from odoo_forge.manifest.module_deps import (
    OdooModule,
    build_module_index,
    find_missing_dependencies,
    parse_manifest_source,
)


def _write_manifest(root: Path, module_name: str, content: str) -> Path:
    module_dir = root / module_name
    module_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = module_dir / "__manifest__.py"
    manifest_path.write_text(content, encoding="utf-8")
    return manifest_path


def test_parse_manifest_source_valid_dict_literal() -> None:
    text = "{'depends': ['base', 'mail'], 'installable': True}"

    module = parse_manifest_source(text, Path("addons/my_module/__manifest__.py"))

    assert module == OdooModule(name="my_module", depends=("base", "mail"), installable=True)


def test_parse_manifest_source_defaults_absent_fields() -> None:
    text = "{'name': 'My Module'}"

    module = parse_manifest_source(text, Path("addons/my_module/__manifest__.py"))

    assert module.depends == ()
    assert module.installable is True


def test_parse_manifest_source_malformed_syntax_raises_naming_path() -> None:
    text = "{'depends': ['base'"  # invalid syntax: unclosed brackets
    path = Path("addons/broken_module/__manifest__.py")

    with pytest.raises(Exception) as exc_info:
        parse_manifest_source(text, path)

    assert str(path) in str(exc_info.value)


def test_parse_manifest_source_function_call_raises_naming_path() -> None:
    text = "dict(depends=['base'])"
    path = Path("addons/broken_module/__manifest__.py")

    with pytest.raises(Exception) as exc_info:
        parse_manifest_source(text, path)

    assert str(path) in str(exc_info.value)


def test_parse_manifest_source_non_dict_top_level_raises_naming_path() -> None:
    text = "['depends', 'base']"
    path = Path("addons/broken_module/__manifest__.py")

    with pytest.raises(Exception) as exc_info:
        parse_manifest_source(text, path)

    assert str(path) in str(exc_info.value)


def test_parse_manifest_source_wrong_depends_type_raises_naming_path() -> None:
    text = "{'depends': 'foo'}"
    path = Path("addons/broken_module/__manifest__.py")

    with pytest.raises(Exception) as exc_info:
        parse_manifest_source(text, path)

    assert str(path) in str(exc_info.value)


def test_parse_manifest_source_wrong_installable_type_raises_naming_path() -> None:
    text = "{'installable': 'yes'}"
    path = Path("addons/broken_module/__manifest__.py")

    with pytest.raises(Exception) as exc_info:
        parse_manifest_source(text, path)

    assert str(path) in str(exc_info.value)


def test_parse_manifest_source_recursion_error_converted_to_clean_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A pathological/corrupted manifest can raise `RecursionError` from
    `ast.literal_eval` (deeply nested literals) — this must never propagate as
    a raw traceback, only a hard error naming the offending file."""

    def _raise_recursion(*args: object, **kwargs: object) -> None:
        raise RecursionError("maximum recursion depth exceeded")

    monkeypatch.setattr(ast, "literal_eval", _raise_recursion)
    path = Path("addons/pathological_module/__manifest__.py")

    with pytest.raises(ValueError) as exc_info:
        parse_manifest_source("{'depends': []}", path)

    assert str(path) in str(exc_info.value)


def test_parse_manifest_source_memory_error_converted_to_clean_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Same hardening as the `RecursionError` case, for `MemoryError`."""

    def _raise_memory(*args: object, **kwargs: object) -> None:
        raise MemoryError("out of memory")

    monkeypatch.setattr(ast, "literal_eval", _raise_memory)
    path = Path("addons/pathological_module/__manifest__.py")

    with pytest.raises(ValueError) as exc_info:
        parse_manifest_source("{'depends': []}", path)

    assert str(path) in str(exc_info.value)


def test_build_module_index_wraps_root_iterdir_os_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A permission-denied directory (or a symlink loop, or a TOCTOU race)
    raises `OSError` from `Path.iterdir`; this must become a clean error
    naming the offending path, never a raw traceback."""
    root = tmp_path / "addons"
    root.mkdir()

    def _raise_os_error(self: Path) -> None:
        raise OSError("permission denied")

    monkeypatch.setattr(Path, "iterdir", _raise_os_error)

    with pytest.raises(ValueError) as exc_info:
        build_module_index([root])

    assert str(root) in str(exc_info.value)


def test_build_module_index_wraps_module_entry_is_dir_os_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Same hardening for an `OSError` raised while classifying one specific
    module-candidate entry (e.g. a symlink loop under an otherwise-healthy
    root), not just the root itself."""
    root = tmp_path / "addons"
    module_dir = root / "mod_a"
    module_dir.mkdir(parents=True)

    original_is_dir = Path.is_dir

    def _raise_for_mod_a(self: Path) -> bool:
        if self.name == "mod_a":
            raise OSError("symlink loop")
        return original_is_dir(self)

    monkeypatch.setattr(Path, "is_dir", _raise_for_mod_a)

    with pytest.raises(ValueError) as exc_info:
        build_module_index([root])

    assert "mod_a" in str(exc_info.value)


def test_build_module_index_walks_roots_one_level(tmp_path: Path) -> None:
    root = tmp_path / "addons"
    _write_manifest(root, "mod_a", "{'depends': ['mod_b']}")
    _write_manifest(root, "mod_b", "{'depends': []}")

    index = build_module_index([root])

    assert set(index) == {"mod_a", "mod_b"}
    assert index["mod_a"].depends == ("mod_b",)
    assert index["mod_b"].installable is True


def test_find_missing_dependencies_all_satisfied(tmp_path: Path) -> None:
    root = tmp_path / "addons"
    _write_manifest(root, "mod_a", "{'depends': ['mod_b']}")
    _write_manifest(root, "mod_b", "{'depends': []}")
    index = build_module_index([root])

    missing = find_missing_dependencies(index)

    assert missing == {}


def test_find_missing_dependencies_reports_absent_dependency(tmp_path: Path) -> None:
    root = tmp_path / "addons"
    _write_manifest(root, "mod_x", "{'depends': ['mod_y']}")
    index = build_module_index([root])

    missing = find_missing_dependencies(index)

    assert missing == {"mod_x": frozenset({"mod_y"})}


def test_find_missing_dependencies_uninstallable_module_does_not_satisfy(
    tmp_path: Path,
) -> None:
    root = tmp_path / "addons"
    _write_manifest(root, "mod_x", "{'depends': ['mod_y']}")
    _write_manifest(root, "mod_y", "{'installable': False}")
    index = build_module_index([root])

    missing = find_missing_dependencies(index)

    assert missing == {"mod_x": frozenset({"mod_y"})}


def test_find_missing_dependencies_uninstallable_module_still_discoverable(
    tmp_path: Path,
) -> None:
    root = tmp_path / "addons"
    _write_manifest(root, "mod_y", "{'installable': False}")
    index = build_module_index([root])

    assert "mod_y" in index
    assert index["mod_y"].installable is False


def test_find_missing_dependencies_multiple_modules_all_reported(tmp_path: Path) -> None:
    root = tmp_path / "addons"
    _write_manifest(root, "mod_a", "{'depends': ['missing_1']}")
    _write_manifest(root, "mod_b", "{'depends': ['missing_2', 'missing_3']}")
    index = build_module_index([root])

    missing = find_missing_dependencies(index)

    assert missing == {
        "mod_a": frozenset({"missing_1"}),
        "mod_b": frozenset({"missing_2", "missing_3"}),
    }


def test_find_missing_dependencies_community_chain_reaches_enterprise_only(
    tmp_path: Path,
) -> None:
    root = tmp_path / "addons"
    _write_manifest(root, "l10n_ar_reports", "{'depends': ['account_reports']}")
    index = build_module_index([root])

    missing = find_missing_dependencies(index)

    assert missing == {"l10n_ar_reports": frozenset({"account_reports"})}
