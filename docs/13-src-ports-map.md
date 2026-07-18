# Mapa De `src/odoo_forge/ports/`

## Qué es este documento

Es la ficha de mantenimiento de `src/odoo_forge/ports/`: define qué significa un port en este repositorio, qué familias existen y qué adapters concretos las implementan hoy.

## Por qué importa

Importa porque este directorio es el punto donde la arquitectura deja de ser una idea general y se vuelve una frontera verificable. Si los ports se degradan, el core empieza a depender de infraestructura y el repo pierde su forma.

## Por qué existe

Existe para que maintainers y futuras personas implementadoras agreguen capacidades nuevas extendiendo contratos deliberados, no importando adapters por atajo.

## Cómo ayuda al sistema

Ayuda al sistema porque concentra las dependencias permitidas del core hacia el exterior y hace que `import-linter`, tests de protocolos y adapters concretos hablen el mismo lenguaje.

## Leer después de...

Leer después de [03-src-core-map.md](03-src-core-map.md), [04-cli-and-adapters-map.md](04-cli-and-adapters-map.md) y [12-src-backend-map.md](12-src-backend-map.md).

## Siguiente lectura...

Seguir con [14-tests-manifest-map.md](14-tests-manifest-map.md) y [15-tests-adapters-map.md](15-tests-adapters-map.md) para ver cómo se verifican estos límites.

## Ruta rápida

1. Empezar aquí antes de agregar un nuevo side effect al sistema.
2. Confirmar si el comportamiento pertenece a un port existente o requiere uno nuevo.
3. Revisar después qué suite valida el contrato y qué adapter lo implementa.

## Qué es un port en este repo

En `odoo-forge`, un port es un contrato de dependencia definido por el core para pedir trabajo externo sin elegir tecnología concreta.

Eso implica tres reglas:

1. El core importa el port.
2. El adapter implementa el port.
3. La CLI o el composition root conecta ambos.

No es solo una interfaz por estilo. Es la pieza que permite que `src/odoo_forge/` siga puro mientras Git, Docker, registry, filesystem o persistencia viven afuera.

## Familias principales de ports

| Port | Responsabilidad | Implementación actual conocida |
| --- | --- | --- |
| `SourceProvider` | Resolver `url` + `ref` a commit SHA | `src/odoo_forge_git` |
| `WorkspaceProvider` | Checkout, scan y promote de workspaces | `src/odoo_forge_workspace` |
| `BackendProvider` | Ejecutar, inspeccionar, detener, loguear y hacer exec sobre una instancia | `src/odoo_forge_docker` |
| `ImageRegistryProvider` | Publicar, pull, resolver digest y existencia de imágenes | `src/odoo_forge_registry` |
| `PublishedArtifactResolver` | Resolver artifacts `published` del manifest a digests inmutables | `src/odoo_forge_registry` |
| `DatabaseProvider` | Lifecycle de base de datos neutral al provider | `src/odoo_forge_postgres_docker` |
| `DurableOperationStore` | Persistencia replay-safe de workflows durables | no hay adapter canónico cableado en este corte |
| `DurableOperationRecovery` | Registro de intentos/evidencia de recovery | no hay adapter canónico cableado en este corte |

## Familias por propósito

| Familia | Ports incluidos | Qué habilita |
| --- | --- | --- |
| Source y workspace | `SourceProvider`, `WorkspaceProvider` | locking, projection, unlock, scan y materialización |
| Runtime local | `BackendProvider` | `forge run`, `status`, `stop`, `logs`, `exec` |
| Registry y artifacts publicados | `ImageRegistryProvider`, `PublishedArtifactResolver` | commands de imágenes y layers `published` |
| Database foundation | `DatabaseProvider` | provision, restore, adopt, reconcile, delete y cleanup |
| Workflows durables | `DurableOperationStore`, `DurableOperationRecovery` | checkpoints, commit terminal, recovery y cleanup residual |

## Qué implementa cada adapter

