# Mapa De `tests/cli/`

## Qué es este documento

Es la ficha de mantenimiento de `tests/cli/`: explica qué protege la suite que verifica el wiring de `forge`, los mensajes visibles para usuarios y los límites de error del entrypoint CLI.

## Por qué importa

Importa porque esta suite cubre la superficie que se rompe primero cuando cambia un command: argumentos, composition root, salida renderizada y códigos de salida. Si falla acá, la regresión ya es visible para quien ejecuta `forge`, aunque el core siga correcto.

## Por qué existe

Existe para que maintainers y futuras personas implementadoras distingan entre comportamiento puro, comportamiento adapter y comportamiento de presentación. Ayuda a decidir cuándo un cambio debe quedarse en `tests/manifest/` o `tests/adapters/` y cuándo necesita además una prueba CLI.

## Cómo ayuda al sistema

Ayuda al sistema porque mantiene estable el contrato público de `src/odoo_forge_cli/main.py`: parseo de opciones, construcción de adapters, boundary único de `error: ...`, ausencia de tracebacks crudos y separación correcta entre familias de commands.

## Leer después de...

Leer después de [04-cli-and-adapters-map.md](04-cli-and-adapters-map.md), [05-tests-and-quality-map.md](05-tests-and-quality-map.md) y [15-tests-adapters-map.md](15-tests-adapters-map.md).

## Siguiente lectura...

Seguir con [17-src-docker-adapter-map.md](17-src-docker-adapter-map.md) si el cambio toca runtime local. Si el cambio toca projection o worktrees, seguir con [18-src-workspace-adapter-map.md](18-src-workspace-adapter-map.md).

## Ruta rápida

1. Empezar aquí cuando cambie `src/odoo_forge_cli/main.py` o el output visible de un command.
2. Identificar qué familia de commands cambió y qué adapter instancia el composition root.
3. Confirmar que el fallo esperado se renderiza como mensaje claro, con exit code correcto y sin traceback.

## Relación directa con `src/odoo_forge_cli/main.py`

`tests/cli/` es la suite que pone bajo presión el composition root real del repo.

| Superficie en `main.py` | Qué afirma la suite |
| --- | --- |
| helpers `_make_*` | que la CLI construye el adapter correcto en el lugar correcto |
| commands `validate`, `lock`, `project`, `unlock` | que el wiring entre manifest/core/workspace/registry produce resultados y errores previsibles |
| commands `run`, `status`, `stop`, `logs`, `exec` | que la familia backend usa identidad, scan y provider solo cuando corresponde |
| commands `image-resolve`, `image-publish`, `image-pull`, `image-exists` | que la familia registry respeta sus boundaries sin invadir backend ni lock |
| render de errores y drift | que la salida pública siga siendo legible, estable y segura |

## Familias de commands cubiertas

| Familia | Archivos principales | Qué comportamientos protege |
| --- | --- | --- |
| Manifest y drift | `test_validate.py`, `test_lock.py` | validación de manifest, round-trip lock/validate, rechazo limpio de lock corrupto, reporte de drift correcto |
| Projection y unlock | `test_project.py`, `test_unlock.py` | proyección de repos, corte limpio ante fallos de checkout, promoción a worktree y naming de branch |
| Runtime backend | `test_backend.py` | `run`, `status`, `stop`, `logs`, `exec`, wiring de credenciales, boundaries de scan y render de errores de provider |
| Image registry | `test_image_registry.py` | resolve/publish/pull/exists, normalización de refs, mensajes de error y aislamiento respecto de backend y lock |

## Qué comportamientos protege de forma explícita

| Comportamiento protegido | Dónde se ve con claridad |
| --- | --- |
| un manifest ausente o malformado debe fallar con mensaje limpio | `test_validate.py`, `test_backend.py` |
| `forge lock` no debe dejar un `project.lock` parcial ni corrupto | `test_lock.py` |
| `forge project` debe detenerse en el primer checkout fallido y nombrar el repo sin filtrar credenciales | `test_project.py` |
| `forge unlock` debe derivar source, destino y branch desde el core y no desde heurística CLI | `test_unlock.py` |
| `forge run` debe rechazar evidencia inválida o refs mal formadas antes de provisionar | `test_backend.py` |
| commands de instancia que no necesitan scan no deben tocar workspace | `test_backend.py` |
| commands de registry no deben invocar backend provider ni mutar `project.lock` | `test_image_registry.py` |

## Por qué los fallos acá son visibles de inmediato

Esta suite está pegada al borde que usa la persona operadora. Por eso un fallo en `tests/cli/` casi siempre significa una de estas cosas:

1. un command dejó de aceptar o validar correctamente su input,
2. el composition root construye el adapter equivocado o en el momento equivocado,
3. la CLI filtró un mensaje crudo del provider,
4. el exit code dejó de representar bien el outcome,
5. o un flujo quedó mezclando capas que deberían seguir separadas.

No es una suite tardía. Es la verificación más cercana a la UX operativa del binario `forge`.

## Qué suele significar un fallo por archivo

| Archivo | Lectura operacional habitual |
| --- | --- |
| `test_validate.py` | `forge validate` puede anunciar éxito falso, leer mal lock drift o esconder errores de manifest/lock |
| `test_lock.py` | `forge lock` puede fijar mal, escribir mal o dejar la frontera de error inconsistente |
| `test_project.py` | la proyección al workspace puede fallar con mensajes inseguros o con control de flujo incompleto |
| `test_unlock.py` | la CLI puede estar calculando mal la promoción a worktree o reportando mal el resultado |
| `test_backend.py` | el runtime local puede estar cableado de forma incorrecta incluso si `src/odoo_forge/backend/` sigue sano |
| `test_image_registry.py` | la familia de commands de imágenes puede perder inmutabilidad, boundaries o clasificación de errores |

## Cómo usar esta suite sin confundir capas

| Si cambiaste... | Mirar primero... | Complementar con... |
| --- | --- | --- |
| semántica pura del manifest o del lock | `tests/manifest/` | `tests/cli/` solo si cambió output o wiring |
| comportamiento concreto de un adapter | `tests/adapters/` | `tests/cli/` si el cambio cruza el boundary del command |
| parseo de opciones, mensajes o exit codes | `tests/cli/` | la suite del core o adapter que soporte el flujo |

## Checklist para maintainers

- Usar `tests/cli/` para contratos públicos del command, no para reemplazar pruebas puras del core.
- Mantener el patrón de mensaje único `error: ...` cuando el fallo cruza la frontera CLI.
- Si cambia un `_make_*` o el adapter instanciado, verificar también el directorio adapter correspondiente.
- Si un command deja de necesitar scan, lock o backend, agregar una prueba que lo haga explícito.
- Si el cambio toca runtime local o registry, seguir con [17-src-docker-adapter-map.md](17-src-docker-adapter-map.md) y [19-src-registry-adapter-map.md](19-src-registry-adapter-map.md).
