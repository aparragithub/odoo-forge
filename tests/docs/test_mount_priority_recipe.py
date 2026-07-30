import re
from pathlib import Path

import yaml

from odoo_forge.manifest.projection import ordered_addons_roots
from odoo_forge.manifest.schema import Manifest

ROOT = Path(__file__).parents[2]
RECIPE = ROOT / "docs/recipes/mount-priority.md"
INDEX = ROOT / "docs/recipes/README.md"


def _recipe_text() -> str:
    return RECIPE.read_text(encoding="utf-8")


def _root_column(section: str) -> list[str]:
    return re.findall(r"^\| \d+ \| `([^`]+)`", section, re.MULTILINE)


def test_published_manifest_is_exactly_one_schema_valid_example() -> None:
    blocks = re.findall(r"^```yaml\n(.*?)\n```$", _recipe_text(), re.MULTILINE | re.DOTALL)

    assert len(blocks) == 1
    manifest = Manifest.model_validate(yaml.safe_load(blocks[0]))
    assert manifest.mount_priority == ["custom/overrides", "worktrees"]


def test_documented_orders_match_the_manifest_projection() -> None:
    recipe = _recipe_text()
    default_section, priority_section = recipe.split("## 2. Move the intended root first", 1)
    priority_section = priority_section.split("## 3. Use valid root keys", 1)[0]
    manifest_block = re.search(r"^```yaml\n(.*?)\n```$", priority_section, re.MULTILINE | re.DOTALL)

    assert _root_column(default_section) == [
        "worktrees",
        "community",
        "enterprise",
        "custom/<category>",
        "/opt/odoo/addons",
    ]
    assert manifest_block is not None
    manifest = Manifest.model_validate(yaml.safe_load(manifest_block.group(1)))
    projected = [path.relative_to("/mnt").as_posix() for path in ordered_addons_roots(manifest)]
    assert _root_column(priority_section) == [*projected, "/opt/odoo/addons"]


def test_recipe_states_collision_and_root_constraints() -> None:
    recipe = _recipe_text()
    prose = " ".join(recipe.split())

    assert "Odoo loads the first matching module directory" in prose
    assert "Empty or missing roots are skipped" in prose
    assert "Module directories are sorted within each root" in prose
    assert "`custom/default`" in recipe
    assert "Unknown or duplicate entries are invalid" in prose
    assert "every unlisted root keeps its default relative order" in prose


def test_recipe_index_link_is_adjacent_and_resolves() -> None:
    index = INDEX.read_text(encoding="utf-8")
    addon_link = "[Add an addon layer](add-an-addon-layer.md)"
    priority_link = "[Resolve duplicate modules with mount priority](mount-priority.md)"

    assert index.index(priority_link) > index.index(addon_link)
    assert index[index.index(addon_link) : index.index(priority_link)].count("\n") == 1
    assert (INDEX.parent / "mount-priority.md").is_file()
