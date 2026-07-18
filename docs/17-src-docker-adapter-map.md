# Mapa De `src/odoo_forge_docker/`

## Qué es este documento

Es la ficha de mantenimiento de `src/odoo_forge_docker/`: describe el adapter que implementa `BackendProvider` para el runtime local basado en Docker y la inyección efímera de secretos que usa ese runtime.

## Por qué importa

Importa porque este package ejecuta el plan de backend real. Si se altera mal, `forge run`, `status`, `stop`, `logs` y `exec` pueden seguir existiendo como commands pero dejar de ser operativamente confiables.

## Por qué existe

Existe para que maintainers y futuras personas implementadoras separen con claridad qué decide el core en `src/odoo_forge/backend/` y qué debe hacer este adapter al hablar con Docker, archivos temporales y `sops`.

## Cómo ayuda al sistema

Ayuda al sistema porque conserva un boundary ejecutable entre planning puro y runtime real: recibe `BackendPlan`, inyecta secretos de forma acotada, crea recursos, espera readiness, hace rollback cuando corresponde y traduce fallos del daemon a errores tipados.

## Leer después de...

Leer después de [12-src-backend-map.md](12-src-backend-map.md), [13-src-ports-map.md](13-src-ports-map.md) y [16-tests-cli-map.md](16-tests-cli-map.md).

## Siguiente lectura...

Seguir con [18-src-workspace-adapter-map.md](18-src-workspace-adapter-map.md) para la evidencia de mounts que `forge run` consume antes de planificar el backend. Para cobertura concreta, complementar con [15-tests-adapters-map.md](15-tests-adapters-map.md).

## Ruta rápida

1. Empezar aquí si el cambio toca `forge run`, `status`, `stop`, `logs` o `exec`.
2. Confirmar si el cambio pertenece al lifecycle de recursos, a readiness, a rollback o a inyección de secretos.
3. Verificar que el core siga siendo dueño del plan y que el adapter siga siendo dueño de la ejecución Docker.

## Qué vive en este package

| Archivo | Responsabilidad principal | Qué no debe hacer |
| --- | --- | --- |
| `provider.py` | ejecutar `BackendPlan` y lifecycle runtime completo vía Docker CLI | redefinir semántica del plan o mover reglas de negocio al adapter |
| `credential_injection.py` | resolver handles SOPS y materializar secretos efímeros para Docker | persistir plaintext más allá de la ventana mínima de uso |

## Responsabilidades runtime del backend local

| Responsabilidad | Dónde vive | Qué garantiza |
| --- | --- | --- |
| validación previa de credenciales | `DockerBackendProvider.run()` + `SopsEnvFileInjector.validate()` | Docker no recibe launch requests si los handles no son resolubles |
| pull de imagen Odoo | `_pull_image()` | clasificación de auth, not-found y daemon unavailable antes del start |
| creación de red y volúmenes | `_ensure_network()`, `_ensure_volume()` | creación idempotente y verificación de ownership para cleanup seguro |
| arranque de Postgres y Odoo | `_run_container()` | ejecución de `ContainerSpec` con o sin secretos materializados |
| bootstrap inicial | `_run_bootstrap()` | inicialización de base solo cuando el volumen PG fue creado por esta invocación |
| readiness | `_wait_pg_ready()`, `_wait_odoo_healthy()` | el command no declara éxito hasta que Postgres y Odoo alcanzan su condición esperada |
| lifecycle de instancia | `status()`, `stop()`, `logs()`, `exec()` | operaciones posteriores a `run` sin filtrar detalles crudos del daemon |

## Lifecycle de recursos y rollback

`src/odoo_forge_docker/` no solo crea recursos. También decide cómo no dejar residuos peligrosos cuando algo falla.

| Etapa | Regla importante |
| --- | --- |
| creación | cada recurso creado por esta invocación se registra en `created` |
| ownership de volúmenes | se agrega `com.odoo-forge.create-token` y luego se verifica antes de borrar |
| bootstrap fallido | se intenta registrar identidad segura del contenedor para poder limpiarlo |
| rollback | `_rollback()` trabaja en orden inverso y sigue aunque un teardown falle |
| `stop` normal | remueve contenedores y red, pero preserva volúmenes nombrados para soportar `stop -> run` |

