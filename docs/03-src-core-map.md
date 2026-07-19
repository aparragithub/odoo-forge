# Mapa Del Core En `src/`

## Qué es este documento

Es la guía del core puro en `src/odoo_forge/`: explica qué responsabilidades son de dominio, qué subpaquetes existen y qué límites no deben cruzarse.

## Por qué importa

Importa porque el core es la base de la arquitectura hexagonal del proyecto. Si se contamina con CLI, Docker, Git o filesystem, el repo pierde aislamiento, testabilidad y evolución segura.

## Por qué existe

Existe para que maintainers y futuras personas implementadoras puedan tocar el núcleo sin mezclar reglas de negocio con wiring o side effects.

## Cómo ayuda al sistema

Ayuda al sistema porque preserva la dirección correcta de dependencias, aclara dónde nacen los contratos de ports y facilita que los adapters evolucionen sin deformar el dominio.

## Leer Después De...

Leé esto después de [02-repository-authority-matrix.md](02-repository-authority-matrix.md). Siguiente lectura: [04-cli-and-adapters-map.md](04-cli-and-adapters-map.md). Si necesitás cruzar specs aceptadas con módulos concretos, seguí con [07-spec-to-module-crosswalk.md](07-spec-to-module-crosswalk.md) después de la serie principal.

## Ruta Rápida

1. Empezá acá cuando un cambio toque `src/odoo_forge/`.
2. Revisá qué port es dueño del side effect antes de editar.
3. Frená si el cambio obliga al core a importar código de CLI, Docker, Git, `subprocess` o registry.

## Límite Del Core

| Pregunta | Respuesta |
| --- | --- |
| ¿Qué es `src/odoo_forge/`? | El core de dominio y aplicación libre de framework. |
| ¿Qué entra al core? | Datos parseados de manifest, datos de lockfile, hechos de workspace materializado, handles opacos de credenciales, referencias opacas de artifacts y requests neutrales al provider. |
| ¿Qué sale del core? | Plans tipados, lockfiles, reports de drift, identidades de instancia, errores de validación y llamadas a ports que piden side effects sin ejecutarlos. |
| ¿Qué debe quedar afuera? | Concerns de Typer CLI, trabajo `subprocess` con Git/Docker/SOPS/GHCR, mutación de filesystem, network calls y parseo de errores específicos de providers. |

## Subpackages Principales

| Path | Responsabilidad | Nota para maintainers |
| --- | --- | --- |
| `manifest/` | Schema, composición, lockfile, detección de drift, plans de proyección del workspace | Es dueño de la semántica de `project.yaml` y `project.lock` |
| `backend/` | Planning del backend local, status tipado del runtime, errores del backend | Produce plans y tipos de status, no commands Docker |
| `ports/` | Límites de dependencia para side effects | El core depende de estos, los adapters los implementan |
| `image_registry/` | Lógica neutral al provider para referencias de imagen y valores/errores de registry | Lenguaje core de registry sin ejecución GHCR/Docker |
| `database/` | Valores, readiness y errores neutrales al provider para lifecycle de bases de datos | Mantiene opacos creación/adopción/cleanup |
| `credentials/` | Handles opacos de credenciales y descriptores de inyección | Los providers deben recibir handles/descriptors, no plaintext |
| `data_artifacts/` | Contratos de restore-set y outcomes redacted de readiness/discard | Protege la semántica de restore sin imponer implementación de storage |
| `project_catalog/` | Modelos de request de catálogo y lógica de resolución autoritativa | Resuelve un registro autoritativo sin heurísticas de fallback |
| `durable_operations/` | Registros replay-safe de workflow, checkpoints y lifecycle de cleanup residual | Persistencia y recovery quedan detrás de ports |
| `resource_ownership/` | Modelo de ownership de tres estados (`created`/`adopted`/`external`), `ResourceRef` genérico, receipt reusable y atribución opcional de tenant | Vocabulario canónico de `CAP-RESOURCE-OWNERSHIP`; `database/types.py` re-exporta `ResourceOwnership`, `OperationIdentity` y `CreationReceipt` desde acá |

## Ports Que Definen El Límite

| Port | Implementado fuera del core por | Qué espera el core |
| --- | --- | --- |
| `SourceProvider` | `src/odoo_forge_git` | Resolver `url` + `ref` a un commit SHA |
| `WorkspaceProvider` | `src/odoo_forge_workspace` | Checkout, scan y promoción de worktrees |
| `BackendProvider` | `src/odoo_forge_docker` | Ejecutar, inspeccionar, detener, loguear y hacer exec sobre una instancia de backend |
| `ImageRegistryProvider` | `src/odoo_forge_registry` | Publicar, descargar, resolver y verificar existencia de image refs inmutables |
| `PublishedArtifactResolver` | `src/odoo_forge_registry` | Resolver artifacts `registry://` del manifest a digests |
| `DatabaseProvider` | `src/odoo_forge_postgres_docker` hoy | Provisionar, restaurar, adoptar, reconciliar, borrar y limpiar bases de datos |
| `DurableOperationStore` | ningún package concreto listado en este corte | Persistir estado autoritativo del workflow |
| `DurableOperationRecovery` | ningún package concreto listado en este corte | Registrar intentos de recovery sobre estado durable |
| `ResourceOwnershipPort` | ningún package concreto listado en este corte (el adapter Docker `LocalOwnershipAuthority` ya satisface read/attest pero no está cableado a este port) | Leer estado de ownership y receipt/evidence, y atestiguar sin transicionar estado |

## Flujos De Dominio Clave

### Flujo de manifest y lock

