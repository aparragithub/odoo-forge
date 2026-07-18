# Mapa De `src/odoo_forge/backend/`

## Qué es este documento

Es la ficha de mantenimiento de `src/odoo_forge/backend/`: describe cómo el core planifica el backend local, cómo interpreta el estado runtime y qué errores tipados expone hacia la CLI y los adapters.

## Por qué importa

Importa porque esta área controla el puente entre intención pura y ejecución real del runtime. Si se contamina con detalles Docker o se simplifican mal sus contratos, el comando visible puede seguir existiendo, pero con resultados engañosos o frágiles.

## Por qué existe

Existe para que maintainers y futuras personas implementadoras distingan claramente entre planificación, introspección de estado y ejecución concreta del adapter Docker.

## Cómo ayuda al sistema

Ayuda al sistema porque mantiene estable el lenguaje de runtime del core: `BackendPlan`, `InstanceRef`, `InstanceStatus`, `ExecResult` y los errores públicos que permiten a la CLI renderizar outcomes previsibles.

## Leer después de...

Leer después de [11-src-manifest-map.md](11-src-manifest-map.md) y [04-cli-and-adapters-map.md](04-cli-and-adapters-map.md).

## Siguiente lectura...

Seguir con [13-src-ports-map.md](13-src-ports-map.md). Para la verificación, continuar luego con [15-tests-adapters-map.md](15-tests-adapters-map.md).

## Ruta rápida

1. Empezar aquí si el cambio toca `forge run`, `status`, `stop`, `logs` o `exec`.
2. Verificar si el cambio es de planning puro, de interpretación de estado o de error model.
3. Confirmar después qué corresponde al core y qué corresponde al adapter Docker.

## Qué vive en este directorio

| Archivo | Responsabilidad principal | Qué no debe hacer |
| --- | --- | --- |
| `plan.py` | Construir `BackendPlan` desde manifest, mounts y parámetros runtime | No debe invocar Docker ni leer subprocess |
| `status.py` | Interpretar introspección ya decodificada en `InstanceStatus` | No debe ejecutar `docker inspect` |
| `errors.py` | Exponer errores públicos tipados del backend | No debe filtrar diagnósticos crudos del provider |

## Entrypoints clave

| Entrypoint | Qué hace | Consumido desde |
| --- | --- | --- |
| `plan_backend()` | Produce el plan autoritativo para runtime local | comando `forge run` |
| `BackendPlan` | Contrato completo que el provider ejecuta | port `BackendProvider` y adapter Docker |
| `parse_status()` | Convierte JSON ya decodificado en `InstanceStatus` | `DockerBackendProvider.status()` |
| `derive_instance_ref()` | Reconstruye identidad de instancia sin inspección del daemon | comandos `status`, `stop`, `logs`, `exec` cuando parten del manifest |
| `instance_ref()` | Deriva la identidad a partir del plan ya armado | `DockerBackendProvider.run()` |
| `BackendError` y subclases | Modelo público de fallos del runtime | adapter Docker y CLI |

## Relación con comandos CLI y adapter Docker

| Superficie | Qué aporta `backend/` | Qué aporta el adapter o la CLI |
| --- | --- | --- |
| `forge run` | Planning puro del runtime y nombres/labels autoritativos | `src/odoo_forge_docker` crea recursos, espera readiness y hace rollback |
| `forge status` | Interpretación tipada del estado de roles | el adapter ejecuta `docker inspect` y entrega JSON |
| `forge stop` | Identidad de instancia y semántica esperada de lifecycle | el adapter detiene y remueve contenedores/red |
| `forge logs` | Identidad de rol y contrato de retorno | el adapter obtiene texto de logs |
| `forge exec` | Contrato del resultado (`ExecResult`) | el adapter ejecuta `docker exec` |

## Qué outcomes visibles controla

| Outcome visible para usuarios | Dónde se define |
| --- | --- |
| Qué contenedores, red y volúmenes componen una instancia | `plan.py` |
| Qué nombres y labels representan la identidad de una instancia | `plan.py`, `status.py` |
| Qué significa que Odoo o Postgres estén listos o no | `status.py` |
| Qué errores se muestran como indisponibilidad, conflicto, timeout o not-found | `errors.py` |
| Qué resultado devuelve `forge exec` aunque el proceso interno salga non-zero | `status.py` mediante `ExecResult` |

