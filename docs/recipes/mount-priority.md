# Resolve duplicate modules with mount priority

When two addon roots contain the same Odoo module, Odoo loads the first
matching module directory in its composite `addons_path`. Use
`mount_priority` when the root containing the intended module must win.

## 1. See the default winner

Without `mount_priority`, the effective root order is:

| Order | Root | Example outcome |
| --- | --- | --- |
| 1 | `worktrees` | A matching module here wins first |
| 2 | `community` | A matching module here wins if it is not in `worktrees` |
| 3 | `enterprise` | A matching module here wins if earlier roots do not contain it |
| 4 | `custom/<category>` roots | Declared custom roots, sorted by key |
| 5 | `/opt/odoo/addons` | The image's built-in addons are checked last |

For example, if `sale_custom` exists in both `community` and
`custom/overrides`, the `community` copy wins with the default order. Empty or
missing roots are skipped, so they do not change the relative order of the
remaining roots. Module directories are sorted within each root.

## 2. Move the intended root first

Declare the custom layer and put its root ahead of `worktrees`:

```yaml
name: mount-priority-example
odoo_version: "19.0"
edition: community
layers:
  - type: git
    name: overrides
    category: overrides
    repos:
      - url: https://github.com/example/overrides.git
        ref: "main"
client:
  type: client
  addons_path: client/addons
mount_priority:
  - custom/overrides
  - worktrees
```

The resulting effective order is:

| Order | Root |
| --- | --- |
| 1 | `custom/overrides` |
| 2 | `worktrees` |
| 3 | `community` |
| 4 | `enterprise` |
| 5 | `/opt/odoo/addons` |

The `custom/overrides` copy of a duplicate module now wins. Listed roots move
to the front in the exact order declared; every unlisted root keeps its
default relative order.

## 3. Use valid root keys

- System roots are `worktrees`, `community`, and `enterprise`.
- A custom root is `custom/<category>` for a category declared in `layers`.
- An uncategorized layer, or a layer with `category: custom`, uses
  `custom/default`.
- Priority entries must be unique and declared for this manifest. Unknown or
  duplicate entries are invalid.
- Missing or empty roots are ignored during path construction. The built-in
  `/opt/odoo/addons` path is always appended last and is not a priority key.

`mount_priority` changes runtime lookup precedence only. It does not change
the layer composition order, lock resolution, or which repositories are
projected.

## 4. Validate and run

Validate the manifest, then project and run it as usual:

```bash
uv run forge validate --manifest project.yaml
uv run forge project  --manifest project.yaml
uv run forge run      --manifest project.yaml
```

If the intended module still does not win, confirm that its root is declared,
non-empty, and listed with the exact `custom/<category>` key.
