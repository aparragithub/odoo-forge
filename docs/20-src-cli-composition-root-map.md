# Mapa De `src/odoo_forge_cli/`

## Qué es este documento

Es la ficha de mantenimiento de `src/odoo_forge_cli/`: describe el composition root real del producto, las familias de commands visibles para usuarios y la manera en que la CLI cablea core + adapters sin absorber lógica de negocio.

## Por qué importa

Importa porque esta superficie concentra el wiring de runtime que primero perciben quienes usan `forge`. Si aquí se mezclan responsabilidades o se degrada el manejo de errores, la experiencia de uso se rompe de inmediato aunque el core siga siendo correcto.

## Por qué existe

Existe para que maintainers y futuras personas implementadoras distingan con precisión qué debe vivir en `main.py`, qué debe seguir en el core y qué debe permanecer encapsulado dentro de cada adapter concreto.

## Cómo ayuda al sistema

Ayuda al sistema porque mantiene una sola puerta de entrada para parseo CLI, construcción de dependencias, lectura/escritura de archivos de entrada y render de outcomes tipados. Eso preserva la dirección de dependencias y evita que el dominio aprenda detalles de Typer, Docker, Git o GHCR.

## Leer después de...

Leer después de [03-src-core-map.md](03-src-core-map.md), [04-cli-and-adapters-map.md](04-cli-and-adapters-map.md), [13-src-ports-map.md](13-src-ports-map.md) y [16-tests-cli-map.md](16-tests-cli-map.md).

## Siguiente lectura...

Después de esta ficha, conviene seguir con [17-src-docker-adapter-map.md](17-src-docker-adapter-map.md), [18-src-workspace-adapter-map.md](18-src-workspace-adapter-map.md) y [19-src-registry-adapter-map.md](19-src-registry-adapter-map.md), según la familia de commands afectada.

## Ruta rápida

1. Empezar aquí cuando cambie un command visible, su parseo, su wiring o su salida.
2. Identificar qué servicio puro o port del core consume esa familia de commands.
3. Confirmar que el cambio no esté moviendo semántica del dominio hacia Typer o hacia helpers de composición.

## Qué vive en este package

| Elemento | Rol principal | Qué debe evitar |
| --- | --- | --- |
| `main.py` | entrypoint Typer, helpers de composición, lectura de manifest/lock, render de errores y mensajes | decidir reglas del dominio, reinterpretar estado Docker/Git, duplicar semántica ya modelada en el core |

## Por qué `src/odoo_forge_cli/` es el composition root

`src/odoo_forge_cli/main.py` es el lugar donde el repo decide qué implementación concreta satisface cada port en tiempo de ejecución.

| Port o capability consumida | Implementación concreta cableada hoy | Dónde se usa |
| --- | --- | --- |
| `SourceProvider` | `GitSourceProvider` | `lock` |
| `PublishedArtifactResolver` | `PublishedArtifactRegistryResolver(GhcrImageRegistryProvider())` | `lock` para layers `published` |
| `WorkspaceProvider` | `GitWorkspaceProvider` | `validate`, `project`, `unlock`, `run` |
| `BackendProvider` | `DockerBackendProvider(SopsEnvFileInjector(...))` | `run`, `status`, `stop`, `logs`, `exec` |
| image registry provider concreto | `GhcrImageRegistryProvider` | `image-resolve`, `image-publish`, `image-pull`, `image-exists` |

La regla de mantenimiento es simple: un adapter concreto se instancia aquí o en un helper `_make_*` de este mismo archivo, no dentro del core y no distribuido por múltiples commands.

## Familias de commands y flujos de producto/runtime

| Familia | Commands | Flujo que exponen | Dependencias principales |
| --- | --- | --- | --- |
| manifest y lock | `validate`, `lock` | parseo del manifest, composición, resolución de refs, chequeo de drift y escritura de `project.lock` | schema/core de manifest, provider Git, resolver de artifacts publicados, workspace scan |
| proyección de workspace | `project`, `unlock` | llevar el lock al filesystem y promover repos a worktree editable | projection core + `WorkspaceProvider` |
| runtime local | `run`, `status`, `stop`, `logs`, `exec` | derivar identidad de instancia, planificar backend, lanzar y operar el runtime Docker local | backend core + `WorkspaceProvider` + `BackendProvider` |
| imágenes | `image-resolve`, `image-publish`, `image-pull`, `image-exists` | operar refs de imágenes inmutables y su existencia/publicación | `GhcrImageRegistryProvider` |

## Cómo la CLI se mantiene delgada

| Responsabilidad que sí pertenece aquí | Cómo se hace hoy |
| --- | --- |
| leer bytes de `project.yaml` y `project.lock` | `_read_manifest_data()` y `_load_lock()` |
| traducir errores de I/O o decode a errores tipados | wrappers que convierten fallos crudos en `ManifestInputError`, `LockfileError` o boundaries equivalentes |
| normalizar input específico de CLI | opciones Typer y normalización de refs de imagen |
| construir adapters concretos | helpers `_make_*` |
| renderizar salida humana | `_format_drift()`, `_render_validation_errors()` y `typer.echo(...)` |
| propagar exit codes correctos | `typer.Exit(code=1)` para errores de boundary y `ExecResult.exit_code` en `exec` |