| Paso | Dueño en el core | Output |
| --- | --- | --- |
| Parsear y validar manifest | `manifest/schema.py` | `Manifest` |
| Componer intención ordenada | `manifest/composition.py` | cadena core -> layers -> client |
| Resolver refs Git y artifacts publicados | `manifest/locking.py` a través de `SourceProvider` y `PublishedArtifactResolver` | `Lockfile` |
| Detectar drift entre manifest/lock/materializado | `manifest/drift.py` | report de drift tipado |

### Flujo de planning del backend

| Paso | Dueño en el core | Evidencia externa consumida |
| --- | --- | --- |
| Escanear mount roots existentes | adapter vía `WorkspaceProvider.scan()` | hechos crudos de checkout |
| Atribuir repos escaneados a mount roots | `manifest/projection.py` | `MaterializedState` |
| Armar la vista de planning de mounts | `manifest/projection.py` | manifest + lock + estado escaneado |
| Producir backend plan | `backend/plan.py` | `BackendPlan` con handles opacos de credenciales |

### Flujo de credenciales

| Regla | Por qué importa |
| --- | --- |
| El core usa solo `CredentialHandle` y `CredentialInjectionDescriptor` | Los secretos en plaintext nunca deben convertirse en datos del core |
| Los providers reciben handles/descriptors opacos | El adapter decide cómo materializar secretos de forma segura |
| Los errores son tipados y redacted | Los fallos visibles para usuarios no deben filtrar material de credenciales |

### Flujo de data artifacts

| Concern del core | Significado |
| --- | --- |
| `DataArtifactRef` | Referencia opaca a un restore set |
| `DataArtifactCapability.resolve()` | Recupera metadata del manifest del restore set |
| `validate_for_restore()` | Decide si el restore set es coherente y seguro de usar |
| `discard()` | Elimina material de restore del provider con reporting redacted |

### Flujo de durable operations

| Concern del core | Significado |
| --- | --- |
| `DurableOperationStore.create_or_load()` | Vincula o reejecuta una identidad durable |
| checkpoints | Progreso resume-safe antes del commit terminal |
| terminal commit bundle | Outcome autoritativo más hechos de cleanup residual |
| reconciliation / recovery | Hace visible outcomes desconocidos sin elegir scheduler ni tecnología de persistencia |

### Flujo de project catalog

| Paso | Dueño en el core |
| --- | --- |
| Normalizar identificadores provistos | `project_catalog/resolver.py` |
| Consultar matches autoritativos | Interfaz tipo port `CatalogIndex` en `project_catalog/interfaces.py` |
| Rechazar cero, muchos o resultados inválidos | `ProjectCatalogResolutionFailure` |
| Devolver un resultado totalmente validado | `ResolvedCatalogResult` |

### Flujo de database

| Concern del core | Significado |
| --- | --- |
| `DatabaseSpec` | Identidad lógica de base de datos solicitada |
| `DatabaseRef` | Identidad opaca propiedad del provider más metadata de ownership |
| `DatabaseCreation` / `CreationReceipt` | Handoff seguro para reconciliar, borrar y limpiar más adelante |
| `DatabaseProvider` | Contrato de lifecycle que nunca exige credenciales en plaintext ni detalles de storage |

### Flujo de resource ownership

| Concern del core | Significado |
| --- | --- |
| `ResourceOwnership` | Exactamente tres estados (`created`/`adopted`/`external`), sin extensiones en v1 |
| `ResourceRef` | Identificador opaco + `resource_kind` + ownership, generalizado a cualquier tipo de recurso |
| `OwnershipReceipt` | Proof de operación opaco + owned resource ids + expectativa de live-proof; el mecanismo concreto queda en el adapter |
| `TenantAttribution` | Link opcional a tenant compuesto con ownership, nunca mandatorio en el momento de ownership |
| `ResourceOwnershipPort.describe_ownership()` / `.attest_ownership()` | Lectura y atestación sin verbos de transición; `reserve`/`bind`/`activate`/`retire`/`adopt` quedan diferidos a `SP-CONTROL-PLANE-AUTHORITY` |

## Lo Que Maintainers No Deben Hacer En El Core

| No hacer | Por qué |
| --- | --- |
| Importar `typer`, `subprocess`, `docker`, packages de adapters o módulos CLI | Los contratos de import-linter en `pyproject.toml` lo convierten en architecture gate |
| Leer archivos, shell out o pegarle a la red desde `src/odoo_forge/` | Los side effects pertenecen a adapters |
| Reemplazar handles opacos por secretos en plaintext | La materialización de secretos es solo de adapters |
| Filtrar identificadores específicos de providers en tipos públicos de dominio salvo que sean explícitamente opacos | Los contratos del core deben seguir neutrales al provider |
| Poner lógica de wiring fallback en el core para un adapter concreto | El wiring pertenece a `src/odoo_forge_cli/` |
| Devolver `dict` sin tipo cuando ya existe un modelo de dominio estable | Maintainers necesitan contratos explícitos para drift, plans, readiness y fallos |

## Checklist De Edición

- Confirmá que el cambio pueda expresarse con datos puros y funciones puras.
- Si se necesita un side effect, agregá o refiná un port en vez de importar un adapter.
- Actualizá los tests correspondientes bajo `tests/manifest`, `tests/backend`, `tests/ports`, `tests/database`, `tests/credentials`, `tests/data_artifacts`, `tests/project_catalog`, `tests/durable_operations` o `tests/resource_ownership`.
- Revisá otra vez el siguiente doc: [Mapa De CLI Y Adapters](04-cli-and-adapters-map.md) antes de tocar wiring del composition root.
