# Mapa De `src/odoo_forge_postgres_docker/`

## Qué es este documento

Es la ficha de mantenimiento de `src/odoo_forge_postgres_docker/`: documenta la foundation del adapter `DatabaseProvider` para PostgreSQL sobre Docker, su modelo de authority/ownership, su manejo de credenciales y restore artifacts, y el alcance real que tiene hoy dentro del producto.

## Por qué importa

Importa porque esta área contiene garantías de seguridad operacional que son fáciles de degradar sin que el problema sea visible al instante: ownership verificable, cleanup seguro, secretos efímeros y restore validado. Si eso se rompe, el provider puede tocar recursos que no le pertenecen o retener material sensible más tiempo del permitido.

## Por qué existe

Existe para dejar claro que el repo ya tiene una foundation seria para lifecycle de bases de datos, aunque esa foundation todavía no sea la ruta principal de la CLI actual. Mantener esta distinción evita dos errores comunes: subestimarla como código “aislado” o sobreasumir que ya gobierna el runtime local completo.

## Cómo ayuda al sistema

Ayuda al sistema porque implementa el contract de `DatabaseProvider` con reglas fail-closed: valida identifiers, exige pruebas de ownership antes de mutar recursos Docker, materializa credenciales de forma efímera, coordina restore artifacts opacos y deja una base creíble para futuros entornos gestionados.

## Leer después de...

Leer después de [04-cli-and-adapters-map.md](04-cli-and-adapters-map.md), [13-src-ports-map.md](13-src-ports-map.md), [15-tests-adapters-map.md](15-tests-adapters-map.md) y [17-src-docker-adapter-map.md](17-src-docker-adapter-map.md).

## Siguiente lectura...

Después de esta ficha, conviene volver a [07-spec-to-module-crosswalk.md](07-spec-to-module-crosswalk.md) para unir spec -> port -> adapter, y luego a [15-tests-adapters-map.md](15-tests-adapters-map.md) para la cobertura que protege authority, secretos y restore.

## Ruta rápida

1. Empezar aquí cuando el cambio toque `DatabaseProvider`, ownership de recursos Docker, credenciales de base de datos o restore artifacts.
2. Separar si el cambio pertenece al provider, a la authority local, a la inyección de secretos o a los handoffs de credentials/data artifacts.
3. Confirmar si el cambio realmente afecta la CLI principal de hoy o solo esta foundation aislada.

## Qué vive en este package

| Archivo | Responsabilidad principal | Qué no debe asumir |
| --- | --- | --- |
| `provider.py` | lifecycle del provider PostgreSQL sobre Docker | que cualquier contenedor con nombre conocido sea suyo o que el runtime local principal ya dependa de este package |
| `authority.py` | custody local duradera y prueba de ownership | que `docker inspect` por sí solo sea autoridad suficiente |
| `secret_injection.py` | materialización efímera de secretos PostgreSQL | que el provider pueda retener plaintext persistentemente |
| `target_handoffs.py` | handoffs opacos hacia CAP-CREDENTIALS y CAP-DATA-ARTIFACTS | que el provider entienda stores o formats internos de otros capabilities |
| `__init__.py` | export público del provider | nada más que la superficie pública mínima |

## Qué problema resuelve

`src/odoo_forge_postgres_docker/` resuelve un problema distinto de “levantar Postgres en Docker”. Resuelve cómo hacerlo con autoridad demostrable.

| Problema | Cómo lo aborda |
| --- | --- |
| probar que un recurso Docker realmente pertenece a una operación del provider | labels en vivo + `CreationReceipt` + `LocalOwnershipAuthority` |
| evitar mutaciones sobre recursos no probados | `assert_live_ownership()` y verificaciones previas en `verify_runtime_ownership()`, `delete()` y `cleanup()` |
| provisionar con secreto sin persistir plaintext como estado normal | `PostgreSQLSecretInjector` y archivos efímeros `0600` |
| restaurar una base desde artifacts opacos sin exponer detalles del store | `validated_database_restore()` + `restore_injector` |
| reconciliar operaciones duraderas o inciertas | `reconcile()` y el contrato de durable operations que este package ya respeta alrededor del ownership |