| Adapter package | Port o ports que implementa | Dónde se consume |
| --- | --- | --- |
| `src/odoo_forge_git` | `SourceProvider` | `build_lock()` y CLI `lock` |
| `src/odoo_forge_workspace` | `WorkspaceProvider` | `validate`, `project`, `unlock`, `run` |
| `src/odoo_forge_docker` | `BackendProvider` | CLI backend commands |
| `src/odoo_forge_registry` | `ImageRegistryProvider`, `PublishedArtifactResolver` | image commands, locking de published artifacts |
| `src/odoo_forge_postgres_docker` | `DatabaseProvider` | tests y foundations de provider de base de datos |

## Por qué este directorio es central para `import-linter`

`pyproject.toml` impone contratos que prohíben que `odoo_forge` importe infraestructura, CLI y adapters concretos como `odoo_forge_cli`, `odoo_forge_git`, `odoo_forge_workspace`, `odoo_forge_docker` y `odoo_forge_registry`.

La consecuencia práctica es directa: cuando el core necesita hablar con algo externo, el paso legítimo es atravesar `src/odoo_forge/ports/`.

Sin este directorio, el core tendría solo dos caminos malos:

1. Importar adapters concretos y romper la arquitectura.
2. Empujar reglas de negocio hacia la CLI para evitar el problema.

Por eso `ports/` no es accesorio. Es el pasillo central por donde pasan los límites permitidos.

## Qué conviene recordar de cada port

| Port | Forma del contrato | Riesgo si se ensucia |
| --- | --- | --- |
| `SourceProvider` | una operación simple de resolución de ref | locking deja de ser puro o se ata a Git específico |
| `WorkspaceProvider` | operaciones de checkout, scan y promoción | projection empieza a depender de filesystem real |
| `BackendProvider` | ejecución de `BackendPlan` y lifecycle operativo | `backend/` o CLI aprenden detalles Docker inestables |
| `ImageRegistryProvider` | operaciones sobre refs inmutables | registry logic se dispersa fuera de su contrato |
| `PublishedArtifactResolver` | resolución source/version -> digest | `manifest/locking` aprende detalles de provider |
| `DatabaseProvider` | lifecycle completo con credenciales opacas | secrets o handles se filtran a capas incorrectas |
| `DurableOperationStore` | persistencia con revisiones y lifecycle | recovery deja de ser auditable o compare-and-swap seguro |
| `DurableOperationRecovery` | evidencia de recuperación | el workflow durable pierde trazabilidad |

## Señales de diseño sano

- Los ports dependen de tipos del core, no de adapters concretos.
- Los adapters satisfacen `Protocol` y se prueban contra ese contrato.
- La CLI construye adapters concretos, pero no redefine la semántica del port.
- Los errores públicos relevantes viven en el lenguaje del dominio o del provider-neutral contract.

## Qué se rompe si esta área se entiende mal

| Malentendido | Consecuencia real |
| --- | --- |
| Tratar un port como una interfaz ornamental | Aparecen métodos ad hoc solo para un adapter |
| Importar el adapter desde el core "porque es más fácil" | `import-linter` deja de ser una barrera real y los tests puros pierden aislamiento |
| Poner detalles de subprocess, Docker o filesystem en un port | El contrato deja de ser reusable y provider-neutral |
| Crear un port nuevo cuando el problema es solo de wiring CLI | Se fragmenta el lenguaje del dominio sin necesidad |
| Extender un adapter sin extender el port cuando el core sí necesita la capacidad | La lógica termina escondida fuera del contrato arquitectónico |

## Checklist para maintainers

- Antes de agregar una dependencia externa, preguntarse primero qué port debería poseerla.
- Mantener las firmas pequeñas y centradas en el lenguaje del dominio.
- Validar el contrato en `tests/ports/` y el comportamiento concreto en `tests/adapters/`.
- Revisar los contratos de `import-linter` antes de aceptar cualquier import nuevo en `src/odoo_forge/`.
- Si el cambio afecta manifest o backend, volver a [11-src-manifest-map.md](11-src-manifest-map.md) o [12-src-backend-map.md](12-src-backend-map.md).