La idea central es importante: el adapter no debe limpiar "lo que parece suyo" por intuición. Debe limpiar solo lo que puede atribuir a la invocación correcta.

## Readiness y diagnóstico operativo

| Concern | Implementación | Por qué importa |
| --- | --- | --- |
| readiness de Postgres | `_wait_pg_ready()` usando `pg_isready` vía `docker exec` | evita declarar backend usable antes de que la base responda |
| readiness de Odoo | `_wait_odoo_healthy()` usando `docker inspect` y health status | evita falsos positivos de arranque |
| timeout con evidencia | `_readiness_diagnostics()` | adjunta `inspect` y `logs` redactados antes del rollback |
| timeout acotado | `_wait_until()` + deadlines monotónicos | mantiene una semántica temporal predecible |

## Inyección de secretos

| Componente | Rol |
| --- | --- |
| `SopsCommandResolver` | resuelve `CredentialHandle` desde `credentials.sops.yaml` sin shell |
| `SopsEnvFileInjector.validate()` | fuerza fail-closed antes de tocar Docker |
| `SopsEnvFileInjector.secret_files()` | crea archivos `0600` de vida corta para `secret_env` |
| `SopsEnvFileInjector.redact()` | elimina secretos conocidos de logs y diagnósticos |
| `SopsEnvFileInjector.clear()` | vacía memoria de valores resueltos al terminar `run()` |

La regla de mantenimiento es simple: el plaintext existe solo el tiempo mínimo necesario para que Docker lo consuma y luego se borra. Si esa propiedad se debilita, el riesgo ya no es solo funcional; es de seguridad operativa.

## Qué flujos CLI dependen de este adapter

| Command | Cómo lo usa |
| --- | --- |
| `forge run` | instancia `DockerBackendProvider` desde `_make_backend_provider()`, ejecuta `run(plan)` y depende de rollback/readiness/secret injection |
| `forge status` | deriva `InstanceRef` desde el manifest y llama `status(ref)` |
| `forge stop` | deriva identidad y llama `stop(ref)` preservando volúmenes |
| `forge logs` | pide texto de logs por rol |
| `forge exec` | ejecuta argv dentro del contenedor Odoo y devuelve `ExecResult` |

## Riesgos operativos si se modifica mal

| Cambio mal hecho | Consecuencia real |
| --- | --- |
| relajar validación previa de credenciales | se puede arrancar a medias y fallar tarde con estados difíciles de limpiar |
| tocar rollback sin respetar ownership | el adapter puede borrar recursos ajenos o dejar residuos propios |
| simplificar readiness | `forge run` puede anunciar éxito con Odoo o Postgres aún no utilizables |
| remover redacción de secretos | logs, stderr o diagnósticos pueden filtrar plaintext |
| mover reglas del plan al adapter | el runtime se desacopla del contrato puro y se vuelve impredecible |
| cambiar `stop` para borrar volúmenes nombrados | se rompe la expectativa de persistencia entre reinicios |

## Qué se rompe si esta área se entiende mal

1. La CLI deja de poder prometer que un `run` fallido limpia lo que creó.
2. `status` y `stop` empiezan a depender de detalles frágiles del daemon.
3. Los tests dejan de separar planning puro de ejecución concreta.
4. La política de secretos se degrada aunque el comando siga "funcionando".

## Checklist para maintainers

- Mantener `BackendPlan` como autoridad del qué y `src/odoo_forge_docker/` como dueño del cómo.
- Verificar cualquier cambio de lifecycle contra `tests/adapters/test_docker_provider.py` y `tests/cli/test_backend.py`.
- No introducir nuevas superficies de plaintext persistente en archivos, excepciones o logs.
- Si cambia la selección de mounts o la evidencia de workspace, revisar [18-src-workspace-adapter-map.md](18-src-workspace-adapter-map.md).
- Si cambia la taxonomía de errores visibles, volver también a [12-src-backend-map.md](12-src-backend-map.md).
