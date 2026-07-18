# Mapa De CLI Y Adapters

## Qué es este documento

Es el mapa del composition root `src/odoo_forge_cli/` y de los adapters concretos que conectan el core con Git, Docker, GHCR, filesystem y otros sistemas externos.

## Por qué importa

Importa porque ahí vive el wiring real del runtime. Si se mueve lógica de negocio a la CLI o se filtran detalles de provider al core, se rompen los límites de la arquitectura.

## Por qué existe

Existe para mostrar qué port implementa cada adapter, qué commands visibles toca y qué sistemas externos puede afectar cada cambio.

## Cómo ayuda al sistema

Ayuda al sistema porque mantiene claro el borde entre planificación pura y ejecución concreta, lo que hace más seguras las extensiones de adapters y más predecibles los flujos CLI.

## Leer Después De...

Leé esto después de [03-src-core-map.md](03-src-core-map.md). Siguiente lectura: [05-tests-and-quality-map.md](05-tests-and-quality-map.md). Si necesitás una vista capability -> package -> command, completá la serie con [07-spec-to-module-crosswalk.md](07-spec-to-module-crosswalk.md).

## Ruta Rápida

1. Empezá acá cuando un cambio toque `src/odoo_forge_cli/` o cualquier package adapter hermano.
2. Verificá qué port del core satisface el adapter.
3. Confirmá qué sistema externo puede tocar ese adapter.

## Composition Root

| Path | Rol | Regla para maintainers |
| --- | --- | --- |
| `src/odoo_forge_cli/main.py` | Entrypoint Typer, definiciones de commands, construcción de adapters, render de errores de cara al usuario | Mantenelo fino: parsear input, construir adapters, llamar al core, renderizar outcomes tipados |

`forge` se registra desde `pyproject.toml` como `odoo_forge_cli.main:app`.

## Flujos CLI De Cara Al Usuario

| Familia de commands | Flujo core | Adapters involucrados |
| --- | --- | --- |
| `validate`, `lock`, `project`, `unlock` | validación de manifest, locking, projection, drift | Git source, workspace, registry-resolver |
| `run`, `status`, `stop`, `logs`, `exec` | backend planning e identidad/status de instancia | workspace scan más Docker backend |
| `image-resolve`, `image-publish`, `image-pull`, `image-exists` | normalización de referencias de imagen y operaciones de registry | GHCR/Docker registry adapter |

## Mapa De Adapters

| Package | Se conecta con | Sistemas externos que toca | Participa en |
| --- | --- | --- | --- |
| `src/odoo_forge_git` | `SourceProvider` | `git ls-remote`, hosting Git remoto | `forge lock` |
| `src/odoo_forge_workspace` | `WorkspaceProvider` | filesystem local, `git clone`, `git checkout`, `git worktree` | `forge validate`, `forge project`, `forge unlock`, `forge run` |
| `src/odoo_forge_docker` | `BackendProvider` | daemon Docker local, archivos locales, `sops` para credenciales | `forge run`, `status`, `stop`, `logs`, `exec` |
| `src/odoo_forge_registry` | `ImageRegistryProvider`, `PublishedArtifactResolver` | refs compatibles con GHCR vía Docker CLI / buildx | commands de imágenes y locking de artifacts publicados |
| `src/odoo_forge_postgres_docker` | `DatabaseProvider` | daemon Docker local, archivos temporales de secretos, restore artifacts | foundation de database-provider y adapter tests |
| `src/odoo_forge_cli` | composition root, no implementación de port | I/O de terminal, archivos manifest/lock | todo workflow visible para usuarios |

## Detalle De Packages

### `src/odoo_forge_cli`

| Tema | Notas |
| --- | --- |
| Qué hace | Lee bytes de manifest y lock, valida/normaliza input CLI, construye adapters y renderiza mensajes tipados de éxito o fallo |
| Cómo se conecta al core | Importa servicios puros y protocolos de ports, y después instancia adapters concretos en helpers `_make_*` |
| Sistemas externos | output de terminal, archivos locales, parseo YAML/JSON |
| Advertencia para maintainers | No muevas reglas de negocio acá solo porque un command las necesita |