| Responsabilidad que NO pertenece aquí | Dueño real |
| --- | --- |
| composición del manifest | `compose()` |
| locking y resolución de layers | `build_lock()` |
| planificación de proyección y unlock | `plan_projection()`, `plan_unlock()` |
| materialización y mount planning | `materialize_state()`, `build_mount_planning_view()` |
| planificación del runtime | `plan_backend()` |
| ejecución Docker/Git/GHCR | packages adapter concretos |

## Helpers `_make_*` y por qué existen

| Helper | Qué construye | Por qué existe |
| --- | --- | --- |
| `_make_provider()` | `GitSourceProvider` | centraliza la elección del adapter Git para `SourceProvider` |
| `_make_published_artifact_resolver()` | `PublishedArtifactRegistryResolver(GhcrImageRegistryProvider())` | evita que `lock` conozca detalles de GHCR o `registry://` |
| `_make_workspace_provider()` | `GitWorkspaceProvider` | mantiene una sola fuente de verdad para checkout/scan/promote |
| `_make_backend_provider()` | `DockerBackendProvider` con `SopsEnvFileInjector` | encapsula la construcción del runtime local y la inyección de credenciales |
| `_make_image_registry_provider()` | `GhcrImageRegistryProvider` | reutiliza el mismo adapter de registry en la familia de image commands |

Estos helpers existen para preservar tres propiedades.

1. El comando sigue leyendo como flujo de presentación y no como fábrica de objetos larga.
2. El binding concreto queda centralizado y visible para review.
3. Cambiar una implementación futura de port requiere tocar un solo punto de composición.

## Flujos que más rápido exponen regresiones de experiencia de usuario

| Superficie | Qué se rompe enseguida |
| --- | --- |
| parseo de opciones Typer | el command deja de aceptar argumentos válidos o cambia la ayuda pública |
| render de errores tipados | aparecen tracebacks, mensajes ambiguos o códigos de salida incorrectos |
| `_write_lock_atomic()` | `project.lock` puede quedar parcial o corrupto |
| normalización de refs de imagen | los image commands aceptan referencias inválidas o rechazan digests válidos |
| boundary de `run` | el usuario ve un fallo tardío, confuso o una instancia a medio provisionar |
| derivación de identidad en `status`/`stop`/`logs`/`exec` | comandos posteriores operan sobre la instancia equivocada |

## Qué debe preservar un maintainer al agregar o cambiar commands

| Regla | Por qué importa |
| --- | --- |
| mantener el command como capa de presentación | evita que Typer se convierta en una segunda implementación del dominio |
| llamar a servicios puros o ports ya existentes antes de crear helpers nuevos | preserva la arquitectura y reduce duplicación |
| instanciar adapters solo mediante el composition root | hace visible el wiring y mantiene el blast radius controlado |
| sostener la taxonomía de errores tipados | la CLI depende de mensajes claros y testeables |
| mantener separados los exit codes de boundary y los exit codes del proceso ejecutado dentro del contenedor | `exec` necesita distinguir fallo del command vs fallo del proceso invocado |
| si un command nuevo toca Docker, Git, GHCR o credenciales, empujar esa lógica al adapter correspondiente | evita contaminar `main.py` con detalle operacional |

## Qué suele romper la UX inmediatamente

1. Mostrar tracebacks en lugar de `error: ...`.
2. Cambiar un path por defecto como `project.yaml`, `project.lock` o `credentials.sops.yaml` sin ajustar toda la cadena.
3. Devolver éxito antes de completar la validación real del lock, del workspace o del backend.
4. Escribir archivos sin atomicidad.
5. Hacer que un command use un adapter distinto al esperado sin reflejarlo en tests CLI.

## Riesgos específicos al extender esta CLI

| Cambio mal hecho | Consecuencia real |
| --- | --- |
| agregar lógica de negocio al command por conveniencia | el core pierde autoridad y los tests empiezan a cubrir comportamiento duplicado |
| construir adapters directamente en varios commands | el wiring deja de ser consistente y se vuelve más difícil de cambiar |
| capturar excepciones demasiado genéricas | la CLI puede ocultar errores incorrectos o perder clasificación útil |
| reutilizar helpers para cosas que ya no son el mismo port | el nombre `_make_*` deja de reflejar una dependencia concreta y el composition root se vuelve opaco |
| imprimir estado humano antes de terminar el trabajo real | la herramienta comunica éxito prematuro |

## Checklist para maintainers

- Verificar cualquier cambio contra [16-tests-cli-map.md](16-tests-cli-map.md) y las suites bajo `tests/cli/`.
- Si el command cambia locking o manifest, releer [11-src-manifest-map.md](11-src-manifest-map.md).
- Si cambia runtime local, seguir con [17-src-docker-adapter-map.md](17-src-docker-adapter-map.md) y [18-src-workspace-adapter-map.md](18-src-workspace-adapter-map.md).
- Si cambia published artifacts o image refs, revisar [19-src-registry-adapter-map.md](19-src-registry-adapter-map.md).
- Mantener `src/odoo_forge_cli/` como composition root y no como segundo core.