## Por qué existe aunque no sea la ruta principal de la CLI hoy

Hoy la CLI principal usa `src/odoo_forge_docker/` como backend local para `forge run`, `status`, `stop`, `logs` y `exec`. Eso NO convierte a `src/odoo_forge_postgres_docker/` en código secundario.

| Hecho actual | Implicación correcta |
| --- | --- |
| la CLI visible no expone un command canónico de `DatabaseProvider` | este package no gobierna la UX principal de runtime hoy |
| el contract `DatabaseProvider` ya existe en el core | esta implementación es una foundation deliberada, no un experimento descartable |
| hay suites específicas `test_postgres_docker_*` | la arquitectura ya trata esta área como boundary serio |
| el roadmap y las specs la referencian | el package prepara integración futura y managed environments |

La lectura correcta es esta: existe para estabilizar la semántica del provider de base de datos ANTES de hacer un cutover más amplio del producto.

## Modelo de authority y ownership que implementa

La pieza más importante de este package es que separa “Docker dice que el recurso existe” de “el sistema puede demostrar que le pertenece”.

| Capa | Qué aporta |
| --- | --- |
| `CreationReceipt` | identidad lógica de la operación y conjunto de recursos que la operación afirma poseer |
| labels Docker | prueba observable en vivo: provider, operación, kind y creator token |
| `LocalOwnershipAuthority` | registro local firmado, privado y fail-closed sobre reserva, activación y retiro |
| `RuntimeOwnershipEvidence` | evidencia opaca emitida solo después de validar ownership real y readiness |

## Lifecycle de ownership en este provider

| Etapa | Acción principal | Garantía |
| --- | --- | --- |
| reserva | `reserve()` antes del `docker run` | el provider registra intención antes de que exista un recurso vivo |
| bind | `bind()` luego de obtener `docker_id` real | el nombre se ata a la identidad inmutable del recurso |
| activación | `activate()` tras verificar labels y ownership | solo un recurso demostrado pasa a estado operable |
| uso y verificación | `verify_runtime_ownership()` | readiness y custody se validan antes de emitir evidencia |
| retiro | `retire()` o `retire_absent()` | cleanup deja trazabilidad y evita reutilizar autoridad histórica |

Esto es FUNDAMENTAL: `docker inspect` solo informa estado actual. La authority local decide si ese estado puede usarse como base legítima para mutar, reconciliar o borrar.

## Relación con base de datos, credenciales, artifacts y operaciones duraderas

| Concern | Cómo participa este package |
| --- | --- |
| base de datos | provisiona, restaura, adopta, reconcilia, borra y limpia recursos PostgreSQL bajo el contract `DatabaseProvider` |
| credenciales | recibe `CredentialHandle`, lo materializa como descriptor opaco y solo después lo inyecta en un target efímero |
| artifacts de datos | valida `DataArtifactRef` para restore sin aprender detalles internos del capability de artifacts |
| operaciones duraderas | usa receipts, identities y recovery-friendly cleanup para soportar lifecycle auditable y reconciliable |
| evidencia runtime | solo emite `RuntimeOwnershipEvidence` cuando ownership + readiness fueron probados realmente |

## Manejo de credenciales y secretos

| Componente | Papel real | Invariante de mantenimiento |
| --- | --- | --- |
| `materialize_database_credentials()` | convierte `CredentialHandle` en `CredentialInjectionDescriptor` para target `database/postgres-docker` | el provider nunca debe pedir plaintext directamente al core |
| `PostgreSQLSecretInjector.inject()` | crea directorio temporal `0700`, archivo secreto `0600` y mount readonly | el plaintext debe existir solo en la ventana mínima necesaria |
| `_erase()` y `_zero_secret()` | vacían y eliminan el archivo efímero | higiene de secretos es requisito, no mejora opcional |