### `src/odoo_forge_git`

| Tema | Notas |
| --- | --- |
| Qué hace | Implementa `SourceProvider` con `git ls-remote` |
| Contrato core | `resolve_ref(url, ref) -> commit SHA` |
| Sistemas externos | Ejecutable Git, servidores Git remotos |
| Comportamiento importante | Desactiva prompts interactivos, normaliza locale para mantener estable la clasificación de stderr y redacta `userinfo` en errores públicos |

### `src/odoo_forge_workspace`

| Tema | Notas |
| --- | --- |
| Qué hace | Implementa checkout, scan y promoción de worktrees para workspaces materializados |
| Contrato core | `WorkspaceProvider` |
| Sistemas externos | filesystem, ejecutable Git |
| Comportamiento importante | Reemplazo atómico de checkout, rechazo de checkout sucio, rechazo de linked worktree, solo hechos crudos de scan; el core puro decide el significado de mount roots |

### `src/odoo_forge_docker`

| Tema | Notas |
| --- | --- |
| Qué hace | Implementa `BackendProvider` para el runtime local distribuido |
| Contrato core | consume `BackendPlan`, devuelve `InstanceRef` / `InstanceStatus` / `ExecResult` |
| Sistemas externos | Docker CLI, daemon Docker local, archivos temporales de env/secret, command de decrypt `sops` |
| Comportamiento importante | Valida secret handles antes del launch, redacta output que contiene secretos, hace rollback de recursos creados y preserva named volumes en `stop` |

### `src/odoo_forge_registry`

| Tema | Notas |
| --- | --- |
| Qué hace | Implementa operaciones de image registry inmutable y resolución de published artifacts del manifest |
| Contratos core | `ImageRegistryProvider` y `PublishedArtifactResolver` |
| Sistemas externos | Docker CLI, `docker buildx imagetools inspect`, image refs estilo GHCR |
| Comportamiento importante | Rechaza `userinfo` en refs, clasifica fallos de auth/not-found/unavailable y convierte sources `registry://` del manifest en `ghcr.io/...:<tag>` y luego en digest refs |

### `src/odoo_forge_postgres_docker`

| Tema | Notas |
| --- | --- |
| Qué hace | Implementación aislada de `DatabaseProvider` para PostgreSQL en Docker |
| Contrato core | provision/restore/adopt/reconcile/delete/cleanup usando credenciales opacas y artifact refs |
| Sistemas externos | Docker CLI, temp secret mounts/files, estado local de authority de ownership |
| Comportamiento importante | Hace cumplir labels de provider y reglas de identidad de operación, valida identificadores opacos seguros y borra archivos de secretos durante cleanup |

## Reglas De Wiring Para Maintainers

| Regla | Por qué |
| --- | --- |
| Instanciar adapters concretos solo en el composition root de la CLI | Mantiene la dirección de dependencia en un solo sentido |
| Traducir fallos crudos de `subprocess`/filesystem a errores tipados de dominio o adapter | La salida de la CLI debe seguir siendo predecible y testeable |
| Mantener el parseo específico del provider dentro del package adapter | El core no debe aprender gramáticas de error de Docker/Git/GHCR |
| Preferir extender un port cuando el nuevo comportamiento es dueño del core | Evita API creep impulsado por adapters |
| No cablear `src/odoo_forge_postgres_docker` en flujos CLI no relacionados sin autoridad de spec | Es una foundation importante, no la ruta por defecto del runtime |

## Checklist Seguro De Edición

- Si cambiás un command, identificá el servicio puro del core que debe llamar.
- Si cambiás un adapter, identificá el port exacto que implementa.
- Si agregás una invocación a una tool externa, dejala en el package adapter que es dueño de ese límite.
- Actualizá los tests correspondientes en `tests/cli/` y `tests/adapters/`.
- Continuá con [Mapa De Tests Y Quality](05-tests-and-quality-map.md) antes de asumir cosas sobre CI.
