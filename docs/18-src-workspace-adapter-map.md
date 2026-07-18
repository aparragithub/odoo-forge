# Mapa De `src/odoo_forge_workspace/`

## Qué es este documento

Es la ficha de mantenimiento de `src/odoo_forge_workspace/`: describe el adapter Git/filesystem que implementa `WorkspaceProvider` para checkout, scan y promoción a worktree.

## Por qué importa

Importa porque este package controla la evidencia sobre la que el sistema decide qué repos existen realmente en disco. Si esa evidencia se vuelve incorrecta o ambigua, `validate`, `project`, `unlock` y `run` empiezan a operar sobre una realidad falsa.

## Por qué existe

Existe para que maintainers y futuras personas implementadoras entiendan que este adapter no decide semántica de layers, mount roots ni drift. Su trabajo es ejecutar Git y filesystem con reglas estrictas, y devolver hechos crudos o efectuar promociones ya decididas por el core.

## Cómo ayuda al sistema

Ayuda al sistema porque preserva un boundary limpio entre proyección pura y materialización real: el core calcula rutas, commits y branches; el adapter hace clone, checkout, scan y `git worktree add` sin reinterpretar esas decisiones.

## Leer después de...

Leer después de [11-src-manifest-map.md](11-src-manifest-map.md), [13-src-ports-map.md](13-src-ports-map.md) y [16-tests-cli-map.md](16-tests-cli-map.md).

## Siguiente lectura...

Seguir con [19-src-registry-adapter-map.md](19-src-registry-adapter-map.md) para la otra frontera externa usada por `forge lock` e image commands. Para los tests concretos de este adapter, complementar con [15-tests-adapters-map.md](15-tests-adapters-map.md).

## Ruta rápida

1. Empezar aquí cuando cambie `forge project`, `forge unlock`, `forge validate` o la evidencia que `forge run` usa para montar repos.
2. Separar si el cambio toca `checkout`, `scan` o `promote`.
3. Confirmar que la semántica de roots, worktrees y drift siga viviendo en `src/odoo_forge/manifest/projection.py`.

## Qué vive en este package

| Archivo | Responsabilidad principal | Qué no debe hacer |
| --- | --- | --- |
| `provider.py` | implementar `checkout`, `scan` y `promote` vía Git y filesystem | atribuir layers, reinterpretar mounts o calcular branch names por cuenta propia |

## Responsabilidades principales

| Operación | Qué hace | Consumida desde |
| --- | --- | --- |
| `checkout(url, commit, dest)` | clona y deja `dest` en el commit exacto, con reemplazo atómico | `project_workspace()` durante `forge project` |
| `scan(roots)` | recorre roots y devuelve `ScannedRepo(path, url, commit)` sin atribución | `forge validate` y `forge run` antes de `materialize_state()` |
| `promote(source, dest, branch)` | crea una copia writable vía `git worktree add -b` | `forge unlock` |

## Relación con checkout, scan, promote y materialización

| Concern | Dueño real |
| --- | --- |
| elegir qué repos deberían existir | `plan_projection()` en el core |
| ejecutar el checkout físico | `GitWorkspaceProvider.checkout()` |
| traducir evidencia escaneada a estado materializado | `materialize_state()` en el core |
| elegir source, dest y branch de unlock | `plan_unlock()` en el core |
| ejecutar la promoción a worktree | `GitWorkspaceProvider.promote()` |

Esa división es FUNDAMENTAL. Si el adapter empieza a "entender" demasiado de layers o mounts, el core pierde autoridad y la arquitectura se diluye.

## Cómo soporta workflows de lock, project, validate y run

| Workflow | Papel de `src/odoo_forge_workspace/` |
| --- | --- |
| `forge lock` | no participa directamente en la resolución de refs, pero define la frontera que luego hará materializable el lock |
| `forge project` | ejecuta cada `checkout` del `WorkspacePlan` ya calculado por el core |
| `forge validate` | aporta el `scan()` real del disco para que `materialize_state()` y `detect_drift()` comparen lock contra evidencia |
| `forge unlock` | convierte una proyección read-only en worktree writable sin tocar el cálculo del destino |
| `forge run` | aporta el `scan()` que permite seleccionar la evidencia montable y distinguir worktree vs read-only |

## Relación con mount planning y projection

`src/odoo_forge_workspace/` es el productor de evidencia cruda que `src/odoo_forge/manifest/projection.py` necesita.

| Función del core | Qué recibe de este adapter | Qué decide el core con eso |
| --- | --- | --- |
| `project_workspace()` | un provider con `checkout()` | ejecuta los pasos del plan en orden |
| `materialize_state()` | `ScannedRepo` crudos | reconstituye `MaterializedState` según roots y layout `/mnt/<root>/<layer>/...` |
| `build_mount_planning_view()` | `ScannedRepo` crudos | valida evidencia, detecta worktrees y elige el bind autoritativo |

Esto explica por qué `scan()` debe ser deliberadamente "tonto": si devolviera interpretación en lugar de hechos, contaminaría la autoridad del core.

## Invariantes que debe preservar

| Invariante | Por qué importa |
| --- | --- |
| `checkout` es idempotente cuando `dest` ya está en el commit pedido | evita trabajo y mutación innecesaria |
| un checkout sucio no se sobrescribe | protege trabajo local no promovido |
| un linked worktree no se toca como si fuera checkout normal | evita destruir una copia writable gestionada aparte |
| el reemplazo de `dest` es atómico y reversible | evita dejar repos a medio clonar |
| `scan()` devuelve solo hechos `path/url/commit` | mantiene la semántica de materialización fuera del adapter |
| `promote()` no modifica `source` | preserva la proyección bloqueada como referencia recuperable |
| errores de Git no filtran URLs con credenciales | mantiene segura la superficie de error pública |

## Riesgos si se modifica mal

| Cambio mal hecho | Consecuencia real |
| --- | --- |
| perder atomicidad en `checkout` | el workspace puede quedar ausente o corrupto tras un fallo intermedio |
| permitir overwrite de checkout sucio | se puede destruir trabajo local silenciosamente |
| reinterpretar roots dentro de `scan()` | `materialize_state()` y `build_mount_planning_view()` dejan de ser la autoridad |
| tocar worktrees como si fueran clones normales | `unlock` y mount planning pueden corromper evidencia writable |
| exponer stderr crudo de Git | la CLI puede filtrar remotes con credenciales |

## Qué se rompe si esta área se entiende mal

1. `forge project` puede proyectar repos equivocados o dejar el disco en estado parcial.
2. `forge validate` puede detectar drift falso o ignorar drift real.
3. `forge run` puede montar evidencia incoherente dentro del contenedor.
4. `forge unlock` puede perder la separación entre copia bloqueada y copia editable.

## Checklist para maintainers

- Mantener este adapter enfocado en hechos de Git/filesystem, no en reglas del dominio.
- Si cambiás `scan()`, revisar de inmediato `materialize_state()` y `build_mount_planning_view()`.
- Si cambiás `checkout()` o `promote()`, validar también `tests/adapters/test_workspace_provider.py` y `tests/cli/test_project.py`/`test_unlock.py`.
- No introducir mensajes de error que repitan remotes o argv sensibles.
- Cuando el cambio toque workflows con imágenes publicadas, seguir con [19-src-registry-adapter-map.md](19-src-registry-adapter-map.md).