## Restore artifacts y handoffs opacos

| Paso | Qué ocurre |
| --- | --- |
| 1 | `restore()` exige `artifact_capability`; si falta, falla cerrado |
| 2 | `validated_database_restore()` pregunta al capability si el artifact es apto para restore |
| 3 | el provider recibe un `RestoreSetComponent` ya validado |
| 4 | `restore_injector` materializa ese componente sobre la base creada |
| 5 | si restore falla, el provider intenta rollback seguro y puede escalar `RollbackIncompleteError` |

La consecuencia arquitectónica es importante: el adapter conoce el handoff, no el almacenamiento ni el formato interno del artifact.

## Qué significaría una integración más profunda más adelante

Una integración futura más profunda NO sería solo “llamar este provider desde más commands”. Implicaría al menos estas decisiones explícitas.

| Posible integración futura | Lo que realmente significaría |
| --- | --- |
| usar este provider desde la CLI principal | definir una superficie de commands o un runtime path donde `DatabaseProvider` sea autoridad real |
| converger con el backend local actual | decidir cómo se coordinan `src/odoo_forge_docker/` y esta authority de ownership sin duplicar lifecycle |
| soportar managed environments | reemplazar o complementar Docker local por otra implementación manteniendo los mismos contracts del core |
| extender durable operations | persistir recovery y cleanup sobre stores más generales sin perder la semántica fail-closed |

## Qué maintainers no deben asumir hoy

1. No asumir que `forge run` ya usa este package como backend principal.
2. No asumir que cualquier contenedor PostgreSQL con labels parecidos es automáticamente seguro de adoptar.
3. No asumir que la authority local es intercambiable con mero estado JSON informal; sus firmas, permisos y atomicidad son parte del contrato.
4. No asumir que restore artifacts o credenciales pueden inspeccionarse libremente desde el provider.
5. No asumir que una futura integración ya está decidida; hoy existe foundation, no cutover completo.

## Riesgos si se modifica mal

| Cambio mal hecho | Consecuencia real |
| --- | --- |
| relajar validación de identifiers o ownership | el provider puede tocar recursos ajenos o ambiguos |
| degradar atomicidad/custody en `authority.py` | el estado local deja de ser una autoridad creíble |
| persistir plaintext o relajar cleanup de secretos | se rompe la higiene operativa del provider |
| acoplar restore a detalles del artifact store | el adapter invade otro capability y pierde portabilidad |
| conectar este provider a la CLI principal sin spec clara | el producto mezcla foundations con flujos todavía no estabilizados |

## Qué se rompe si esta área se entiende mal

1. `DatabaseProvider` deja de ser una abstracción confiable para futuros entornos.
2. Las operaciones de delete/cleanup pueden volverse inseguras aunque los tests superficiales sigan pasando.
3. La autoridad del sistema sobre ownership se reduce a heurísticas de Docker.
4. Una integración futura con runtime principal o managed providers arrancaría sobre una base conceptual equivocada.

## Checklist para maintainers

- Verificar cualquier cambio contra `tests/adapters/test_postgres_docker_provider.py`, `test_postgres_docker_provider_integration.py`, `test_postgres_docker_secret_injection.py` y `test_postgres_docker_authority.py`.
- Mantener `authority.py` como frontera de custody firmada y fail-closed.
- No mover detalles de credentials ni de data artifacts al core ni a la CLI principal por conveniencia.
- Si se plantea una integración mayor con runtime local, releer antes [17-src-docker-adapter-map.md](17-src-docker-adapter-map.md) y [04-cli-and-adapters-map.md](04-cli-and-adapters-map.md).
- Tratar este package como foundation estratégica: todavía no es el camino CLI principal, pero ya define contratos que el resto del sistema debe poder respetar.
