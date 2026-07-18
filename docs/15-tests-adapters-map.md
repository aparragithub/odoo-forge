# Mapa De `tests/adapters/`

## Qué es este documento

Es la ficha de mantenimiento de `tests/adapters/`: organiza la suite que verifica el comportamiento concreto de adapters Git, workspace, Docker, registry y PostgreSQL Docker.

## Por qué importa

Importa porque aquí se prueba el borde donde el repositorio deja de trabajar con modelos puros y empieza a hablar con herramientas, procesos, filesystem y daemon Docker. Si esta suite falla, no suele ser un detalle cosmético: suele indicar que el contrato con el mundo exterior ya no se cumple.

## Por qué existe

Existe para que maintainers y futuras personas implementadoras distingan entre pruebas de contrato, pruebas de integración opt-in y pruebas contra Docker real, y sepan leer correctamente lo que significa cada fallo.

## Cómo ayuda al sistema

Ayuda al sistema porque hace verificable que los ports estén bien implementados, que los adapters redacten errores y secretos como corresponde y que el wiring operativo siga siendo confiable.

## Leer después de...

Leer después de [04-cli-and-adapters-map.md](04-cli-and-adapters-map.md), [05-tests-and-quality-map.md](05-tests-and-quality-map.md) y [13-src-ports-map.md](13-src-ports-map.md).

## Siguiente lectura...

Después de esta ficha, la siguiente documentación recomendada es volver a [07-spec-to-module-crosswalk.md](07-spec-to-module-crosswalk.md) para trazar capability -> adapter -> test, y luego a `tests/cli/` cuando el cambio también modifique output o wiring visible.

## Ruta rápida

1. Empezar aquí cuando un cambio toque un adapter concreto o una interacción con herramienta externa.
2. Confirmar si la prueba debe ser default, `integration` o `real_docker`.
3. Leer el fallo como señal operacional, no solo como aserción aislada.

## Familias de adapters cubiertas

| Familia | Archivos principales | Qué validan |
| --- | --- | --- |
| Git source | `test_git_provider.py` | resolución de refs, normalización y redacción de errores |
| Workspace | `test_workspace_provider.py` | checkout, scan, promote y límites de worktree/filesystem |
| Docker backend | `test_docker_provider.py`, `test_docker_provider_integration.py` | ejecución de `BackendPlan`, lifecycle runtime, rollback, readiness, logs y exec |
| Registry y published artifacts | `test_registry_provider.py`, `test_published_artifact_resolver.py` | refs inmutables, existencia, pull/publish y resolución de artifacts publicados |
| PostgreSQL Docker | `test_postgres_docker_provider.py`, `test_postgres_docker_provider_integration.py`, `test_postgres_docker_secret_injection.py`, `test_postgres_docker_authority.py` | lifecycle de base de datos, secretos, autoridad de ownership y cleanup |

## Límites entre default, integration y real_docker

| Capa | Qué incluye aquí | Cuándo usarla |
| --- | --- | --- |
| Default | tests unitarios o de adapter con subprocess/runner simulado | cuando el comportamiento puede verificarse sin daemon real |
| `integration` | tests que ejercitan integración más amplia u opt-in por costo/entorno | cuando el límite existe pero no requiere necesariamente Docker real persistente |
| `real_docker` | tests que necesitan daemon Docker real y semántica operacional genuina | cuando la garantía depende del runtime Docker efectivo |

Casos actuales relevantes:

- `test_docker_provider_integration.py` usa `pytest.mark.integration`.
- `test_postgres_docker_provider_integration.py` usa `pytest.mark.integration` y `pytest.mark.real_docker`.

## Archivos especialmente importantes

| Archivo | Qué protege | Señal principal |
| --- | --- | --- |
| `test_docker_provider.py` | contrato amplio del backend Docker: argv, readiness, rollback, redacción, status, stop, logs, exec | si falla, el runtime local puede estar roto incluso con core sano |
| `test_docker_provider_integration.py` | comportamiento más operativo del adapter Docker en escenarios de integración | si falla, hay desalineación entre mocks y semántica real esperada |
| `test_workspace_provider.py` | scan, checkout y promote frente a filesystem/Git | si falla, manifest/projection puede recibir evidencia errónea |
| `test_git_provider.py` | resolución de refs y clasificación de errores Git | si falla, `forge lock` puede fijar mal o reportar mal |
| `test_registry_provider.py` | provider de image registry | si falla, commands de imágenes o resolución de digests dejan de ser confiables |
| `test_published_artifact_resolver.py` | published layers del manifest | si falla, `build_lock()` puede fijar artifacts incorrectos |
| `test_postgres_docker_provider.py` | lifecycle lógico del adapter de base de datos | si falla, la foundation de database provider pierde garantías |
| `test_postgres_docker_secret_injection.py` | materialización y limpieza segura de secretos | si falla, hay riesgo operativo y de higiene de secretos |
| `test_postgres_docker_authority.py` | ownership authority y decisiones de adopción/cleanup | si falla, el adapter puede tocar recursos que no le pertenecen |
| `test_postgres_docker_provider_integration.py` | semántica real del provider PostgreSQL sobre Docker | si falla, la seguridad operacional del provider está en duda |

## Qué suele significar un fallo aquí

| Área que falla | Lectura operacional habitual |
| --- | --- |
| Git adapter | `forge lock` puede resolver refs o clasificar errores remotos de forma incorrecta |
| Workspace adapter | `project`, `unlock`, `validate` o `run` pueden trabajar con rutas o commits equivocados |
| Docker backend default tests | el adapter Docker rompió un contrato del core, del port o de seguridad/redacción |
| Docker backend integration | el comportamiento esperado no coincide con la forma real en que Docker responde |
| Registry resolver/provider | la cadena manifest/lock/image commands pierde inmutabilidad o clasificación de fallos |
| PostgreSQL secret injection | puede haber filtración, limpieza incompleta o target inválido de secretos |
| PostgreSQL authority/provider | el adapter puede adoptar, restaurar o limpiar recursos sin autoridad segura |
| PostgreSQL real_docker | la implementación pasa en unit tests, pero no resiste condiciones reales del daemon |

## Cómo usar esta suite sin confundir capas

| Si querés validar... | Mirar primero... | No asumir que alcanza con... |
| --- | --- | --- |
| conformidad del contrato puro | `tests/ports/` | solo `tests/adapters/` |
| semántica concreta del adapter | `tests/adapters/` default | solo tests CLI |
| comportamiento operativo costoso o dependiente del entorno | `integration` / `real_docker` | mocks unitarios |

## Por qué esta suite es crítica para evolución segura

El core puede estar impecable y aun así el sistema fallar si un adapter:

1. ejecuta el comando incorrecto,
2. interpreta mal una respuesta externa,
3. no redacta diagnósticos o secretos,
4. deja recursos residuales,
5. o aplica autoridad de ownership equivocada.

`tests/adapters/` es la barrera que detecta esas roturas antes de que lleguen a quienes usan `forge` o a futuras extensiones del repo.

## Checklist para maintainers

- Elegir `integration` y `real_docker` solo cuando la garantía realmente dependa del entorno.
- Mantener los tests default como primera barrera rápida para adapters.
- Si cambia un port, revisar tanto `tests/ports/` como la familia adapter correspondiente.
- Si cambia output visible o wiring CLI, complementar con `tests/cli/`.
- Si el cambio toca runtime local o manifest projection, volver a [11-src-manifest-map.md](11-src-manifest-map.md) y [12-src-backend-map.md](12-src-backend-map.md).