## Modelo de planning

`plan.py` no crea contenedores. Define qué debería crear un provider correcto.

Eso incluye, entre otras cosas:

| Concern | Lo fija el core en `plan.py` |
| --- | --- |
| Identidad | network, nombres de contenedor, labels de proyecto/instancia/rol |
| Montajes | binds seleccionados desde la vista autoritativa de manifest/projection |
| Runtime env | variables, puertos y contratos de inyección de secretos |
| Imagen de Odoo | referencia normalizada que el adapter deberá pull/usar |
| Recursos persistentes | volúmenes nombrados y relación entre bootstrap y runtime normal |

Si este plan se entiende como "solo datos internos", se pierde el punto central: es el contrato ejecutable entre el core y `BackendProvider`.

## Modelo de estado runtime

`status.py` define cómo se interpreta el estado de una instancia sin depender de Docker en tiempo de importación.

| Tipo | Rol |
| --- | --- |
| `InstanceRef` | Handle liviano de identidad para una instancia ya conocida |
| `RoleStatus` | Estado de un rol individual (`postgres` u `odoo`) |
| `InstanceStatus` | Vista conjunta de ambos roles |
| `parse_status()` | Traduce JSON ya decodificado a estado tipado |

Reglas importantes de interpretación:

- Contenedor ausente o no running no explota: se interpreta como `exited`.
- Postgres running sin healthcheck se expresa como `no_healthcheck`, no como listo.
- Odoo running sin health válido se expresa como `unknown`, no como saludable.

## Modelo de errores

| Familia de error | Qué representa operacionalmente |
| --- | --- |
| indisponibilidad del daemon | Docker no está disponible o el ejecutable falla |
| conflicto o instancia existente | Ya hay recursos con esa identidad |
| imagen no encontrada o no autorizada | La referencia de imagen no puede usarse tal como fue pedida |
| timeout de readiness | Postgres u Odoo no llegaron al estado esperado a tiempo |
| instancia no encontrada | `status`/`stop`/`logs`/`exec` apuntan a recursos ausentes |

El punto importante es que `errors.py` fija un lenguaje público. El adapter puede tener diagnósticos ricos, pero no debe forzar a la CLI a parsear mensajes frágiles del provider.

## Dependencias entrantes y salientes

| Dirección | Relación |
| --- | --- |
| Entrante desde `src/odoo_forge_cli/main.py` | `run`, `status`, `stop`, `logs` y `exec` consumen tipos y helpers del backend |
| Entrante desde `src/odoo_forge_docker/provider.py` | el adapter ejecuta `BackendPlan` y reutiliza `parse_status()` e identidades |
| Saliente hacia `src/odoo_forge/manifest/` | el planning depende de mounts ya validados y de la semántica del manifest |
| Saliente hacia `src/odoo_forge/ports/backend_provider.py` | el port se tipa con contratos de `backend/` |

## Qué se rompe si esta área se entiende mal

| Malentendido | Consecuencia real |
| --- | --- |
| Mover lógica Docker específica al core | Se rompe el límite hexagonal y los tests puros pierden valor |
| Tratar `BackendPlan` como una conveniencia opcional | El adapter deja de tener un contrato estable para ejecutar |
| Parsear estado runtime directamente en CLI | La presentación queda atada a JSON o labels del provider |
| Exponer errores crudos de Docker como API pública | La UX y los tests dependen de mensajes no estables |
| Confundir identidad derivada con estado observado | `stop` o `logs` pueden apuntar a recursos equivocados o renderizar falsos negativos |

## Checklist para maintainers

- Mantener `backend/` libre de subprocess, Docker SDK y filesystem operativo.
- Si cambia una decisión de planning, revisar el impacto en `src/odoo_forge_docker/` y `tests/backend/`.
- Si cambia la semántica de estado, actualizar primero `tests/backend/test_status.py`.
- Si cambia la taxonomía de errores, validar también `tests/adapters/test_docker_provider*.py` y `tests/cli/test_backend.py`.
- Antes de extender el runtime, revisar [13-src-ports-map.md](13-src-ports-map.md).
